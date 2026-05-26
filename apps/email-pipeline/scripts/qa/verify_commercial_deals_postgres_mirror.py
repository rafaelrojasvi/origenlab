#!/usr/bin/env python3
"""Verify SQLite commercial_deal count matches Postgres commercial.deal mirror."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.commercial.commercial_deal_mirror_read_model import (  # noqa: E402
    FORBIDDEN_MIRROR_JSON_KEYS,
    assert_mirror_payload_safe,
)
from origenlab_email_pipeline.commercial.commercial_deal_schema import (  # noqa: E402
    commercial_deal_tables_exist,
)
from origenlab_email_pipeline.mart_core_postgres_migrate import (  # noqa: E402
    connect_sqlite_readonly,
    resolve_postgres_url,
    resolve_sqlite_path,
)


def resolve_verify_sqlite_path(sqlite_db: Path | None) -> Path:
    """Resolve SQLite path for verify CLI (Path args + ORIGENLAB_SQLITE_PATH env string)."""
    sqlite_arg = sqlite_db
    if sqlite_arg is None:
        env_sqlite = os.environ.get("ORIGENLAB_SQLITE_PATH")
        sqlite_arg = Path(env_sqlite) if env_sqlite else None
    return resolve_sqlite_path(sqlite_arg)


def _scan_jsonb_forbidden(cur, schema: str, table: str) -> list[str]:
    errors: list[str] = []
    cols = (
        "product_line_summaries",
        "cost_summaries_by_type",
        "payment_summaries_masked",
        "margin_blockers",
    )
    for col in cols:
        cur.execute(
            f"""
            SELECT deal_key, {col}
            FROM {schema}.{table}
            """,
        )
        for deal_key, payload in cur.fetchall():
            try:
                assert_mirror_payload_safe(payload)
            except ValueError as exc:
                errors.append(f"{deal_key}.{col}: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-db", type=Path, default=None)
    parser.add_argument("--postgres-url", default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument(
        "--scan-jsonb",
        action="store_true",
        help="Fail if forbidden keys appear in JSONB columns",
    )
    args = parser.parse_args()

    try:
        import psycopg
    except ImportError:
        print("ERROR: psycopg missing — run: uv sync --group dev", file=sys.stderr)
        return 2

    sqlite_path = resolve_verify_sqlite_path(args.sqlite_db)
    pg_url = resolve_postgres_url(args.postgres_url or os.environ.get("ORIGENLAB_POSTGRES_URL"))

    sqlite_conn = connect_sqlite_readonly(sqlite_path)
    try:
        if not commercial_deal_tables_exist(sqlite_conn):
            sqlite_count = 0
            sqlite_note = "commercial_deal tables missing in SQLite"
        else:
            row = sqlite_conn.execute("SELECT COUNT(*) FROM commercial_deal").fetchone()
            sqlite_count = int(row[0] if row else 0)
            sqlite_note = ""
    finally:
        sqlite_conn.close()

    out: dict[str, object] = {
        "sqlite_path": str(sqlite_path),
        "postgres_url_redacted": pg_url.split("@")[-1] if "@" in pg_url else pg_url,
        "sqlite_deal_count": sqlite_count,
        "postgres_deal_count": None,
        "forbidden_keys_checked": sorted(FORBIDDEN_MIRROR_JSON_KEYS),
    }
    failures: list[str] = []

    if sqlite_note:
        failures.append(sqlite_note)

    with psycopg.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'commercial' AND table_name = 'deal'
                """,
            )
            if not cur.fetchone():
                failures.append("Postgres table commercial.deal missing (run alembic upgrade head)")
                pg_count = None
            else:
                cur.execute("SELECT COUNT(*)::bigint FROM commercial.deal")
                pg_count = int(cur.fetchone()[0])
                out["postgres_deal_count"] = pg_count
                if pg_count != sqlite_count:
                    failures.append(
                        f"count mismatch: sqlite={sqlite_count} postgres={pg_count}"
                    )
                if args.scan_jsonb:
                    jsonb_errors = _scan_jsonb_forbidden(cur, "commercial", "deal")
                    if jsonb_errors:
                        failures.extend(jsonb_errors)
                        out["jsonb_scan_errors"] = jsonb_errors

    out["passed"] = not failures
    out["failures"] = failures
    text = json.dumps(out, indent=2, default=str)
    print(text)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")

    if failures:
        print("VERIFY FAILED:", file=sys.stderr)
        for msg in failures:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    print("VERIFY OK: commercial deal mirror counts match.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
