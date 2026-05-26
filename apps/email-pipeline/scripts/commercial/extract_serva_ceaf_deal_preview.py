#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# Read-only SERVA → CEAF commercial deal preview from local SQLite.
# Does not mutate Gmail, outreach state, or any database.
# -----------------------------------------------------------------------------
"""Extract SERVA/CEAF deal evidence preview (JSON/CSV under active/current)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from origenlab_email_pipeline.commercial.serva_ceaf_deal_preview import (  # noqa: E402
    build_serva_ceaf_deal_preview,
    connect_sqlite_readonly,
    write_preview_outputs,
)
from origenlab_email_pipeline.config import load_settings  # noqa: E402

DEFAULT_OUT = (
    _ROOT / "reports" / "out" / "active" / "current" / "commercial_deals_preview"
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite-db", type=Path, default=None, help="Override ORIGENLAB_SQLITE_PATH")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory (default: reports/out/active/current/commercial_deals_preview)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    db_path = (args.sqlite_db or settings.resolved_sqlite_path()).expanduser().resolve()
    if not db_path.is_file():
        print(f"ERROR: SQLite database not found: {db_path}", file=sys.stderr)
        return 2

    conn = connect_sqlite_readonly(db_path)
    try:
        preview = build_serva_ceaf_deal_preview(conn)
    finally:
        conn.close()

    json_path, csv_path, public_path = write_preview_outputs(
        preview, args.out_dir.expanduser().resolve()
    )
    print(f"DB (read-only): {db_path}")
    print(f"Wrote: {json_path}")
    print(f"Wrote: {public_path}")
    print(f"Wrote: {csv_path}")
    print(f"deal_key={preview['deal_key']}")
    ev = preview["evidence"]
    print(
        f"emails={ev['email_count_total']} (preview {ev['email_count_in_preview']}) "
        f"attachments={ev['attachment_count_total']} (preview {ev['attachment_count_in_preview']})"
    )
    if ev.get("truncated"):
        print("note=evidence lists truncated to top relevant rows; see JSON")
    rec = preview.get("reconciliation") or {}
    print(f"reconciliation_status={rec.get('reconciliation_status')}")
    print(f"deal_status={preview['fields']['deal_status']['value']}")
    if preview.get("missing_fields"):
        print(f"missing_fields={','.join(preview['missing_fields'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
