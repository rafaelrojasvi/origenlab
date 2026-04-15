from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.commercial.commercial_intel_schema import ensure_commercial_intel_tables
from origenlab_email_pipeline.db import connect, init_schema
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def test_commercial_schema_create_idempotent(tmp_path) -> None:
    db = tmp_path / "emails.sqlite"
    conn = connect(db)
    try:
        init_schema(conn)
        ensure_commercial_intel_tables(conn)
        # run again to assert idempotence
        ensure_commercial_intel_tables(conn)

        assert _table_exists(conn, "commercial_email_signal_fact")
        assert _table_exists(conn, "commercial_org_signal_rollup")
        assert _table_exists(conn, "commercial_contact_signal_rollup")
        assert _table_exists(conn, "commercial_opportunity_fact")
        assert _table_exists(conn, "organization_candidate")
        assert _table_exists(conn, "contact_candidate")
        assert _table_exists(conn, "opportunity_candidate")
        assert _table_exists(conn, "candidate_review_event")
        assert _table_exists(conn, "candidate_manual_override")
        assert _table_exists(conn, "v_commercial_candidate_queue")
        sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='view' AND name='v_commercial_candidate_queue'"
        ).fetchone()
        assert sql_row and "reason_summary" in sql_row[0]
    finally:
        conn.close()


def test_sqlite_migrate_can_apply_commercial_layer_only(tmp_path) -> None:
    db = tmp_path / "emails.sqlite"
    conn = connect(db)
    try:
        migrate_sqlite_schema(
            conn,
            layers={SchemaLayer.ARCHIVE_AND_MART, SchemaLayer.COMMERCIAL_INTEL},
        )
        assert _table_exists(conn, "emails")
        assert _table_exists(conn, "commercial_email_signal_fact")
        assert _table_exists(conn, "organization_candidate")
    finally:
        conn.close()

