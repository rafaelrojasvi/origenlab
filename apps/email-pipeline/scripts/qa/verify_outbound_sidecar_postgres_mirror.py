#!/usr/bin/env python3
"""Verify SQLite outbound sidecars match Postgres outbound.* mirror (fail-closed)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from origenlab_email_pipeline.mart_core_postgres_migrate import (
    connect_sqlite_readonly,
    resolve_postgres_url,
    resolve_sqlite_path,
)
from origenlab_email_pipeline.outbound_sidecar_mirror_verify import (
    compare_outbound_sidecar_mirror,
    count_contacted_exact_csv_rows,
    postgres_lead_research_segment_counts,
    postgres_outbound_sidecar_counts,
    sqlite_lead_research_mirror_segment_counts,
    sqlite_lead_research_segment_counts_raw,
    sqlite_outbound_sidecar_counts,
)


def default_contacted_exact_csv(repo_root: Path) -> Path:
    return (
        repo_root
        / "reports"
        / "out"
        / "active"
        / "current"
        / "contacted_exact_emails_for_exclusion.csv"
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite-db", type=Path, default=None)
    p.add_argument("--postgres-url", default=None)
    p.add_argument(
        "--contacted-exact-csv",
        type=Path,
        default=None,
        help="Optional contacted_exact_emails_for_exclusion.csv for row-count reporting",
    )
    p.add_argument(
        "--include-lead-research",
        action="store_true",
        help="Also verify lead_intel blocked / net_new_safe segment counts",
    )
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args()

    try:
        import psycopg
    except ImportError:
        print("ERROR: psycopg required (uv sync --group postgres)", file=sys.stderr)
        return 2

    sqlite_path = resolve_sqlite_path(args.sqlite_db)
    pg_url = resolve_postgres_url(args.postgres_url)
    contacted_csv = args.contacted_exact_csv
    if contacted_csv is None:
        contacted_csv = default_contacted_exact_csv(REPO)

    conn = connect_sqlite_readonly(sqlite_path)
    try:
        sqlite_counts = sqlite_outbound_sidecar_counts(conn)
        sqlite_lead = None
        sqlite_lead_raw = None
        if args.include_lead_research:
            sqlite_lead = sqlite_lead_research_mirror_segment_counts(conn)
            sqlite_lead_raw = sqlite_lead_research_segment_counts_raw(conn)
    finally:
        conn.close()

    contacted_exact_csv_count = count_contacted_exact_csv_rows(contacted_csv)

    with psycopg.connect(pg_url) as pg_conn:
        with pg_conn.cursor() as cur:
            postgres_counts = postgres_outbound_sidecar_counts(cur)
            postgres_lead = (
                postgres_lead_research_segment_counts(cur)
                if args.include_lead_research
                else None
            )

    report = compare_outbound_sidecar_mirror(
        sqlite_counts,
        postgres_counts,
        include_lead_research=args.include_lead_research,
        sqlite_lead=sqlite_lead,
        postgres_lead=postgres_lead,
        sqlite_lead_raw=sqlite_lead_raw,
        contacted_exact_csv_count=contacted_exact_csv_count,
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if not report["ok"]:
        print(
            "ERROR: Outbound sidecar Postgres mirror is stale — "
            "run sqlite_outbound_sidecars_to_postgres.py --replace",
            file=sys.stderr,
        )
        for err in report["errors"]:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "Outbound sidecar mirror OK: "
        f"email_suppressions={sqlite_counts['email_suppression_total']} "
        f"bounce={sqlite_counts['bounce_suppressions']} "
        f"contacted_sidecar_distinct={sqlite_counts['contacted_sidecar_distinct_emails']}",
    )
    if contacted_exact_csv_count is not None:
        print(f"  contacted_exact_csv_rows (SQLite artifact): {contacted_exact_csv_count}")
    if args.include_lead_research and sqlite_lead:
        print(
            f"  lead_blocked={sqlite_lead['lead_blocked']} "
            f"lead_net_new_safe={sqlite_lead['lead_net_new_safe']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
