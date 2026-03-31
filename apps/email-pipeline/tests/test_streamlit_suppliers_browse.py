"""Streamlit supplier browse helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from openpyxl import Workbook

from origenlab_email_pipeline.business_mart_schema import BUSINESS_MART_SCHEMA_SQL
from origenlab_email_pipeline.streamlit_suppliers_browse import (
    SupplierBrowseFilters,
    build_suppliers_browse_sql,
    fetch_suppliers_browse_df,
    supplier_browse_filter_options,
    supplier_browse_ready,
)
from origenlab_email_pipeline.supplier_schema import ensure_supplier_tables
from origenlab_email_pipeline.supplier_workbook import import_supplier_workbook


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def test_supplier_browse_ready_missing_table() -> None:
    conn = _conn()
    ok, reason = supplier_browse_ready(conn)
    assert ok is False
    assert reason == "missing_supplier_master"


def test_fetch_suppliers_empty_without_tables() -> None:
    conn = _conn()
    df = fetch_suppliers_browse_df(conn)
    assert df.empty


def test_build_suppliers_browse_sql_shape() -> None:
    sql, args = build_suppliers_browse_sql(
        SupplierBrowseFilters(limit=10),
        include_mailbox_join=False,
    )
    assert "supplier_master sm" in sql
    assert "supplier_priority_snapshot sps" in sql
    assert args == [10]


def test_fetch_after_import_and_mailbox_join(tmp_path: Path) -> None:
    p = tmp_path / "s.xlsx"
    wb = Workbook()
    wb.active.title = "Resumen"
    wb.active.append(["a", "b"])
    sheets = [
        ("Oportunidades_50", [["Dominio", "Empresa", "Región", "Ranking"], ["mail.org", "M", "EU", 1]]),
        ("Contacto_15", [["Dominio"], ["mail.org"]]),
        ("Evidencias", [["Dominio", "URL"], ["mail.org", "https://mail.org/e"]]),
        ("Prioridades", [["c"], [1]]),
        ("Exclusiones", [["Dominio"], ["x.com"]]),
        ("Anexo_CSV_NoRepetido", [["Dominio"], ["y.org"]]),
    ]
    for title, rows in sheets:
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    wb.save(p)

    conn = _conn()
    conn.executescript(BUSINESS_MART_SCHEMA_SQL)
    conn.execute(
        "INSERT INTO organization_master (domain, organization_name_guess) VALUES (?, ?)",
        ("mail.org", "Mail Org Archive"),
    )
    ensure_supplier_tables(conn)
    import_supplier_workbook(conn, p)

    opts = supplier_browse_filter_options(conn)
    assert "region" in opts
    df = fetch_suppliers_browse_df(conn, SupplierBrowseFilters(limit=100),
                                    include_mailbox_join=True)
    assert not df.empty
    row = df[df["domain_norm"] == "mail.org"].iloc[0]
    assert int(row["seen_in_mailbox"]) == 1
