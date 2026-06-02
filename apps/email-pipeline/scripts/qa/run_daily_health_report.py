#!/usr/bin/env python3
"""Read-only daily pipeline health report (no Gmail/DB mutations).

Writes under ``reports/out/active/current/daily_health_report_<YYYY_MM_DD>/`` by default.
Does not send email, apply suppressions, refresh mirrors, or ingest Gmail.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.mart_core_postgres_migrate import resolve_sqlite_path
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)
from origenlab_email_pipeline.qa.daily_health_report import (
    build_daily_health_report,
    default_date_label,
    default_out_dir,
    exit_code_for_result,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=None, help="SQLite path (default: settings)")
    p.add_argument(
        "--active-current",
        type=Path,
        default=_REPO / "reports" / "out" / "active" / "current",
    )
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="manifest.json (default: <active-current>/manifest.json)",
    )
    p.add_argument("--since-days", type=int, default=2)
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--date-label", default=None, help="Folder suffix, default YYYY_MM_DD")
    p.add_argument("--json-only", action="store_true", help="Print summary JSON to stdout")
    p.add_argument(
        "--fail-on-blocked",
        action="store_true",
        help="Exit 2 when health verdict is BLOCKED (default exit 1)",
    )
    p.add_argument("--skip-postgres", action="store_true")
    p.add_argument("--skip-ndr", action="store_true", help="Troubleshooting only")
    p.add_argument("--postgres-url", default=None)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    sqlite_path = resolve_sqlite_path(args.db)
    active_current = args.active_current.resolve()
    manifest_path = (args.manifest or (active_current / "manifest.json")).resolve()
    label = args.date_label or default_date_label()
    out_dir = (args.out_dir or default_out_dir(_REPO, label)).resolve()

    result = build_daily_health_report(
        repo_root=_REPO,
        sqlite_path=sqlite_path,
        active_current=active_current,
        manifest_path=manifest_path,
        out_dir=out_dir,
        since_days=args.since_days,
        date_label=label,
        skip_postgres=args.skip_postgres,
        skip_ndr=args.skip_ndr,
        gmail_user=resolve_outbound_gmail_user(settings, explicit=None),
        sent_folders=resolve_outbound_sent_folders(None),
        postgres_url=args.postgres_url,
    )

    payload = result.to_summary_dict()
    payload["out_dir"] = str(out_dir)
    if args.json_only:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"health_verdict={result.health_verdict}")
        print(f"out_dir={out_dir}")
        for reason in result.health_reasons:
            print(f"  reason: {reason}")
    return exit_code_for_result(result, fail_on_blocked=args.fail_on_blocked)


if __name__ == "__main__":
    sys.exit(main())
