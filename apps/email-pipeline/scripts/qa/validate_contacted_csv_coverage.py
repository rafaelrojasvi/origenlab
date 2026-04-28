#!/usr/bin/env python3
"""Read-only audit: Sent recipients vs contacted/do-not-repeat CSV coverage.

Compares normalized recipient emails from Gmail Sent history against:
- reports/out/active/current/do_not_repeat_master.csv
- reports/out/active/outreach_contacted_all.csv
- reports/out/active/all_known_marketing_contacts_dedup.csv

No SQLite writes, no CSV rewrites, no network calls.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)

EMAIL_FIELDS: tuple[str, ...] = (
    "email_norm",
    "contact_email",
    "resolved_contact_email",
    "email",
    "to",
    "recipient",
    "real_to",
    "effective_to",
    "recipient_email",
)


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


def _norm_email(value: str) -> str | None:
    found = emails_in(str(value or ""))
    if not found:
        return None
    return found[0].strip().lower()


def _csv_email_counter(path: Path) -> tuple[Counter[str], int]:
    counter: Counter[str] = Counter()
    rows_scanned = 0
    if not path.is_file():
        return counter, rows_scanned
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = {str(h or "").strip().lower(): h for h in (reader.fieldnames or [])}
        candidate_cols = [headers[c] for c in EMAIL_FIELDS if c in headers]
        for row in reader:
            rows_scanned += 1
            em: str | None = None
            for col in candidate_cols:
                em = _norm_email(str(row.get(col) or ""))
                if em:
                    break
            if em:
                counter[em] += 1
    return counter, rows_scanned


def _load_sent_norms(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
) -> tuple[set[str], int]:
    if not _table_exists(conn, "emails"):
        return set(), 0
    user = gmail_user.strip()
    folders = tuple(f.strip() for f in sent_folders if f.strip())
    if not user or not folders:
        return set(), 0
    like_pat = f"gmail:{user}/%".lower()
    ph = ",".join("?" * len(folders))
    cur = conn.execute(
        f"""
        SELECT recipients FROM emails
        WHERE lower(source_file) LIKE ?
          AND folder IN ({ph})
        """,
        (like_pat, *folders),
    )
    out: set[str] = set()
    rows_scanned = 0
    for (recipients,) in cur:
        rows_scanned += 1
        if not recipients:
            continue
        for em in emails_in(recipients):
            out.add(em.strip().lower())
    return out, rows_scanned


def _pairwise_overlaps(
    sets_by_name: dict[str, set[str]],
) -> dict[str, dict[str, Any]]:
    keys = list(sets_by_name.keys())
    out: dict[str, dict[str, Any]] = {}
    for i, left in enumerate(keys):
        for right in keys[i + 1 :]:
            inter = sets_by_name[left] & sets_by_name[right]
            out[f"{left}__{right}"] = {
                "count": len(inter),
                "sample": sorted(inter)[:25],
            }
    return out


def _csv_stats(counter: Counter[str], rows_scanned: int) -> dict[str, int]:
    return {
        "rows_scanned": rows_scanned,
        "unique_emails": len(counter),
        "duplicate_unique_emails": sum(1 for n in counter.values() if n > 1),
        "duplicate_extra_rows": sum(n - 1 for n in counter.values() if n > 1),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--reports-active", type=Path, default=_ROOT / "reports" / "out" / "active")
    ap.add_argument("--gmail-user", default=None)
    ap.add_argument("--sent-folder", action="append", default=[])
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite database not found: {db_path}", file=sys.stderr)
        return 1

    reports_active = Path(args.reports_active)
    csv_paths = {
        "do_not_repeat_master": reports_active / "current" / "do_not_repeat_master.csv",
        "outreach_contacted_all": reports_active / "outreach_contacted_all.csv",
        "all_known_marketing_contacts_dedup": reports_active / "all_known_marketing_contacts_dedup.csv",
    }
    missing = [name for name, path in csv_paths.items() if not path.is_file()]
    if missing:
        print(f"Missing required CSV files: {', '.join(missing)}", file=sys.stderr)
        return 2

    counters: dict[str, Counter[str]] = {}
    rows_scanned_by_csv: dict[str, int] = {}
    for name, path in csv_paths.items():
        ctr, rows_scanned = _csv_email_counter(path)
        counters[name] = ctr
        rows_scanned_by_csv[name] = rows_scanned

    csv_sets = {k: set(v.keys()) for k, v in counters.items()}

    gmail_user = resolve_outbound_gmail_user(settings, explicit=args.gmail_user)
    sent_folders = resolve_outbound_sent_folders(args.sent_folder)
    conn = _connect_readonly(db_path)
    try:
        sent_norms, sent_rows_scanned = _load_sent_norms(
            conn,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
        )
    finally:
        conn.close()

    sent_vs_csv: dict[str, dict[str, Any]] = {}
    mismatched = False
    for name, email_set in csv_sets.items():
        missing_from_csv = sorted(sent_norms - email_set)
        csv_not_in_sent = sorted(email_set - sent_norms)
        intersection = sent_norms & email_set
        sent_vs_csv[name] = {
            "intersection_count": len(intersection),
            "sent_missing_from_csv_count": len(missing_from_csv),
            "sent_missing_from_csv_sample": missing_from_csv[:25],
            "csv_not_in_sent_count": len(csv_not_in_sent),
            "csv_not_in_sent_sample": csv_not_in_sent[:25],
        }
        if missing_from_csv:
            mismatched = True

    payload = {
        "ok": True,
        "read_only": True,
        "db_path": str(db_path.resolve()),
        "gmail_user": gmail_user,
        "sent_folders": list(sent_folders),
        "sent_email_rows_scanned": sent_rows_scanned,
        "sent_unique_emails": len(sent_norms),
        "csv_paths": {k: str(v.resolve()) for k, v in csv_paths.items()},
        "csv_stats": {
            k: _csv_stats(counters[k], rows_scanned_by_csv[k]) for k in csv_paths.keys()
        },
        "pairwise_overlaps": _pairwise_overlaps(csv_sets),
        "sent_vs_csv": sent_vs_csv,
        "strict_failures": mismatched,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    if args.strict and mismatched:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
