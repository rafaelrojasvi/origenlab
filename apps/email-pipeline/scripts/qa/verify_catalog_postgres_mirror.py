#!/usr/bin/env python3
"""Verify SQLite catalog_* counts match Postgres catalog.* mirror."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.catalog.catalog_mirror_read_model import (  # noqa: E402
    load_catalog_mirror_payload,
    sqlite_catalog_counts,
)
from origenlab_email_pipeline.catalog.catalog_mirror_safety import (  # noqa: E402
    FORBIDDEN_MIRROR_TEXT_PATTERNS,
    assert_mirror_text_safe,
)
from origenlab_email_pipeline.catalog.catalog_schema import catalog_tables_exist
from origenlab_email_pipeline.catalog.catalog_postgres_mirror import (  # noqa: E402
    pg_catalog_tables_exist,
    postgres_catalog_counts,
)
from origenlab_email_pipeline.mart_core_postgres_migrate import (  # noqa: E402
    connect_sqlite_readonly,
    resolve_postgres_url,
    resolve_sqlite_path,
)


def resolve_verify_sqlite_path(sqlite_db: Path | None) -> Path:
    if sqlite_db is not None:
        return resolve_sqlite_path(sqlite_db)
    env_sqlite = os.environ.get("ORIGENLAB_SQLITE_PATH")
    if env_sqlite:
        return resolve_sqlite_path(Path(env_sqlite))
    return resolve_sqlite_path(None)


_TEXT_COLUMNS_BY_TABLE: dict[str, tuple[str, ...]] = {
    "product": (
        "display_name",
        "brand",
        "manufacturer_name",
        "public_summary",
        "website_slug",
    ),
    "product_category": ("display_name",),
    "product_alias": ("alias_code", "alias_source"),
    "product_spec": ("spec_value", "spec_key"),
    "supplier_offer": (
        "supplier_org_name",
        "payment_terms",
        "delivery_terms",
        "availability_note",
    ),
    "price_snapshot": ("price_notes", "amount_decimal"),
    "product_commercial_link": ("link_ref",),
    "product_commercial_history": (
        "deal_label",
        "source_summary",
        "client_org_name",
        "supplier_org_name",
        "amount_decimal",
    ),
}


def _scan_postgres_text_fields(cur, *, schema: str = "catalog") -> list[str]:
    errors: list[str] = []
    for table, columns in _TEXT_COLUMNS_BY_TABLE.items():
        for col in columns:
            cur.execute(f"SELECT {col} FROM {schema}.{table} WHERE {col} IS NOT NULL")
            for (value,) in cur.fetchall():
                try:
                    assert_mirror_text_safe(str(value), field=f"{schema}.{table}.{col}")
                except ValueError as exc:
                    errors.append(str(exc))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-db", type=Path, default=None)
    parser.add_argument("--postgres-url", default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument(
        "--scan-text",
        action="store_true",
        help="Fail if forbidden terms appear in Postgres text columns",
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
    sqlite_conn.row_factory = __import__("sqlite3").Row
    has_sqlite_catalog = False
    try:
        has_sqlite_catalog = catalog_tables_exist(sqlite_conn)
        sqlite_counts = sqlite_catalog_counts(sqlite_conn)
        if has_sqlite_catalog:
            load_catalog_mirror_payload(sqlite_conn)
    finally:
        sqlite_conn.close()

    failures: list[str] = []
    if not has_sqlite_catalog:
        failures.append("SQLite catalog_* tables missing — run build_catalog_sqlite.py")

    pg_counts: dict[str, int] = {}
    with psycopg.connect(pg_url) as conn:
        with conn.cursor() as cur:
            if not pg_catalog_tables_exist(cur):
                failures.append("Postgres catalog.product missing (run alembic upgrade head)")
            else:
                pg_counts = postgres_catalog_counts(pg_url)
                if args.scan_text:
                    failures.extend(_scan_postgres_text_fields(cur))

    for key in sqlite_counts:
        if key in pg_counts and sqlite_counts[key] != pg_counts[key]:
            failures.append(
                f"count mismatch {key}: sqlite={sqlite_counts[key]} postgres={pg_counts[key]}"
            )

    out: dict[str, object] = {
        "sqlite_path": str(sqlite_path),
        "postgres_url_redacted": pg_url.split("@")[-1] if "@" in pg_url else pg_url,
        "sqlite_counts": sqlite_counts,
        "postgres_counts": pg_counts,
        "forbidden_patterns": [p.pattern for p in FORBIDDEN_MIRROR_TEXT_PATTERNS],
        "ok": len(failures) == 0,
        "failures": failures,
    }

    text = json.dumps(out, indent=2, default=str)
    print(text)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
