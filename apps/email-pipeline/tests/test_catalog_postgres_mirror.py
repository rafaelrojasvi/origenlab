"""Tests for catalog Postgres mirror (Phase 8C)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from origenlab_email_pipeline.catalog.catalog_builder import build_catalog_from_seed_file
from origenlab_email_pipeline.catalog.catalog_mirror_read_model import (
    load_catalog_mirror_payload,
    sqlite_catalog_counts,
)
from origenlab_email_pipeline.catalog.catalog_mirror_safety import (
    CatalogMirrorSafetyError,
    assert_mirror_text_safe,
)
from origenlab_email_pipeline.catalog.catalog_postgres_mirror import (
    sync_catalog_postgres_mirror,
)
from origenlab_email_pipeline.catalog.catalog_seed import default_seed_path

_REPO = Path(__file__).resolve().parents[1]
_SEED = default_seed_path(_REPO)
_MIGRATION = _REPO / "alembic" / "versions" / "20260527_0019_catalog_mirror.py"
_HISTORY_MIGRATION = _REPO / "alembic" / "versions" / "20260528_0020_catalog_product_commercial_history.py"


def _memory_catalog_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    build_catalog_from_seed_file(conn, _SEED, dry_run=False)
    return conn


class _RecordingCursor:
    def __init__(self) -> None:
        self.deletes: list[str] = []
        self.inserts: list[tuple[str, tuple[Any, ...] | None]] = []
        self._fetchone: tuple[Any, ...] | None = (1,)

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        low = sql.lower().strip()
        if "information_schema" in low:
            self._fetchone = (1,)
        elif low.startswith("delete"):
            self.deletes.append(sql)
        elif low.startswith("insert"):
            self.inserts.append((sql, params))
        elif low.startswith("select count"):
            self._fetchone = (0,)

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._fetchone

    def __enter__(self) -> _RecordingCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _RecordingPgConn:
    def __init__(self) -> None:
        self.cur = _RecordingCursor()
        self.committed = False

    def cursor(self) -> _RecordingCursor:
        return self.cur

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> _RecordingPgConn:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_migration_defines_catalog_tables_without_evidence_columns() -> None:
    text = _MIGRATION.read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS catalog" in text
    for table in (
        "catalog.product",
        "catalog.product_alias",
        "catalog.product_category",
        "catalog.product_spec",
        "catalog.supplier_offer",
        "catalog.price_snapshot",
        "catalog.product_commercial_link",
    ):
        assert table in text
    history_text = _HISTORY_MIGRATION.read_text(encoding="utf-8")
    assert "catalog.product_commercial_history" in history_text
    for forbidden in ("evidence_email_id", "transfer_id", "operation_id", "source_file"):
        assert forbidden not in text
        assert forbidden not in history_text


def test_forbidden_bank_term_rejected() -> None:
    with pytest.raises(CatalogMirrorSafetyError, match="forbidden"):
        assert_mirror_text_safe("Pay to bank account", field="test")


def test_load_mirror_payload_counts_match_sqlite(tmp_path: Path) -> None:
    conn = _memory_catalog_db()
    try:
        payload = load_catalog_mirror_payload(conn)
        counts = sqlite_catalog_counts(conn)
        assert len(payload["products"]) == counts["products"] == 9
        assert counts["aliases"] == len(payload["aliases"])
        assert counts["price_snapshots"] == len(payload["price_snapshots"])
    finally:
        conn.close()


def test_mirror_payload_preserves_spanish_prose_spacing() -> None:
    conn = _memory_catalog_db()
    try:
        payload = load_catalog_mirror_payload(conn)
        serva = next(p for p in payload["products"] if p["product_key"] == "serva-blueslick-250ml")
        assert "cotización y disponibilidad" in (serva.get("public_summary") or "")

        ika_offer = next(
            o for o in payload["supplier_offers"] if o["product_key"] == "ika-rv10-70-vapor-tube"
        )
        ika = next(p for p in payload["products"] if p["product_key"] == "ika-rv10-70-vapor-tube")
        assert "por cliente" in (ika.get("public_summary") or "")
        assert "cantidad 3" in (ika.get("public_summary") or "")
        assert "monto es" in (ika_offer.get("availability_note") or "")

        ika_snap = next(
            s for s in payload["price_snapshots"] if s["snapshot_key"] == "ika-rv10-70-price-ambiguous"
        )
        assert "Monto 112,00" in (ika_snap.get("price_notes") or "")

        crtop = next(p for p in payload["products"] if p["product_key"] == "crtop-olt-hp-5l")
        assert "antes de cotizar" in (crtop.get("public_summary") or "")
    finally:
        conn.close()


def test_mirror_payload_repairs_legacy_joined_spacing() -> None:
    conn = _memory_catalog_db()
    try:
        conn.execute(
            """
            UPDATE catalog_product
            SET public_summary = ?
            WHERE product_key = ?
            """,
            (
                "cotizacióny disponibilidad sujetas a confirmación.",
                "serva-blueslick-250ml",
            ),
        )
        conn.commit()
        payload = load_catalog_mirror_payload(conn)
        serva = next(p for p in payload["products"] if p["product_key"] == "serva-blueslick-250ml")
        assert "cotización y disponibilidad" in (serva.get("public_summary") or "")
    finally:
        conn.close()


def test_ika_ambiguous_price_preserved_in_payload() -> None:
    conn = _memory_catalog_db()
    try:
        snaps = load_catalog_mirror_payload(conn)["price_snapshots"]
        ika = next(s for s in snaps if s["snapshot_key"] == "ika-rv10-70-price-ambiguous")
        assert ika["currency"] is None
        assert ika["amount_decimal"] == "112.00"
        notes = (ika.get("price_notes") or "").lower()
        assert "ambigu" in notes
        assert ika["quantity"] == "3"
        assert ika["is_public_safe"] is False
    finally:
        conn.close()


def test_crtop_usd_exw_preserved_in_payload() -> None:
    conn = _memory_catalog_db()
    try:
        snaps = load_catalog_mirror_payload(conn)["price_snapshots"]
        crtop = next(s for s in snaps if s["snapshot_key"] == "crtop-olt-hp-5l-exw-usd")
        assert crtop["currency"] == "USD"
        assert crtop["amount_decimal"] == "10600.00"
        assert crtop["amount_minor"] == 1060000
        assert crtop["incoterm"] == "EXW"
    finally:
        conn.close()


def test_sync_dry_run_writes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    build_catalog_from_seed_file(conn, _SEED, dry_run=False)
    conn.close()

    with patch(
        "origenlab_email_pipeline.catalog.catalog_postgres_mirror.psycopg.connect",
        side_effect=AssertionError("psycopg must not connect on dry-run"),
    ):
        result = sync_catalog_postgres_mirror(
            "postgresql://u:p@127.0.0.1:5432/scratch",
            db,
            dry_run=True,
        )
    assert result["skipped"] is True
    assert result["built_counts"]["products"] == 9
    assert result["written_counts"]["products"] == 0


def test_sync_full_replace_inserts_all_tables(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    build_catalog_from_seed_file(conn, _SEED, dry_run=False)
    conn.close()

    pg = _RecordingPgConn()
    with patch(
        "origenlab_email_pipeline.catalog.catalog_postgres_mirror.psycopg.connect",
        return_value=pg,
    ):
        result = sync_catalog_postgres_mirror(
            "postgresql://u:p@127.0.0.1:5432/scratch",
            db,
            dry_run=False,
        )

    assert result["skipped"] is False
    assert pg.committed is True
    assert len(pg.cur.deletes) == 9
    assert result["written_counts"]["products"] == 9
    assert result["written_counts"]["commercial_history"] == 4
    assert result["written_counts"]["products"] == result["built_counts"]["products"]
    assert result["written_counts"]["price_snapshots"] == result["built_counts"]["price_snapshots"]

    insert_tables = {
        "product": 0,
        "supplier_offer": 0,
        "price_snapshot": 0,
    }
    for sql, _params in pg.cur.inserts:
        low = sql.lower()
        if "into catalog.product (" in low:
            insert_tables["product"] += 1
        elif "into catalog.supplier_offer (" in low:
            insert_tables["supplier_offer"] += 1
        elif "into catalog.price_snapshot (" in low:
            insert_tables["price_snapshot"] += 1

    assert insert_tables["product"] == 9
    assert insert_tables["supplier_offer"] >= 2
    assert insert_tables["price_snapshot"] >= 2

    # Mirror always writes is_public_safe=false to Postgres
    for sql, params in pg.cur.inserts:
        if "catalog.price_snapshot" in sql.lower() and params is not None:
            assert params[-4] is False


def test_sync_idempotent_row_counts_stable(tmp_path: Path) -> None:
    db = tmp_path / "catalog.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    build_catalog_from_seed_file(conn, _SEED, dry_run=False)
    conn.close()

    pg = _RecordingPgConn()
    with patch(
        "origenlab_email_pipeline.catalog.catalog_postgres_mirror.psycopg.connect",
        return_value=pg,
    ):
        r1 = sync_catalog_postgres_mirror("postgresql://u:p@127.0.0.1:5432/x", db, dry_run=False)
        first_inserts = len(pg.cur.inserts)
        pg2 = _RecordingPgConn()
        with patch(
            "origenlab_email_pipeline.catalog.catalog_postgres_mirror.psycopg.connect",
            return_value=pg2,
        ):
            r2 = sync_catalog_postgres_mirror("postgresql://u:p@127.0.0.1:5432/x", db, dry_run=False)
    assert r1["written_counts"] == r2["written_counts"]
    assert first_inserts == len(pg2.cur.inserts)
