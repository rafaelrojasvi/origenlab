#!/usr/bin/env python3
"""Reconcile lead_master with external_leads_raw: soft-retire missing upstream keys.

Compares (source_name, canonical source_record_id) in ``external_leads_raw`` to
``lead_master``. Default is **dry-run** (no writes). Use ``--apply`` to set
``upstream_sync_state = 'retired_no_raw'`` and append ``lead_upstream_reconcile_log``.

Conservative rule: if a ``source_name`` has **zero** rows in ``external_leads_raw``,
no ``lead_master`` rows for that source are retired (avoids wiping a source when
fetch was skipped). Use ``--sources`` to limit which sources participate.

Reactivation: the next ``normalize_leads.py`` upsert clears retirement when the raw
row exists again.

Usage::

    uv run python scripts/leads/reconcile_lead_upstream.py
    uv run python scripts/leads/reconcile_lead_upstream.py --apply
    uv run python scripts/leads/reconcile_lead_upstream.py --sources chilecompra,inn_labs
    uv run python scripts/leads/reconcile_lead_upstream.py --json-out /tmp/reconcile.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_upstream_reconcile import (
    dump_reconcile_json,
    format_reconcile_report,
    run_upstream_reconcile,
)
from origenlab_email_pipeline.leads_schema import ensure_leads_tables


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Dry-run or apply soft-retire for lead_master rows missing from external_leads_raw.",
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write retire flags + reconcile log (default: dry-run only).",
    )
    ap.add_argument(
        "--sources",
        type=str,
        default="",
        help="Comma-separated source_name filter (must still have raw rows to be in scope).",
    )
    ap.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write full result JSON to this path.",
    )
    ap.add_argument(
        "--preview-limit",
        type=int,
        default=40,
        help="Max candidate rows to print (default: 40).",
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    conn.execute("PRAGMA busy_timeout=30000")
    ensure_leads_tables(conn)

    only: frozenset[str] | None = None
    if (args.sources or "").strip():
        only = frozenset(s.strip() for s in args.sources.split(",") if s.strip())

    result = run_upstream_reconcile(conn, dry_run=not args.apply, only_sources=only)
    conn.close()

    for line in format_reconcile_report(result, preview_limit=args.preview_limit):
        print(line)

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(dump_reconcile_json(result), encoding="utf-8")
        print(f"Wrote JSON: {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
