"""Tests for redacted commercial deal Postgres mirror read-model builders."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.commercial.commercial_deal_mirror_read_model import (
    FORBIDDEN_MIRROR_JSON_KEYS,
    assert_mirror_payload_safe,
    build_safe_deal_mirror_row,
    load_all_safe_deal_mirror_rows,
)
from origenlab_email_pipeline.commercial.commercial_deal_promotion import (
    apply_deal_promotion_plan,
    build_serva_ceaf_plan_from_default_preview,
)
from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    ensure_commercial_deal_tables,
)
from origenlab_email_pipeline.commercial.serva_ceaf_deal_confirmed import (
    DEAL_KEY,
)

_REPO = Path(__file__).resolve().parents[1]
_PREVIEW = _REPO / "reports/out/active/current/commercial_deals_preview/serva-ceaf-oc-26172-po-174-26.json"


@pytest.fixture
def serva_db(tmp_path: Path) -> Path:
    if not _PREVIEW.is_file():
        pytest.skip(f"preview fixture missing: {_PREVIEW}")
    db = tmp_path / "ledger.sqlite"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_commercial_deal_tables(conn)
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    apply_deal_promotion_plan(conn, plan)
    conn.close()
    return db


def test_safe_mirror_row_has_allowed_fields_only(serva_db: Path) -> None:
    conn = sqlite3.connect(str(serva_db))
    conn.row_factory = sqlite3.Row
    row = build_safe_deal_mirror_row(conn, DEAL_KEY)
    conn.close()
    assert row is not None
    assert row["deal_key"] == DEAL_KEY
    assert "client_org_name" in row
    assert "margin_notes" not in row
    assert "transfer_id" not in json.dumps(row)
    for key in FORBIDDEN_MIRROR_JSON_KEYS:
        assert key not in json.dumps(row)


def test_product_lines_exclude_ref_code_and_description(serva_db: Path) -> None:
    conn = sqlite3.connect(str(serva_db))
    conn.row_factory = sqlite3.Row
    row = build_safe_deal_mirror_row(conn, DEAL_KEY)
    conn.close()
    assert row is not None
    lines = row["product_line_summaries"]
    assert len(lines) >= 1
    for line in lines:
        assert "ref_code" not in line
        assert "description" not in line
        assert "product_name" in line or line.get("line_kind")


def test_payment_summaries_exclude_transfer_ids(serva_db: Path) -> None:
    conn = sqlite3.connect(str(serva_db))
    conn.row_factory = sqlite3.Row
    row = build_safe_deal_mirror_row(conn, DEAL_KEY)
    conn.close()
    assert row is not None
    payments = row["payment_summaries_masked"]
    assert payments
    blob = json.dumps(payments)
    assert "transfer_id" not in blob
    assert "operation_id" not in blob
    assert "counterparty_email" not in blob


def test_margin_blockers_when_not_computed(serva_db: Path) -> None:
    conn = sqlite3.connect(str(serva_db))
    conn.row_factory = sqlite3.Row
    row = build_safe_deal_mirror_row(conn, DEAL_KEY)
    conn.close()
    assert row is not None
    assert row["margin_status"] != "computed"
    assert isinstance(row["margin_blockers"], list)
    assert len(row["margin_blockers"]) > 0


def test_load_all_safe_rows_count(serva_db: Path) -> None:
    conn = sqlite3.connect(str(serva_db))
    conn.row_factory = sqlite3.Row
    rows = load_all_safe_deal_mirror_rows(conn)
    conn.close()
    assert len(rows) == 1
    assert_mirror_payload_safe(rows[0])
