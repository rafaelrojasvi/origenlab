"""Supplier schema DDL smoke tests."""

from __future__ import annotations

import sqlite3

from origenlab_email_pipeline.supplier_schema import ensure_supplier_tables


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def test_ensure_supplier_tables_creates_all() -> None:
    conn = _conn()
    ensure_supplier_tables(conn)
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'supplier_%'"
        )
    }
    assert names >= {
        "supplier_import_batch",
        "supplier_master",
        "supplier_evidence",
        "supplier_contact_channel",
        "supplier_priority_snapshot",
        "supplier_review_state",
    }
