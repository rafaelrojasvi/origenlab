#!/usr/bin/env python3
"""CLI for cloud Postgres URL validation (used by ops shell scripts)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.cloud_postgres_url import (  # noqa: E402
    ensure_psycopg_driver_url,
    postgres_url_host_db,
    shell_prepare_lines,
    validate_cloud_postgres_url,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser(
        "prepare",
        help="Print NORMALIZED_URL and HOST_DB shell assignments (read ORIGENLAB_CLOUD_POSTGRES_URL).",
    )
    p_prepare.add_argument(
        "--url",
        default=None,
        help="Postgres URL (default: ORIGENLAB_CLOUD_POSTGRES_URL env).",
    )

    p_validate = sub.add_parser("validate", help="Validate URL; exit 2 on failure.")
    p_validate.add_argument("--url", default=None, help="Postgres URL (default: env).")

    p_norm = sub.add_parser("normalize", help="Print psycopg driver URL to stdout.")
    p_norm.add_argument("--url", default=None, help="Postgres URL (default: env).")

    p_host = sub.add_parser("host-db", help="Print host/db only (no credentials).")
    p_host.add_argument("--url", default=None, help="Postgres URL (default: env).")

    args = parser.parse_args(argv)

    def _resolved_url(explicit: str | None) -> str:
        return (explicit or os.environ.get("ORIGENLAB_CLOUD_POSTGRES_URL") or "").strip()

    if args.command == "prepare":
        url = _resolved_url(args.url)
        code, payload = shell_prepare_lines(url)
        if code != 0:
            print(payload, file=sys.stderr)
            return code
        print(payload)
        return 0

    url = _resolved_url(args.url)

    if args.command == "validate":
        errors = validate_cloud_postgres_url(url)
        if errors:
            for err in errors:
                print(f"ERROR: {err}", file=sys.stderr)
            return 2
        return 0

    if args.command == "normalize":
        errors = validate_cloud_postgres_url(url)
        if errors:
            for err in errors:
                print(f"ERROR: {err}", file=sys.stderr)
            return 2
        print(ensure_psycopg_driver_url(url))
        return 0

    if args.command == "host-db":
        errors = validate_cloud_postgres_url(url)
        if errors:
            for err in errors:
                print(f"ERROR: {err}", file=sys.stderr)
            return 2
        print(postgres_url_host_db(url))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
