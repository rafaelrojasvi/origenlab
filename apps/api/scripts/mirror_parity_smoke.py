#!/usr/bin/env python3
"""Optional GET-only smoke: compare legacy :8000 routes to mirror :8001 twins.

Requires both servers running (see apps/api/docs/API-3_PHASE2_PARITY_CHECKLIST.md).
Uses stdlib HTTP only. Does not mutate Gmail, SQLite, or Postgres.

Example:
  cd apps/api
  uv run python scripts/mirror_parity_smoke.py \\
    --legacy-base http://127.0.0.1:8000 \\
    --mirror-base http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Keep in sync with tests/mirror/parity_routes.py
_ROUTE_PAIRS: tuple[tuple[str, str, dict[str, str | int]], ...] = (
    ("/health/dependencies", "/mirror/health/dependencies", {}),
    ("/meta/dashboard-sync", "/mirror/meta/dashboard-sync", {}),
    ("/dashboard/summary", "/mirror/dashboard/summary", {"scope": "canonical"}),
    ("/classification/summary", "/mirror/classification/summary", {}),
    ("/classification/recent", "/mirror/classification/recent", {"limit": 5}),
    ("/classification/actions", "/mirror/classification/actions", {}),
    ("/commercial/purchase-events", "/mirror/commercial/purchase-events", {"limit": 5}),
    ("/contacts", "/mirror/contacts", {"limit": 5, "offset": 0}),
    ("/organizations", "/mirror/organizations", {"limit": 5, "offset": 0}),
    ("/outbound/suppressions/emails", "/mirror/outbound/suppressions/emails", {"limit": 5}),
    ("/outbound/contact-state", "/mirror/outbound/contact-state", {"limit": 5}),
    ("/outbound/readiness", "/mirror/outbound/readiness", {}),
)


def _get(base: str, path: str, params: dict[str, str | int]) -> tuple[int, dict[str, Any] | None, str]:
    query = urllib.parse.urlencode(params) if params else ""
    url = f"{base.rstrip('/')}{path}" + (f"?{query}" if query else "")
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = int(resp.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        status = int(exc.code)
    except urllib.error.URLError as exc:
        return -1, None, str(exc.reason)
    if not body.strip():
        return status, None, ""
    try:
        return status, json.loads(body), body[:300]
    except json.JSONDecodeError:
        return status, None, body[:300]


def _top_level_keys(data: dict[str, Any] | None) -> set[str] | None:
    if data is None:
        return None
    return set(data.keys())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--legacy-base",
        default="http://127.0.0.1:8000",
        help="Legacy email-pipeline API base URL",
    )
    parser.add_argument(
        "--mirror-base",
        default="http://127.0.0.1:8001",
        help="apps/api mirror base URL",
    )
    parser.add_argument(
        "--event-id",
        type=int,
        default=1,
        help="Purchase event id for detail pair (skipped if either side not 200)",
    )
    parser.add_argument(
        "--skip-commercial-detail",
        action="store_true",
        help="Do not compare /commercial/purchase-events/{id}",
    )
    args = parser.parse_args(argv)

    report: dict[str, Any] = {"pairs": [], "errors": []}
    unreachable: list[str] = []

    pairs = list(_ROUTE_PAIRS)
    if not args.skip_commercial_detail:
        eid = args.event_id
        pairs.append(
            (
                f"/commercial/purchase-events/{eid}",
                f"/mirror/commercial/purchase-events/{eid}",
                {},
            )
        )

    for legacy_path, mirror_path, params in pairs:
        leg_status, leg_json, leg_err = _get(args.legacy_base, legacy_path, params)
        mir_status, mir_json, mir_err = _get(args.mirror_base, mirror_path, params)
        entry: dict[str, Any] = {
            "legacy": legacy_path,
            "mirror": mirror_path,
            "legacy_status": leg_status,
            "mirror_status": mir_status,
        }
        if leg_status == -1:
            unreachable.append(f"legacy {legacy_path}: {leg_err}")
        if mir_status == -1:
            unreachable.append(f"mirror {mirror_path}: {mir_err}")
        if leg_status >= 0 and mir_status >= 0:
            if leg_status != mir_status:
                report["errors"].append(
                    f"status mismatch {legacy_path}: legacy={leg_status} mirror={mir_status}"
                )
            elif leg_status == 200 and mir_status == 200:
                leg_keys = _top_level_keys(leg_json)
                mir_keys = _top_level_keys(mir_json)
                entry["legacy_keys"] = sorted(leg_keys or [])
                entry["mirror_keys"] = sorted(mir_keys or [])
                if leg_keys != mir_keys:
                    report["errors"].append(
                        f"JSON top-level keys differ {legacy_path}: "
                        f"legacy-only={sorted(leg_keys - mir_keys)} "
                        f"mirror-only={sorted(mir_keys - leg_keys)}"
                    )
        report["pairs"].append(entry)

    print(json.dumps(report, indent=2, default=str))
    if unreachable:
        print("ERROR: server unreachable (start both uvicorn processes):", file=sys.stderr)
        for msg in unreachable:
            print(f"  {msg}", file=sys.stderr)
        return 2
    if report["errors"]:
        print("FAIL:", file=sys.stderr)
        for err in report["errors"]:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("OK: legacy vs mirror parity smoke passed (status + top-level keys).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
