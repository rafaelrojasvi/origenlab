#!/usr/bin/env python3
"""Apply a minimal review action (approve | reject | snooze) to a commercial candidate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.commercial.commercial_intel_review import apply_review_action  # noqa: E402
from origenlab_email_pipeline.config import load_settings  # noqa: E402
from origenlab_email_pipeline.db import connect  # noqa: E402
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entity-kind", required=True, choices=("organization", "contact", "opportunity"))
    ap.add_argument("--entity-key", required=True, help="org_domain, contact_email, or opportunity_key.")
    ap.add_argument("--action", required=True, choices=("approve", "reject", "snooze"))
    ap.add_argument("--actor", default="cli", help="Actor label stored on override/event.")
    ap.add_argument("--note", default="", help="Optional note (reason_text / note_text).")
    ap.add_argument("--run-id", type=int, default=None, help="Optional pipeline run id for the audit row.")
    args = ap.parse_args()

    settings = load_settings()
    conn = connect(settings.resolved_sqlite_path())
    try:
        migrate_sqlite_schema(conn, layers={SchemaLayer.ARCHIVE_AND_MART, SchemaLayer.COMMERCIAL_INTEL})
        result = apply_review_action(
            conn,
            entity_kind=args.entity_kind,
            entity_key=args.entity_key,
            action=args.action,
            actor=args.actor,
            note=args.note,
            run_id=args.run_id,
        )
    finally:
        conn.close()

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
