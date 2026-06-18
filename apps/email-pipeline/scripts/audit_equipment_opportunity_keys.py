#!/usr/bin/env python3
"""Audit repeated equipment opportunity_key values in Postgres (read-only).

Usage:
  cd apps/email-pipeline
  ORIGENLAB_POSTGRES_URL=... uv run python scripts/audit_equipment_opportunity_keys.py

Exits 0 with a skip message when no Postgres URL is configured.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

SKIP_MESSAGE = (
    "skip: equipment opportunity key audit requires "
    "ORIGENLAB_POSTGRES_URL or ALEMBIC_DATABASE_URL"
)

DEFAULT_LIMIT = 50

AUDIT_SQL = """
SELECT
  opportunity_key,
  row_count,
  source_count,
  canonical_row_count,
  has_canonical,
  last_synced_at,
  codigo_licitacion,
  sample_buyer,
  sample_title,
  sample_equipment_category,
  source_artifacts,
  canonical_reasons
FROM api.v_equipment_opportunity_key_audit
WHERE row_count > 1
ORDER BY row_count DESC, last_synced_at DESC NULLS LAST
LIMIT %(limit)s
"""


def resolve_postgres_url() -> str | None:
    for var in ("ORIGENLAB_POSTGRES_URL", "ALEMBIC_DATABASE_URL"):
        value = (os.environ.get(var) or "").strip()
        if value:
            return value
    return None


def format_audit_row(row: dict[str, Any]) -> str:
    artifacts = row.get("source_artifacts") or []
    if isinstance(artifacts, list):
        artifacts_text = ", ".join(str(x) for x in artifacts if x)
    else:
        artifacts_text = str(artifacts)
    reasons = row.get("canonical_reasons") or []
    if isinstance(reasons, list):
        reasons_text = ", ".join(str(x) for x in reasons if x)
    else:
        reasons_text = str(reasons)
    return (
        f"{row.get('opportunity_key')} "
        f"rows={row.get('row_count')} sources={row.get('source_count')} "
        f"canonical_rows={row.get('canonical_row_count')} has_canonical={row.get('has_canonical')} "
        f"codigo={row.get('codigo_licitacion') or ''} buyer={row.get('sample_buyer') or ''} "
        f"category={row.get('sample_equipment_category') or ''} "
        f"artifacts=[{artifacts_text}] reasons=[{reasons_text}] "
        f"last_synced={row.get('last_synced_at')}"
    )


def format_audit_report(rows: list[dict[str, Any]], *, limit: int) -> str:
    lines = [f"equipment opportunity key audit (repeated keys, limit={limit})"]
    if not rows:
        lines.append("ok: no repeated opportunity_key values found")
        return "\n".join(lines)
    for row in rows:
        lines.append(f"  {format_audit_row(row)}")
    lines.append(f"ok: listed {len(rows)} repeated opportunity_key value(s)")
    return "\n".join(lines)


def fetch_repeated_keys(pg_url: str, *, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    from origenlab_email_pipeline.mart_core_postgres_migrate import normalize_postgres_url

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("psycopg is required (uv sync --group postgres)") from exc

    cap = max(1, int(limit))
    with psycopg.connect(normalize_postgres_url(pg_url)) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(AUDIT_SQL, {"limit": cap})
            return [dict(row) for row in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max repeated keys to list (default {DEFAULT_LIMIT})",
    )
    args = parser.parse_args(argv)

    pg_url = resolve_postgres_url()
    if pg_url is None:
        print(SKIP_MESSAGE)
        return 0

    rows = fetch_repeated_keys(pg_url, limit=args.limit)
    print(format_audit_report(rows, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
