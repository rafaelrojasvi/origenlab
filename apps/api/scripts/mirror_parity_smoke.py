#!/usr/bin/env python3
"""GET-only smoke for apps/api mirror routes on :8001.

Uses stdlib HTTP only. Does not mutate Gmail, SQLite, or Postgres.

Example:
  cd apps/api
  uv run python scripts/mirror_parity_smoke.py --mirror-base http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_MIRROR_ROUTES: tuple[tuple[str, dict[str, str | int]], ...] = (
    ("/mirror/health/dependencies", {}),
    ("/mirror/meta/dashboard-sync", {}),
    ("/mirror/dashboard/summary", {"scope": "canonical"}),
    ("/mirror/classification/summary", {}),
    ("/mirror/classification/recent", {"limit": 5}),
    ("/mirror/classification/actions", {}),
    ("/mirror/commercial/purchase-events", {"limit": 5}),
    ("/mirror/contacts", {"limit": 5, "offset": 0}),
    ("/mirror/organizations", {"limit": 5, "offset": 0}),
    ("/mirror/outbound/suppressions/emails", {"limit": 5}),
    ("/mirror/outbound/contact-state", {"limit": 5}),
    ("/mirror/outbound/readiness", {}),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mirror-base",
        default="http://127.0.0.1:8001",
        help="apps/api mirror base URL",
    )
    parser.add_argument(
        "--event-id",
        type=int,
        default=1,
        help="Purchase event id for detail route (skipped unless --include-commercial-detail)",
    )
    parser.add_argument(
        "--include-commercial-detail",
        action="store_true",
        help="Also GET /mirror/commercial/purchase-events/{id}",
    )
    args = parser.parse_args(argv)

    report: dict[str, Any] = {"routes": [], "errors": []}
    unreachable: list[str] = []

    routes = list(_MIRROR_ROUTES)
    if args.include_commercial_detail:
        eid = args.event_id
        routes.append((f"/mirror/commercial/purchase-events/{eid}", {}))

    for path, params in routes:
        status, data, err = _get(args.mirror_base, path, params)
        entry: dict[str, Any] = {"path": path, "status": status}
        if status == -1:
            unreachable.append(f"{path}: {err}")
        elif status != 200:
            report["errors"].append(f"{path}: HTTP {status}")
        elif data is None:
            report["errors"].append(f"{path}: non-JSON body")
        else:
            entry["keys"] = sorted(data.keys())
        report["routes"].append(entry)

    print(json.dumps(report, indent=2, default=str))
    if unreachable:
        print("ERROR: mirror server unreachable:", file=sys.stderr)
        for msg in unreachable:
            print(f"  {msg}", file=sys.stderr)
        return 2
    if report["errors"]:
        print("FAIL:", file=sys.stderr)
        for err in report["errors"]:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("OK: mirror smoke passed (GET /mirror/* on :8001).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
