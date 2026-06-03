#!/usr/bin/env python3
"""Read-only QA: heuristic «commercial type» labels on canonical Gmail (contacto@origenlab.cl).

Does **not** mutate SQLite, suppression, or outreach state. Uses keyword/heuristic rules from
:mod:`origenlab_email_pipeline.email_classification_qa` — not a claim of ground truth.

Examples:
  uv run python scripts/qa/audit_email_classification_quality.py --days 90 --limit 400
  uv run python scripts/qa/audit_email_classification_quality.py --json --out /tmp/classification_audit.json

Internal domains for counterparty parsing default to ``origenlab.cl`` and ``labdelivery.cl`` only
(see ``qa_operational_internal_domains``). Optional comma-separated env:
``ORIGENLAB_INTERNAL_DOMAINS=partner.cl``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.qa.email_classification_quality import (
    attach_audit_meta,
    connect_readonly,
    emit_baseline_delta,
    run_audit,
    write_review_csv,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: settings)")
    ap.add_argument("--days", type=int, default=120, help="lookback window on date_iso (default 120)")
    ap.add_argument("--limit", type=int, default=2500, help="max rows to scan (default 2500)")
    ap.add_argument("--json", action="store_true", help="print JSON summary to stdout")
    ap.add_argument("--out", type=Path, default=None, help="write full JSON audit to this path")
    ap.add_argument(
        "--csv-out",
        type=Path,
        default=_ROOT / "reports" / "out" / "qa" / "email_classification_review_sample.csv",
        help="manual review CSV path (default under reports/out/qa/); omit with --no-csv",
    )
    ap.add_argument(
        "--no-csv",
        action="store_true",
        help="do not write the manual review CSV",
    )
    ap.add_argument(
        "--legacy-also",
        action="store_true",
        help="reserved: optional legacy comparison (not implemented; documents intent only)",
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = (args.db or settings.resolved_sqlite_path()).expanduser().resolve()
    if not db_path.is_file():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 2

    conn = connect_readonly(db_path)
    try:
        payload = run_audit(conn, days=args.days, limit=args.limit, legacy_also=args.legacy_also)
    finally:
        conn.close()

    payload = attach_audit_meta(payload, db_path=db_path, days=args.days, limit=args.limit)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote JSON: {args.out}", file=sys.stderr)

    if not args.no_csv and args.csv_out:
        write_review_csv(args.csv_out, payload["review_csv_rows"])
        print(f"Wrote CSV: {args.csv_out}", file=sys.stderr)

    emit_baseline_delta(payload["summary"])

    if args.json:
        slim = {
            "meta": payload["meta"],
            "summary": payload["summary"],
            "reliability_notes": payload["reliability_notes"],
            "baseline_comparison": payload["baseline_comparison"],
        }
        print(json.dumps(slim, ensure_ascii=False, indent=2))
    else:
        s = payload["summary"]
        print(f"SQLite: {db_path}", file=sys.stderr)
        print(f"Rows scanned: {s['rows_scanned']}", file=sys.stderr)
        print("Counts (primary label):", file=sys.stderr)
        for k, v in sorted(s["counts_by_primary"].items(), key=lambda kv: (-int(kv[1]), kv[0])):
            print(f"  {k}: {v}", file=sys.stderr)
        print(f"Ambiguous (multi-tag): {s['ambiguous_rows']}", file=sys.stderr)
        print(f"Inbox commercial-ish sin quote_request fuerte: {s['likely_missed_quote_request']}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
