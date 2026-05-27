"""Tests for build_catalog_sqlite (Phase 8B)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.catalog.catalog_builder import build_catalog_from_seed_file
from origenlab_email_pipeline.catalog.catalog_schema import catalog_tables_exist, ensure_catalog_tables
from origenlab_email_pipeline.catalog.catalog_seed import default_seed_path

_REPO = Path(__file__).resolve().parents[1]
_SEED = default_seed_path(_REPO)
_SCRIPT = _REPO / "scripts" / "catalog" / "build_catalog_sqlite.py"


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def test_builder_dry_run_does_not_create_tables_on_disk(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite"
    conn = sqlite3.connect(str(db))
    conn.close()
    summary = build_catalog_from_seed_file(sqlite3.connect(":memory:"), _SEED, dry_run=True)
    assert summary.dry_run is True
    assert summary.products == 9
    conn2 = sqlite3.connect(str(db))
    try:
        assert catalog_tables_exist(conn2) is False
    finally:
        conn2.close()


def test_builder_creates_tables_and_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        s1 = build_catalog_from_seed_file(conn, _SEED, dry_run=False)
        assert catalog_tables_exist(conn)
        assert s1.products == 9

        counts1 = _table_counts(conn)

        s2 = build_catalog_from_seed_file(conn, _SEED, dry_run=False)
        counts2 = _table_counts(conn)
        assert counts1 == counts2
        assert s2.products == 9
    finally:
        conn.close()


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        "catalog_product",
        "catalog_product_alias",
        "catalog_product_category",
        "catalog_product_spec",
        "catalog_supplier_offer",
        "catalog_price_snapshot",
        "catalog_product_commercial_link",
    ]
    return {t: int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in tables}


def test_ika_price_currency_null_in_db(tmp_path: Path) -> None:
    conn = _memory_conn()
    build_catalog_from_seed_file(conn, _SEED, dry_run=False)
    row = conn.execute(
        """
        SELECT ps.currency, ps.amount_decimal, ps.price_notes
        FROM catalog_price_snapshot ps
        JOIN catalog_product p ON p.id = ps.product_id
        WHERE p.product_key = 'ika-rv10-70-vapor-tube'
        """
    ).fetchone()
    assert row is not None
    assert row["currency"] is None
    assert row["amount_decimal"] == "112.00"
    notes = (row["price_notes"] or "").lower()
    assert "ambigu" in notes
    assert "unitario" in notes
    conn.close()


def test_crtop_price_usd_exw_in_db(tmp_path: Path) -> None:
    conn = _memory_conn()
    build_catalog_from_seed_file(conn, _SEED, dry_run=False)
    row = conn.execute(
        """
        SELECT ps.currency, ps.amount_decimal, ps.amount_minor, ps.incoterm, ps.is_public_safe
        FROM catalog_price_snapshot ps
        JOIN catalog_product p ON p.id = ps.product_id
        WHERE p.product_key = 'crtop-olt-hp-5l'
        """
    ).fetchone()
    assert row is not None
    assert row["currency"] == "USD"
    assert row["amount_decimal"] == "10600.00"
    assert row["amount_minor"] == 1060000
    assert row["incoterm"] == "EXW"
    assert row["is_public_safe"] == 0
    conn.close()


def test_serva_aliases_normalized_distinct(tmp_path: Path) -> None:
    conn = _memory_conn()
    build_catalog_from_seed_file(conn, _SEED, dry_run=False)
    rows = conn.execute(
        """
        SELECT a.alias_code FROM catalog_product_alias a
        JOIN catalog_product p ON p.id = a.product_id
        WHERE p.product_key = 'serva-blueslick-250ml'
        ORDER BY a.alias_code
        """
    ).fetchall()
    codes = [r[0] for r in rows]
    assert codes == ["004250001", "42500", "4250001"]
    conn.close()


def test_commercial_links_no_orphans(tmp_path: Path) -> None:
    conn = _memory_conn()
    build_catalog_from_seed_file(conn, _SEED, dry_run=False)
    orphan = conn.execute(
        """
        SELECT COUNT(*) FROM catalog_product_commercial_link l
        LEFT JOIN catalog_product p ON p.id = l.product_id
        WHERE p.id IS NULL
        """
    ).fetchone()[0]
    assert orphan == 0
    conn.close()


def test_cli_dry_run_exit_zero() -> None:
    cp = subprocess.run(
        [sys.executable, str(_SCRIPT), "--dry-run"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert cp.returncode == 0, cp.stderr
    assert "DRY-RUN" in cp.stdout
    assert "products: 9" in cp.stdout
