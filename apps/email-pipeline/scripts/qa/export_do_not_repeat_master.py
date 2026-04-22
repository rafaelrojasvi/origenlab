#!/usr/bin/env python3
"""Build a unified do-not-repeat email master list (read-only).

Merges Gmail Sent recipients, outreach sidecar state, suppressions, marketing CSVs,
send manifests, and send_ready from the active reports tree. Does not modify SQLite.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)
from origenlab_email_pipeline.outreach_contact_state import outreach_contact_state_table_exists

_CSV_EMAIL_FIELDS = (
    "contact_email",
    "resolved_contact_email",
    "email",
    "to",
    "recipient",
    "real_to",
    "effective_to",
    "recipient_email",
)
_DATE_FIELDS = (
    "last_contacted_at",
    "first_contacted_at",
    "contacted_at",
    "date_iso",
    "sent_at",
    "date",
)

_MASTER_FIELDS = [
    "email_norm",
    "source_kinds",
    "source_count",
    "first_seen_at",
    "last_seen_at",
    "notes",
]


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _norm_email_from_cell(text: str) -> str | None:
    found = emails_in(str(text or ""))
    if not found:
        return None
    return found[0].strip().lower()


def _add_manifest_emails(node: Any, out: list[str], counter: dict[str, int]) -> None:
    if isinstance(node, str):
        counter["total"] += 1
        em = _norm_email_from_cell(node)
        if em:
            out.append(em)
        return
    if isinstance(node, list):
        for item in node:
            _add_manifest_emails(item, out, counter)
        return
    if isinstance(node, dict):
        for key in _CSV_EMAIL_FIELDS:
            if key in node:
                counter["total"] += 1
                em = _norm_email_from_cell(str(node.get(key) or ""))
                if em:
                    out.append(em)
        for key in ("recipients", "to", "emails", "sent_recipients", "results", "messages"):
            if key in node:
                _add_manifest_emails(node[key], out, counter)


def _parse_send_manifest(path: Path) -> tuple[list[str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    counter = {"total": 0}
    _add_manifest_emails(payload, out, counter)
    root = payload if isinstance(payload, dict) else {}
    return out, root


def _sent_recipient_date_bounds(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
) -> tuple[dict[str, tuple[str, str]], int]:
    if not _table_exists(conn, "emails"):
        return {}, 0
    user = gmail_user.strip()
    folders = tuple(f.strip() for f in sent_folders if f.strip())
    if not user or not folders:
        return {}, 0
    like_pat = f"gmail:{user}/%".lower()
    ph = ",".join("?" * len(folders))
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(emails)").fetchall()}
    date_expr = (
        "COALESCE(NULLIF(TRIM(date_iso), ''), NULLIF(TRIM(date_raw), ''), '')"
        if "date_raw" in cols
        else "COALESCE(NULLIF(TRIM(date_iso), ''), '')"
    )
    cur = conn.execute(
        f"""
        SELECT recipients, {date_expr} AS dts
        FROM emails
        WHERE lower(source_file) LIKE ?
          AND folder IN ({ph})
        """,
        (like_pat, *folders),
    )
    out: dict[str, tuple[str, str]] = {}
    n_rows = 0
    for recipients, dts in cur:
        n_rows += 1
        ds = str(dts or "").strip()
        if not recipients:
            continue
        for em in emails_in(recipients):
            prev = out.get(em)
            if prev is None:
                out[em] = (ds, ds)
                continue
            old_min, old_max = prev
            new_min = ds if ds and (not old_min or ds < old_min) else old_min
            new_max = ds if ds and (not old_max or ds > old_max) else old_max
            out[em] = (new_min, new_max)
    return out, n_rows


def _load_outreach_blocking_with_dates(
    conn: sqlite3.Connection,
) -> dict[str, tuple[str, str]]:
    if not outreach_contact_state_table_exists(conn):
        return {}
    rows = conn.execute(
        """
        SELECT lower(trim(contact_email_norm)) AS e,
               COALESCE(NULLIF(TRIM(first_contacted_at), ''), ''),
               COALESCE(NULLIF(TRIM(last_contacted_at), ''), '')
        FROM outreach_contact_state
        WHERE state IN ('contacted', 'replied', 'snoozed')
          AND length(trim(contact_email_norm)) > 0
        """
    ).fetchall()
    out: dict[str, tuple[str, str]] = {}
    for e, f, l in rows:
        if not e:
            continue
        dates = [d for d in (str(f or "").strip(), str(l or "").strip()) if d]
        if not dates:
            out[str(e)] = ("", "")
        else:
            out[str(e)] = (min(dates), max(dates))
    return out


def _load_suppression_emails(conn: sqlite3.Connection) -> set[str]:
    if not _table_exists(conn, "contact_email_suppression"):
        return set()
    rows = conn.execute(
        "SELECT lower(trim(email)) AS e FROM contact_email_suppression WHERE length(trim(email)) > 0"
    ).fetchall()
    return {str(r[0]) for r in rows if r[0]}


def _rel_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _discover_active_files(active_root: Path) -> list[tuple[str, str, Path]]:
    found: list[tuple[str, str, Path]] = []
    if not active_root.is_dir():
        return found
    for p in sorted(active_root.rglob("send_manifest.json")):
        found.append(("send_manifest", p.parent.name or "manifest", p))
    send_ready = active_root / "current" / "send_ready.csv"
    if send_ready.is_file():
        found.append(("send_ready_csv", "send_ready", send_ready))

    def _add_glob(label: str, pattern: str) -> None:
        for p in sorted(active_root.rglob(pattern)):
            if p.is_file():
                found.append(("marketing_csv", label, p))

    _add_glob("all_known_marketing_contacts_dedup", "all_known_marketing_contacts_dedup.csv")
    _add_glob("outreach_contacted_all", "outreach_contacted_all.csv")
    for p in sorted(active_root.rglob("chile_institutional_*.csv")):
        found.append(("marketing_csv", "chile_institutional", p))
    for p in sorted(active_root.rglob("deepsearch_*.csv")):
        found.append(("marketing_csv", "deepsearch", p))

    seen: set[Path] = set()
    deduped: list[tuple[str, str, Path]] = []
    for kind, name, path in found:
        rp = path.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        deduped.append((kind, name, path))
    return deduped


def _scan_csv_emails(path: Path) -> set[str]:
    emails: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = {str(h or "").strip().lower(): h for h in (reader.fieldnames or []) if h is not None}
        for row in reader:
            em: str | None = None
            for field in _CSV_EMAIL_FIELDS:
                lk = field.lower()
                if lk not in headers:
                    continue
                raw = row.get(headers[lk])
                em = _norm_email_from_cell(str(raw or ""))
                if em:
                    break
            if em:
                emails.add(em)
    return emails


@dataclass
class _Agg:
    kinds: set[str] = field(default_factory=set)
    paths: set[str] = field(default_factory=set)
    merge_count: int = 0
    first: str = ""
    last: str = ""

    def touch(
        self,
        kind: str,
        *,
        path: str | None = None,
        dmin: str = "",
        dmax: str = "",
    ) -> None:
        self.kinds.add(kind)
        self.merge_count += 1
        if path:
            self.paths.add(path)
        for d in (dmin, dmax):
            ds = str(d or "").strip()
            if not ds:
                continue
            if not self.first or ds < self.first:
                self.first = ds
            if not self.last or ds > self.last:
                self.last = ds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument(
        "--reports-out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active",
    )
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--gmail-user", default=None)
    ap.add_argument("--sent-folder", action="append", default=[])
    args = ap.parse_args(argv)

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite database not found: {db_path}", file=sys.stderr)
        return 1

    out_dir = args.out_dir or (args.reports_out_dir / "current")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "do_not_repeat_master.csv"
    txt_path = out_dir / "do_not_repeat_master.txt"
    summary_path = out_dir / "do_not_repeat_summary.json"

    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)
    rel_root = _ROOT

    conn = _connect_readonly(db_path)
    try:
        sent_bounds, _n_sent_rows = _sent_recipient_date_bounds(
            conn, gmail_user=gmail_user, sent_folders=sent_folders
        )
        outreach_dates = _load_outreach_blocking_with_dates(conn)
        suppressed = _load_suppression_emails(conn)
    finally:
        conn.close()

    agg: dict[str, _Agg] = {}

    for em, (dmin, dmax) in sent_bounds.items():
        a = agg.setdefault(em, _Agg())
        a.touch("gmail_sent", dmin=dmin, dmax=dmax)

    for em, (dmin, dmax) in outreach_dates.items():
        a = agg.setdefault(em, _Agg())
        a.touch("outreach_state", dmin=dmin, dmax=dmax)

    for em in suppressed:
        a = agg.setdefault(em, _Agg())
        a.touch("email_suppression")

    file_email_counts: Counter[str] = Counter()

    for kind, name, path in _discover_active_files(args.reports_out_dir):
        rel = _rel_path(path, rel_root)
        tag = f"{kind}:{name}"
        if kind == "send_manifest":
            try:
                emails, _root = _parse_send_manifest(path)
            except (json.JSONDecodeError, OSError):
                continue
            for em in emails:
                a = agg.setdefault(em, _Agg())
                a.touch(tag, path=rel)
            file_email_counts[rel] += len(set(emails))
            continue
        try:
            emails = _scan_csv_emails(path)
        except OSError:
            continue
        for em in emails:
            a = agg.setdefault(em, _Agg())
            a.touch(tag, path=rel)
        file_email_counts[rel] += len(emails)

    rows_out: list[dict[str, str]] = []
    for em in sorted(agg.keys()):
        a = agg[em]
        kinds = ";".join(sorted(a.kinds))
        notes_paths = sorted(a.paths)[:8]
        notes = f"paths={','.join(notes_paths)}" if notes_paths else ""
        rows_out.append(
            {
                "email_norm": em,
                "source_kinds": kinds,
                "source_count": str(a.merge_count),
                "first_seen_at": a.first,
                "last_seen_at": a.last,
                "notes": notes[:2000],
            }
        )

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_MASTER_FIELDS, lineterminator="\n")
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    txt_path.write_text("\n".join(sorted(agg.keys())) + "\n", encoding="utf-8")

    n_gmail = sum(1 for a in agg.values() if "gmail_sent" in a.kinds)
    n_state = sum(1 for a in agg.values() if "outreach_state" in a.kinds)
    n_supp = sum(1 for a in agg.values() if "email_suppression" in a.kinds)
    def _from_reports_file(kinds: Iterable[str]) -> bool:
        for k in kinds:
            if k.startswith("marketing_csv:") or k.startswith("send_manifest:") or k.startswith(
                "send_ready_csv:"
            ):
                return True
        return False

    n_mkt = sum(1 for a in agg.values() if _from_reports_file(a.kinds))
    top_files = [p for p, _ in file_email_counts.most_common(12)]

    summary = {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "db_path": str(db_path.resolve()),
        "gmail_user": gmail_user,
        "sent_folders": list(sent_folders),
        "reports_out_dir": str(args.reports_out_dir.resolve()),
        "unique_emails": len(agg),
        "from_gmail_sent": n_gmail,
        "from_outreach_state": n_state,
        "from_email_suppression": n_supp,
        "from_marketing_csv_or_manifest_or_send_ready_files": n_mkt,
        "top_source_files_by_email_rows_scanned": top_files,
        "outputs": {
            "csv": str(csv_path.resolve()),
            "txt": str(txt_path.resolve()),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("Do-not-repeat master (read-only)")
    print(f"  unique emails: {len(agg):,}")
    print(f"  from Gmail Sent: {n_gmail:,}")
    print(f"  from outreach_state (contacted|replied|snoozed): {n_state:,}")
    print(f"  from email_suppression: {n_supp:,}")
    print(f"  touched marketing/manifest/send_ready files (subset overlap): {n_mkt:,}")
    print("  top source files:")
    for p in top_files[:8]:
        print(f"    - {p} ({file_email_counts[p]:,} email cells)")
    print(f"Wrote: {csv_path}")
    print(f"Wrote: {txt_path}")
    print(f"Wrote: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
