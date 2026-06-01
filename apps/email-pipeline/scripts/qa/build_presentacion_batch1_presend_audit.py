#!/usr/bin/env python3
"""Pre-send audit for Presentación OrigenLab Batch 1 (read-only, no sends)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.campaigns.presentacion_origenlab_presend_audit import (
    run_batch1_presend_audit,
    write_presend_audit_outputs,
)
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.leads.contacted_universe_audit import connect_readonly
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active" / "current",
    )
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--gmail-user", default=None)
    ap.add_argument("--sent-folder", action="append", default=[])
    args = ap.parse_args(argv)

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite not found: {db_path}", file=sys.stderr)
        return 1

    out_dir = args.out_dir.resolve()
    conn = connect_readonly(db_path)
    try:
        result = run_batch1_presend_audit(
            conn,
            out_dir,
            gmail_user=resolve_outbound_gmail_user(settings, explicit=args.gmail_user),
            sent_folders=resolve_outbound_sent_folders(args.sent_folder),
        )
    finally:
        conn.close()

    paths = write_presend_audit_outputs(result, out_dir)
    s = result.summary
    print("Presentación Batch 1 pre-send audit (read-only) — NO SEND")
    print(f"  Input:     {s.get('input_count')}")
    print(f"  Approved:  {s.get('approved_count')}")
    print(f"  Removed:   {s.get('removed_count')}")
    print(f"  Replaced:  {s.get('replaced_count')}")
    print(f"  Final CSV: {paths['final']}")
    print(f"  Dry-run:   {paths['dry_run']}")
    if result.removed:
        print("  Removed:")
        for r in result.removed:
            print(f"    - {r['email']}: {r['reason_codes']}")
    if result.replaced:
        print("  Replaced with:")
        for r in result.replaced:
            print(f"    + {r['replacement_email']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
