"""Load canonical Gmail classification snapshot into Postgres (read-only SQLite)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.email_classification_qa import (
    classify_email_row,
    qa_operational_internal_domains,
    spanish_heuristic_bucket_label,
)
from origenlab_email_pipeline.marketing_supplier_domains import supplier_email_domains
from origenlab_email_pipeline.mart_core_postgres_migrate import connect_sqlite_readonly
from origenlab_email_pipeline.canonical_operational_sql import (
    load_canonical_gmail_classification_sample,
)

try:
    import psycopg
    from psycopg.types.json import Json
except ImportError as exc:  # pragma: no cover
    psycopg = None  # type: ignore[misc, assignment]
    Json = None  # type: ignore[misc, assignment]
    _PSYCOPG_IMPORT_ERROR = exc
else:
    _PSYCOPG_IMPORT_ERROR = None

CLASSIFICATION_TABLE = ("reporting", "email_classification_canonical")
DEFAULT_CLASSIFICATION_DAYS = 180
DEFAULT_CLASSIFICATION_LIMIT = 5000


def _require_psycopg() -> None:
    if psycopg is None:
        raise RuntimeError(
            f"psycopg is required (uv sync --group postgres). ({_PSYCOPG_IMPORT_ERROR})"
        )


def pg_table_exists(cur: Any, *, schema: str, table: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        LIMIT 1
        """,
        (schema, table),
    )
    return cur.fetchone() is not None


def build_classification_rows(
    sqlite_path: Path,
    *,
    days: int = DEFAULT_CLASSIFICATION_DAYS,
    limit: int = DEFAULT_CLASSIFICATION_LIMIT,
) -> list[dict[str, Any]]:
    """Classify recent canonical Gmail rows (heuristic QA, not CRM truth)."""
    conn = connect_sqlite_readonly(sqlite_path)
    try:
        supplier_domains = supplier_email_domains(conn)
        internal = qa_operational_internal_domains()
        raw_rows = load_canonical_gmail_classification_sample(conn, days=days, limit=limit)
    finally:
        conn.close()

    out: list[dict[str, Any]] = []
    for row in raw_rows:
        rc = classify_email_row(
            folder=row.get("folder"),
            subject=row.get("subject"),
            sender=row.get("sender"),
            recipients=row.get("recipients"),
            body=row.get("body"),
            full_body_clean=row.get("full_body_clean"),
            top_reply_clean=row.get("top_reply_clean"),
            doc_types_csv=row.get("doc_types"),
            supplier_domains=supplier_domains,
            internal_domains_lower=internal,
        )
        evidence = "; ".join(rc.evidence[:6])
        out.append(
            {
                "email_id": int(row["id"]),
                "date_iso": row.get("date_iso"),
                "folder": row.get("folder"),
                "from_addr": row.get("sender"),
                "to_addrs": row.get("recipients"),
                "subject": row.get("subject"),
                "predicted_label": rc.primary,
                "categories_json": rc.categories,
                "confidence": rc.confidence,
                "ambiguous": rc.ambiguous,
                "recommended_action": rc.recommended_action,
                "etiqueta_ui": spanish_heuristic_bucket_label(rc.primary),
                "evidence": evidence or None,
                "source_scope": "canonical",
            }
        )
    return out


def sync_email_classification_canonical(
    pg_url: str,
    sqlite_path: Path,
    *,
    sync_run_id: int | None = None,
    days: int = DEFAULT_CLASSIFICATION_DAYS,
    limit: int = DEFAULT_CLASSIFICATION_LIMIT,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Replace reporting.email_classification_canonical from SQLite heuristics."""
    _require_psycopg()
    assert psycopg is not None and Json is not None
    schema, table = CLASSIFICATION_TABLE
    rows = build_classification_rows(sqlite_path, days=days, limit=limit)
    result: dict[str, Any] = {
        "table": f"{schema}.{table}",
        "rows_built": len(rows),
        "rows_written": 0,
        "skipped": False,
        "sync_run_id": sync_run_id,
    }
    if dry_run:
        result["skipped"] = True
        return result

    synced_at = datetime.now(timezone.utc)
    with psycopg.connect(pg_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            if not pg_table_exists(cur, schema=schema, table=table):
                result["skipped"] = True
                result["reason"] = "table_missing"
                return result
            cur.execute(f"DELETE FROM {schema}.{table}")
            if rows:
                cur.executemany(
                    f"""
                    INSERT INTO {schema}.{table} (
                      email_id, sync_run_id, date_iso, folder, from_addr, to_addrs, subject,
                      predicted_label, categories_json, confidence, ambiguous,
                      recommended_action, etiqueta_ui, evidence, source_scope, synced_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s, %s
                    )
                    """,
                    [
                        (
                            r["email_id"],
                            sync_run_id,
                            r["date_iso"],
                            r["folder"],
                            r["from_addr"],
                            r["to_addrs"],
                            r["subject"],
                            r["predicted_label"],
                            Json(r["categories_json"]),
                            r["confidence"],
                            r["ambiguous"],
                            r["recommended_action"],
                            r["etiqueta_ui"],
                            r["evidence"],
                            r["source_scope"],
                            synced_at,
                        )
                        for r in rows
                    ],
                )
        conn.commit()
    result["rows_written"] = len(rows)
    return result
