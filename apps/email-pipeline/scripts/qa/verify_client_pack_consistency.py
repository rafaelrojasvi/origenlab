#!/usr/bin/env python3
"""Cross-check client pack summary.json, live SQLite, top20 CSV, and readiness exports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.operational_trust import (
    TrustCheck,
    any_critical_failed,
    check_cohort_partition,
    leads_active_paths,
    verify_client_pack_against_db,
    verify_top20_and_readiness,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--repo-root",
        type=Path,
        default=REPO,
        help="Email-pipeline repo root (default: inferred from script location)",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (default: ORIGENLAB_SQLITE_PATH or data_root default)",
    )
    return p


def run(args: argparse.Namespace) -> int:
    repo = args.repo_root.resolve()
    db = args.db
    if db is None:
        db = load_settings().resolved_sqlite_path()
    else:
        db = db.resolve()
    paths = leads_active_paths(repo)
    checks: list[TrustCheck] = []
    checks.extend(
        verify_client_pack_against_db(paths.client_pack_summary.resolve(), db)
    )
    checks.extend(
        verify_top20_and_readiness(
            top20_path=paths.top20.resolve(),
            ready_path=paths.ready.resolve(),
            needs_path=paths.needs.resolve(),
            hunt_path=paths.hunt.resolve(),
            db_path=db,
        )
    )
    checks.extend(
        check_cohort_partition(
            paths.hunt.resolve(),
            paths.ready.resolve(),
            paths.needs.resolve(),
            paths.not_ready.resolve(),
        )
    )
    for c in checks:
        mark = "OK  " if c.ok else "FAIL"
        crit = " [critical]" if c.critical else ""
        print(f"{mark}{crit} {c.check_id}: {c.message}")
    return 1 if any_critical_failed(checks) else 0


def main() -> None:
    raise SystemExit(run(build_parser().parse_args()))


if __name__ == "__main__":
    main()
