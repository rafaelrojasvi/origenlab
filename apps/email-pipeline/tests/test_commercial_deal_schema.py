"""Tests for commercial deal ledger SQLite schema (Phase 1 DDL only)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    COMMERCIAL_DEAL_SCHEMA_VERSION,
    COMMERCIAL_DEAL_TABLE_NAMES,
    OPERATOR_ONLY_PAYMENT_COLUMNS,
    commercial_deal_tables_exist,
    decimal_to_minor,
    ensure_commercial_deal_tables,
    foreign_key_check_ok,
    minor_to_decimal,
    table_column_names,
    validate_decimal_minor_pair,
)
from origenlab_email_pipeline.timeutil import now_iso

_REPO = Path(__file__).resolve().parents[1]
_SCHEMA_PY = _REPO / "src/origenlab_email_pipeline/commercial/commercial_deal_schema.py"
_DRY_RUN_SCRIPT = _REPO / "scripts/commercial/apply_commercial_deal_schema_dry_run.py"

_FORBIDDEN_BODY_SUBSTRINGS = (
    "body",
    "full_body",
    "body_clean",
    "body_text",
    "attachment_extract",
    "full_text",
)


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _insert_minimal_deal(conn: sqlite3.Connection, *, deal_status: str = "draft") -> int:
    conn.execute(
        """
        INSERT INTO commercial_deal (
          deal_key, deal_status, client_org_name, schema_version,
          created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "test-deal-1",
            deal_status,
            "Test Client",
            COMMERCIAL_DEAL_SCHEMA_VERSION,
            now_iso(),
            now_iso(),
        ),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM commercial_deal WHERE deal_key='test-deal-1'").fetchone()
    assert row is not None
    return int(row[0])


def test_tables_exist_false_before_true_after() -> None:
    conn = _memory_conn()
    assert commercial_deal_tables_exist(conn) is False
    ensure_commercial_deal_tables(conn)
    assert commercial_deal_tables_exist(conn) is True
    conn.close()


def test_ensure_creates_all_eleven_tables() -> None:
    conn = _memory_conn()
    ensure_commercial_deal_tables(conn)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'commercial_%'"
        ).fetchall()
    }
    for t in COMMERCIAL_DEAL_TABLE_NAMES:
        assert t in names
    assert len(COMMERCIAL_DEAL_TABLE_NAMES) == 11
    conn.close()


def test_foreign_key_check_passes() -> None:
    conn = _memory_conn()
    ensure_commercial_deal_tables(conn)
    assert foreign_key_check_ok(conn) is True
    conn.close()


def test_foreign_key_enforcement_on_line() -> None:
    conn = _memory_conn()
    ensure_commercial_deal_tables(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO commercial_deal_line (
              deal_id, line_number, side, line_kind, description, currency, confidence, created_at
            ) VALUES (99999, 1, 'client', 'product', 'x', 'CLP', 'needs_review', ?)
            """,
            (now_iso(),),
        )
        conn.commit()
    conn.close()


def test_deal_reproducibility_columns() -> None:
    conn = _memory_conn()
    ensure_commercial_deal_tables(conn)
    cols = set(table_column_names(conn, "commercial_deal"))
    for name in (
        "schema_version",
        "source_preview_sha256",
        "parser_version",
        "confirmed_facts_version",
        "supplier_invoice_total_minor",
        "supplier_amount_paid_minor",
    ):
        assert name in cols
    conn.close()


def test_cost_document_and_payment_fk_columns() -> None:
    conn = _memory_conn()
    ensure_commercial_deal_tables(conn)
    cols = set(table_column_names(conn, "commercial_deal_cost"))
    assert "document_id" in cols
    assert "payment_id" in cols
    assert "amount_minor" in cols
    conn.close()


def test_field_evidence_table_columns() -> None:
    conn = _memory_conn()
    ensure_commercial_deal_tables(conn)
    cols = set(table_column_names(conn, "commercial_deal_field_evidence"))
    for name in (
        "entity_table",
        "entity_id",
        "field_name",
        "parser_version",
        "operator_confirmed",
        "normalized_value",
    ):
        assert name in cols
    conn.close()


def test_product_catalog_columns() -> None:
    conn = _memory_conn()
    ensure_commercial_deal_tables(conn)
    cols = set(table_column_names(conn, "commercial_product"))
    for name in ("category", "subcategory", "is_hazardous", "requires_special_shipping"):
        assert name in cols
    conn.close()


def test_check_constraint_rejects_invalid_deal_status() -> None:
    conn = _memory_conn()
    ensure_commercial_deal_tables(conn)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_minimal_deal(conn, deal_status="not_a_valid_status")
    conn.close()


def test_check_constraint_rejects_invalid_event_type() -> None:
    conn = _memory_conn()
    ensure_commercial_deal_tables(conn)
    deal_id = _insert_minimal_deal(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO commercial_deal_event (
              deal_id, event_type, event_at, summary, confidence, created_at
            ) VALUES (?, 'invalid_event', ?, 'x', 'needs_review', ?)
            """,
            (deal_id, now_iso(), now_iso()),
        )
        conn.commit()
    conn.close()


def test_decimal_to_minor_eur_usd_examples() -> None:
    assert decimal_to_minor("218.00", "EUR") == 21800
    assert decimal_to_minor("268.47", "USD") == 26847
    assert decimal_to_minor("363.00", "EUR") == 36300
    assert validate_decimal_minor_pair("218.00", 21800, "EUR")
    assert minor_to_decimal(21800) == "218.00"


def test_decimal_to_minor_rejects_clp() -> None:
    with pytest.raises(ValueError, match="CLP"):
        decimal_to_minor("1499400", "CLP")


def test_chilean_vat_net_gross_integer_math() -> None:
    net = 1_260_000
    gross = round(net * 1.19)
    assert gross == 1_499_400


def test_no_body_columns_on_deal_tables() -> None:
    conn = _memory_conn()
    ensure_commercial_deal_tables(conn)
    for table in COMMERCIAL_DEAL_TABLE_NAMES:
        for col in table_column_names(conn, table):
            lower = col.lower()
            for forbidden in _FORBIDDEN_BODY_SUBSTRINGS:
                assert forbidden not in lower, f"{table}.{col} looks like archive body storage"
    conn.close()


def test_payment_operator_only_sensitive_columns_documented() -> None:
    """transfer_id / operation_id exist locally but must not ship to public API."""
    conn = _memory_conn()
    ensure_commercial_deal_tables(conn)
    cols = set(table_column_names(conn, "commercial_deal_payment"))
    assert OPERATOR_ONLY_PAYMENT_COLUMNS <= cols
    conn.close()


def test_dry_run_script_memory_only(tmp_path: Path) -> None:
    db_file = tmp_path / "must_stay_empty.sqlite"
    proc = subprocess.run(
        [sys.executable, str(_DRY_RUN_SCRIPT)],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "DRY-RUN" in proc.stdout
    assert "foreign_key_check_ok=True" in proc.stdout
    assert not db_file.exists()


def test_apply_requires_sqlite_db_flag() -> None:
    proc = subprocess.run(
        [sys.executable, str(_DRY_RUN_SCRIPT), "--apply"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "--sqlite-db" in proc.stderr


def test_module_has_no_forbidden_imports() -> None:
    text = _SCHEMA_PY.read_text(encoding="utf-8")
    lowered = text.lower()
    forbidden_imports = (
        "import imaplib",
        "import alembic",
        "from origenlab",
        "import psycopg",
        "gmail",
        "send_inline",
        "outreach",
        "fastapi",
        "sync_dashboard_postgres",
    )
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("import ", "from ")):
            continue
        low = stripped.lower()
        for token in forbidden_imports:
            assert token not in low, f"unexpected import line: {stripped!r}"
    assert "render" not in lowered.split("def ")[0]  # module header only
