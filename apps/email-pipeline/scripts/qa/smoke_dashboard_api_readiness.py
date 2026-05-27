#!/usr/bin/env python3
"""Read-only smoke: deployed OrigenLab dashboard API readiness (Phase 9E).

Does not send email, mutate Gmail, or write SQLite/Postgres.

Example:
  uv run python scripts/qa/smoke_dashboard_api_readiness.py \\
    --api-base https://api.origenlab.cl

  uv run python scripts/qa/smoke_dashboard_api_readiness.py \\
    --api-base http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SRC = REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from origenlab_email_pipeline.qa.dashboard_api_readiness import (  # noqa: E402
    run_dashboard_api_smoke,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base",
        required=True,
        help="Operator API base URL (e.g. https://api.origenlab.cl or http://127.0.0.1:8001)",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to write machine-readable report (no secrets)",
    )
    args = parser.parse_args(argv)

    report = run_dashboard_api_smoke(args.api_base, timeout=args.timeout)
    for line in report.summary_lines():
        print(line)

    if args.json_out:
        payload = {
            "api_base": report.api_base,
            "passed": report.passed,
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail} for c in report.checks
            ],
        }
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.json_out}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
