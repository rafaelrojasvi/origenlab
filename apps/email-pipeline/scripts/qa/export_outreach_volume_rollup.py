#!/usr/bin/env python3
"""Read-only rollup: unique outreach / Sent / contacted volume by source.

Aggregates Gmail Sent (SQLite ``emails``), ``outreach_contact_state``, send manifests,
and known marketing CSVs under ``reports/out/active``. Does not modify the database,
send mail, or change gate logic.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from dataclasses import dataclass
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

_ROLLUP_FIELDS = [
    "source_kind",
    "source_name",
    "file_path_or_db_source",
    "campaign_tag",
    "row_count",
    "unique_email_count",
    "sent_count",
    "contacted_state_count",
    "overlap_sent_and_state_count",
    "earliest_date",
    "latest_date",
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


def _parse_send_manifest(path: Path) -> tuple[list[str], int, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    counter = {"total": 0}
    _add_manifest_emails(payload, out, counter)
    root = payload if isinstance(payload, dict) else {}
    return out, int(counter["total"]), root


def _manifest_campaign_tag(path: Path, root: dict[str, Any]) -> str:
    for k in ("campaign_tag", "campaign", "source", "batch_name", "batch"):
        v = root.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()[:240]
    return (path.parent.name or path.stem)[:240]


@dataclass(frozen=True)
class _CsvScan:
    row_count: int
    emails: frozenset[str]
    earliest: str
    latest: str


def _scan_csv_emails(path: Path) -> _CsvScan:
    emails: set[str] = set()
    dates: list[str] = []
    row_count = 0
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = {str(h or "").strip().lower(): h for h in (reader.fieldnames or []) if h is not None}
        date_keys = [headers[k] for k in _DATE_FIELDS if k in headers]
        for row in reader:
            row_count += 1
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
            for dk in date_keys:
                dv = str(row.get(dk) or "").strip()
                if dv:
                    dates.append(dv)
    earliest = min(dates) if dates else ""
    latest = max(dates) if dates else ""
    return _CsvScan(row_count=row_count, emails=frozenset(emails), earliest=earliest, latest=latest)


def _load_gmail_sent_stats(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
) -> tuple[int, frozenset[str], str, str]:
    """Return (n_email_rows, unique_recipients, earliest_date, latest_date)."""
    if not _table_exists(conn, "emails"):
        return 0, frozenset(), "", ""
    user = gmail_user.strip()
    folders = tuple(f.strip() for f in sent_folders if f.strip())
    if not user or not folders:
        return 0, frozenset(), "", ""
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
    norms: set[str] = set()
    dates: list[str] = []
    n_rows = 0
    for recipients, dts in cur:
        n_rows += 1
        d = str(dts or "").strip()
        if d:
            dates.append(d)
        if not recipients:
            continue
        for e in emails_in(recipients):
            norms.add(e)
    earliest = min(dates) if dates else ""
    latest = max(dates) if dates else ""
    return n_rows, frozenset(norms), earliest, latest


def _load_outreach_blocking(
    conn: sqlite3.Connection,
) -> tuple[int, frozenset[str], str, str]:
    if not outreach_contact_state_table_exists(conn):
        return 0, frozenset(), "", ""
    rows = conn.execute(
        """
        SELECT lower(trim(contact_email_norm)) AS e,
               COALESCE(NULLIF(TRIM(last_contacted_at), ''), NULLIF(TRIM(first_contacted_at), ''), '')
        FROM outreach_contact_state
        WHERE state IN ('contacted', 'replied', 'snoozed')
          AND length(trim(contact_email_norm)) > 0
        """
    ).fetchall()
    emails: set[str] = set()
    dates: list[str] = []
    for e, ts in rows:
        if not e:
            continue
        emails.add(str(e))
        d = str(ts or "").strip()
        if d:
            dates.append(d)
    earliest = min(dates) if dates else ""
    latest = max(dates) if dates else ""
    return len(rows), frozenset(emails), earliest, latest


def _cross_counts(emails: Iterable[str], sent: set[str], state: set[str]) -> tuple[int, int, int]:
    em = set(emails)
    sent_c = len(em & sent)
    st_c = len(em & state)
    ov = len(em & sent & state)
    return sent_c, st_c, ov


def _rel_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _discover_active_files(active_root: Path) -> list[tuple[str, str, Path, str]]:
    """(source_kind, source_name, path, campaign_tag_hint)."""
    found: list[tuple[str, str, Path, str]] = []
    if not active_root.is_dir():
        return found

    for p in sorted(active_root.rglob("send_manifest.json")):
        found.append(("send_manifest", p.parent.name or "send_manifest", p, p.parent.name))

    send_ready = active_root / "current" / "send_ready.csv"
    if send_ready.is_file():
        found.append(("send_ready_csv", "send_ready", send_ready, "current"))

    def _add_glob(label: str, pattern: str) -> None:
        for p in sorted(active_root.rglob(pattern)):
            if not p.is_file():
                continue
            found.append(("marketing_csv", label, p, ""))

    _add_glob("all_known_marketing_contacts_dedup", "all_known_marketing_contacts_dedup.csv")
    _add_glob("outreach_contacted_all", "outreach_contacted_all.csv")
    for p in sorted(active_root.rglob("chile_institutional_*.csv")):
        found.append(("marketing_csv", "chile_institutional", p, ""))
    for p in sorted(active_root.rglob("deepsearch_*.csv")):
        found.append(("marketing_csv", "deepsearch", p, ""))

    seen: set[Path] = set()
    deduped: list[tuple[str, str, Path, str]] = []
    for kind, name, path, tag in found:
        rp = path.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        deduped.append((kind, name, path, tag))
    return deduped


def _row_dict(
    *,
    source_kind: str,
    source_name: str,
    file_path_or_db_source: str,
    campaign_tag: str,
    row_count: int,
    unique_emails: frozenset[str],
    sent_set: set[str],
    state_set: set[str],
    earliest_date: str,
    latest_date: str,
    notes: str,
) -> dict[str, str]:
    sent_c, st_c, ov = _cross_counts(unique_emails, sent_set, state_set)
    return {
        "source_kind": source_kind,
        "source_name": source_name,
        "file_path_or_db_source": file_path_or_db_source,
        "campaign_tag": campaign_tag,
        "row_count": str(row_count),
        "unique_email_count": str(len(unique_emails)),
        "sent_count": str(sent_c),
        "contacted_state_count": str(st_c),
        "overlap_sent_and_state_count": str(ov),
        "earliest_date": earliest_date,
        "latest_date": latest_date,
        "notes": notes,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--reports-out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active",
        help="Root for campaign reports (default: reports/out/active under app)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for rollup CSV + JSON (default: <reports-out-dir>/current)",
    )
    ap.add_argument("--gmail-user", default=None, help="Override Gmail mailbox for Sent scan")
    ap.add_argument("--sent-folder", action="append", default=[], help="Sent folder label (repeatable)")
    args = ap.parse_args(argv)

    settings = load_settings()
    db_path = args.db or Path(settings.sqlite_path)
    if not db_path.is_file():
        print(f"SQLite database not found: {db_path}", file=sys.stderr)
        return 1

    out_dir = args.out_dir or (args.reports_out_dir / "current")
    out_dir.mkdir(parents=True, exist_ok=True)
    rollup_path = out_dir / "outreach_volume_rollup.csv"
    summary_path = out_dir / "outreach_volume_summary.json"

    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)

    conn = _connect_readonly(db_path)
    try:
        n_sent_rows, sent_emails, sent_early, sent_late = _load_gmail_sent_stats(
            conn, gmail_user=gmail_user, sent_folders=sent_folders
        )
        n_state_rows, state_emails, st_early, st_late = _load_outreach_blocking(conn)
    finally:
        conn.close()

    sent_set = set(sent_emails)
    state_set = set(state_emails)

    rollup_rows: list[dict[str, str]] = []

    db_sent_descr = (
        f"emails:gmail:{gmail_user}/folder_in({','.join(sent_folders)})"
    )
    rollup_rows.append(
        _row_dict(
            source_kind="gmail_sent",
            source_name="gmail_sent",
            file_path_or_db_source=db_sent_descr,
            campaign_tag="",
            row_count=n_sent_rows,
            unique_emails=sent_emails,
            sent_set=sent_set,
            state_set=state_set,
            earliest_date=sent_early,
            latest_date=sent_late,
            notes="Recipient norms from Sent folder rows; case-insensitive dedupe.",
        )
    )
    rollup_rows.append(
        _row_dict(
            source_kind="outreach_contact_state",
            source_name="outreach_contact_state",
            file_path_or_db_source="outreach_contact_state:contacted|replied|snoozed",
            campaign_tag="",
            row_count=n_state_rows,
            unique_emails=state_emails,
            sent_set=sent_set,
            state_set=state_set,
            earliest_date=st_early,
            latest_date=st_late,
            notes="Sidecar states that block cold export.",
        )
    )

    marketing_union: set[str] = set()
    rel_root = _ROOT

    for kind, name, path, tag_hint in _discover_active_files(args.reports_out_dir):
        rel = _rel_path(path, rel_root)
        notes = ""
        if kind == "send_manifest":
            try:
                raw_list, n_slots, root = _parse_send_manifest(path)
            except (json.JSONDecodeError, OSError) as exc:
                rollup_rows.append(
                    {
                        "source_kind": kind,
                        "source_name": name,
                        "file_path_or_db_source": rel,
                        "campaign_tag": tag_hint,
                        "row_count": "0",
                        "unique_email_count": "0",
                        "sent_count": "0",
                        "contacted_state_count": "0",
                        "overlap_sent_and_state_count": "0",
                        "earliest_date": "",
                        "latest_date": "",
                        "notes": f"parse_error: {exc}",
                    }
                )
                continue
            tag = _manifest_campaign_tag(path, root) or tag_hint
            uniq = frozenset(raw_list)
            sent_c, st_c, _ov = _cross_counts(uniq, sent_set, state_set)
            rollup_rows.append(
                {
                    "source_kind": kind,
                    "source_name": name,
                    "file_path_or_db_source": rel,
                    "campaign_tag": tag,
                    "row_count": str(n_slots),
                    "unique_email_count": str(len(uniq)),
                    "sent_count": str(sent_c),
                    "contacted_state_count": str(st_c),
                    "overlap_sent_and_state_count": str(len(uniq & sent_set & state_set)),
                    "earliest_date": "",
                    "latest_date": "",
                    "notes": notes or "Recipients extracted from JSON manifest.",
                }
            )
            continue

        # CSV paths (marketing + send_ready)
        try:
            scan = _scan_csv_emails(path)
        except OSError as exc:
            rollup_rows.append(
                {
                    "source_kind": kind,
                    "source_name": name,
                    "file_path_or_db_source": rel,
                    "campaign_tag": tag_hint,
                    "row_count": "0",
                    "unique_email_count": "0",
                    "sent_count": "0",
                    "contacted_state_count": "0",
                    "overlap_sent_and_state_count": "0",
                    "earliest_date": "",
                    "latest_date": "",
                    "notes": f"read_error: {exc}",
                }
            )
            continue

        if kind == "marketing_csv" and name in (
            "all_known_marketing_contacts_dedup",
            "outreach_contacted_all",
            "chile_institutional",
            "deepsearch",
        ):
            marketing_union.update(scan.emails)

        sent_c, st_c, ov = _cross_counts(scan.emails, sent_set, state_set)
        rollup_rows.append(
            {
                "source_kind": kind,
                "source_name": name,
                "file_path_or_db_source": rel,
                "campaign_tag": tag_hint,
                "row_count": str(scan.row_count),
                "unique_email_count": str(len(scan.emails)),
                "sent_count": str(sent_c),
                "contacted_state_count": str(st_c),
                "overlap_sent_and_state_count": str(ov),
                "earliest_date": scan.earliest,
                "latest_date": scan.latest,
                "notes": "",
            }
        )

    with rollup_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_ROLLUP_FIELDS, lineterminator="\n")
        w.writeheader()
        for row in rollup_rows:
            w.writerow(row)

    overlap_ss = len(sent_set & state_set)
    sent_not_state = len(sent_set - state_set)
    state_not_sent = len(state_set - sent_set)

    top_sources = sorted(
        (
            r
            for r in rollup_rows
            if r["source_kind"] in ("send_manifest", "marketing_csv", "send_ready_csv")
        ),
        key=lambda r: int(r["unique_email_count"] or 0),
        reverse=True,
    )[:15]

    summary = {
        "schema_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "db_path": str(db_path.resolve()),
        "gmail_user": gmail_user,
        "sent_folders": list(sent_folders),
        "reports_out_dir": str(args.reports_out_dir.resolve()),
        "totals": {
            "unique_sent_recipients_gmail": len(sent_set),
            "unique_contacted_state_emails": len(state_set),
            "unique_known_marketing_contacts_union": len(marketing_union),
            "overlap_sent_and_contacted_state": overlap_ss,
            "sent_but_not_contacted_state_count": sent_not_state,
            "contacted_state_but_not_in_sent_count": state_not_sent,
        },
        "outputs": {
            "rollup_csv": str(rollup_path.resolve()),
            "summary_json": str(summary_path.resolve()),
        },
        "top_sources_by_unique_email_count": [
            {
                "source_kind": r["source_kind"],
                "source_name": r["source_name"],
                "path": r["file_path_or_db_source"],
                "unique_email_count": int(r["unique_email_count"] or 0),
            }
            for r in top_sources
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("Outreach volume rollup (read-only)")
    print(f"  db: {db_path}")
    print(f"  Gmail Sent unique recipients: {len(sent_set):,}")
    print(f"  outreach_contact_state (contacted|replied|snoozed) unique: {len(state_set):,}")
    print(f"  Known marketing CSV union (dedup|outreach_contacted|chile_institutional*|deepsearch*): {len(marketing_union):,}")
    print(f"  Overlap Sent ∩ contacted_state: {overlap_ss:,}")
    print(f"  Possible missing state marks (in Sent, not in contacted_state): {sent_not_state:,}")
    print(f"  Possible missing Sent ingest (in contacted_state, not in Sent): {state_not_sent:,}")
    print("  Top sources by unique_email_count:")
    for r in top_sources[:8]:
        print(f"    - {r['unique_email_count']:>6}  {r['source_kind']}/{r['source_name']}  {r['file_path_or_db_source']}")
    print(f"Wrote: {rollup_path}")
    print(f"Wrote: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
