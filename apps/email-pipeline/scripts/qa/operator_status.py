#!/usr/bin/env python3
"""Read-only operator status: SQLite, DNR files, canonical queues, manifest warnings.

Does not send email, mutate Gmail, write SQLite/Postgres, or run migrations.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.operator_status_report import (
    build_operator_status_report,
    format_human_report,
)
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)

_DEFAULT_ACTIVE = _REPO / "reports/out/active/current"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=None, help="SQLite path (default: settings)")
    p.add_argument(
        "--active-current",
        type=Path,
        default=_DEFAULT_ACTIVE,
        help="active/current directory (default: reports/out/active/current)",
    )
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="manifest.json path (default: <active-current>/manifest.json)",
    )
    p.add_argument("--json-out", type=Path, default=None, help="Write full JSON report")
    p.add_argument("--json", action="store_true", help="Print JSON to stdout instead of human text")
    return p


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings()
    sqlite_path = (args.db or settings.resolved_sqlite_path()).resolve()
    active_current = args.active_current.resolve()
    manifest_path = (args.manifest or (active_current / "manifest.json")).resolve()

    report = build_operator_status_report(
        sqlite_path=sqlite_path,
        active_current=active_current,
        manifest_path=manifest_path,
        gmail_user=resolve_outbound_gmail_user(settings, explicit=None),
        sent_folders=resolve_outbound_sent_folders(None),
    )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(report.to_json_obj(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(report.to_json_obj(), indent=2, ensure_ascii=False))
    else:
        print(format_human_report(report))

    if report.verdict == "BLOCKED":
        return 1
    if report.verdict == "CAUTION":
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
