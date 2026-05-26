"""Tests for commercial deal promotion dry-run planner (Phase 2)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.commercial.commercial_deal_promotion import (
    APPLY_NOT_IMPLEMENTED_MSG,
    build_plan_for_deal_key,
    build_serva_ceaf_plan_from_default_preview,
    default_preview_path,
    iter_plan_entity_rows,
    plan_contains_forbidden_columns,
    validate_apply_args,
)
from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    ensure_commercial_deal_tables,
)
from origenlab_email_pipeline.commercial.serva_ceaf_deal_confirmed import (
    DEAL_KEY,
    SUPPLIER_AMOUNT_PAID_EUR,
    SUPPLIER_FREIGHT_QUOTED_EUR,
    SUPPLIER_INVOICE_TOTAL_EUR,
)
from origenlab_email_pipeline.timeutil import now_iso

_REPO = Path(__file__).resolve().parents[1]
_PREVIEW = _REPO / "reports/out/active/current/commercial_deals_preview/serva-ceaf-oc-26172-po-174-26.json"
_SCRIPT = _REPO / "scripts/commercial/promote_deal_from_preview.py"

_ENTITY_GROUPS = (
    "commercial_deal",
    "commercial_deal_line",
    "commercial_deal_cost",
    "commercial_deal_payment",
    "commercial_deal_document",
    "commercial_deal_event",
    "commercial_deal_evidence",
    "commercial_deal_field_evidence",
    "commercial_deal_review",
    "commercial_product",
    "commercial_product_alias",
)


@pytest.fixture
def serva_preview_exists() -> None:
    if not _PREVIEW.is_file():
        pytest.skip(f"preview fixture missing: {_PREVIEW}")


def test_dry_run_includes_all_entity_groups(serva_preview_exists: None) -> None:
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    data = plan.to_dict()
    for key in _ENTITY_GROUPS:
        assert key in data, f"missing entity group {key}"
        if key in ("commercial_deal", "commercial_deal_review"):
            assert data[key] is not None
        else:
            assert len(data[key]) > 0, f"empty entity group {key}"


def test_minor_units_and_vat(serva_preview_exists: None) -> None:
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    deal_cols = plan.commercial_deal["columns"]
    assert deal_cols["client_sale_net_clp"] == 1_260_000
    assert deal_cols["client_iva_amount_clp"] == 239_400
    assert deal_cols["client_sale_gross_clp"] == 1_499_400
    assert deal_cols["client_payment_received_clp"] == 1_499_400
    assert deal_cols["supplier_invoice_total_minor"] == 36300
    assert deal_cols["supplier_amount_paid_minor"] == 21800
    assert deal_cols["supplier_invoice_total_decimal"] == "363.00"
    assert deal_cols["supplier_amount_paid_decimal"] == "218.00"

    outbound = next(
        r for r in plan.commercial_deal_payment if r["columns"]["direction"] == "outbound"
    )
    assert outbound["columns"]["amount_minor"] == 21800
    assert outbound["columns"]["secondary_amount_minor"] == 26847


def test_reconciliation_363_minus_145_equals_218(serva_preview_exists: None) -> None:
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    rec = plan.reconciliation
    assert rec["supplier_invoice_total_eur"] == str(SUPPLIER_INVOICE_TOTAL_EUR)
    assert rec["supplier_freight_quoted_eur"] == str(SUPPLIER_FREIGHT_QUOTED_EUR)
    assert rec["supplier_amount_paid_eur"] == str(SUPPLIER_AMOUNT_PAID_EUR)
    assert rec["expected_payment_excluding_freight_eur"] == "218.00"
    assert rec.get("freight_excluded_from_wire") is True


def test_margin_needs_review(serva_preview_exists: None) -> None:
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    assert plan.commercial_deal["columns"]["margin_status"] == "needs_review"
    assert plan.gross_margin.get("status") == "needs_review" or plan.gross_margin.get("margin_status")


def test_field_evidence_for_key_money_fields(serva_preview_exists: None) -> None:
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    fields = {r["columns"]["field_name"] for r in plan.commercial_deal_field_evidence}
    for expected in (
        "client_sale_net_clp",
        "client_iva_amount_clp",
        "client_sale_gross_clp",
        "client_payment_received_clp",
        "supplier_invoice_total_decimal",
        "supplier_amount_paid_decimal",
        "reconciliation_status",
    ):
        assert expected in fields


def test_plan_has_no_body_columns(serva_preview_exists: None) -> None:
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    forbidden = plan_contains_forbidden_columns(plan.to_dict())
    assert forbidden == []


def test_idempotency_keys_present(serva_preview_exists: None) -> None:
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    assert plan.commercial_deal["upsert_key"] == {"deal_key": DEAL_KEY}
    assert plan.commercial_product[0]["upsert_key"] == {"ref_code": "004250001"}
    alias = plan.commercial_product_alias[0]
    assert set(alias["upsert_key"]) == {"alias_source", "alias_code"}
    line = plan.commercial_deal_line[0]
    assert line["upsert_key"] == {"deal_key": DEAL_KEY, "side": "client", "line_number": 1}


def test_existing_deal_sets_update_action(serva_preview_exists: None, tmp_path: Path) -> None:
    db = tmp_path / "ledger.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_commercial_deal_tables(conn)
    conn.execute(
        """
        INSERT INTO commercial_deal (
          deal_key, deal_status, client_org_name, schema_version, created_at, updated_at
        ) VALUES (?, 'draft', 'CEAF', '1.1.0', ?, ?)
        """,
        (DEAL_KEY, now_iso(), now_iso()),
    )
    conn.commit()
    plan = build_plan_for_deal_key(DEAL_KEY, pipeline_root=_REPO, conn=conn)
    conn.close()
    assert plan.deal_action == "update"
    assert plan.idempotency.get("existing_deal_id") is not None


def test_default_mode_no_sqlite_writes(tmp_path: Path, serva_preview_exists: None) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(str(db))
    ensure_commercial_deal_tables(conn)
    conn.commit()
    conn.close()

    before = db.stat().st_mtime_ns
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--deal-key",
            DEAL_KEY,
            "--sqlite-db",
            str(db),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert "DRY-RUN" in r.stdout

    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT COUNT(*) FROM commercial_deal").fetchone()[0]
    conn.close()
    assert count == 0
    assert db.stat().st_mtime_ns == before


def test_apply_fails_without_guard(serva_preview_exists: None, tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    sqlite3.connect(str(db)).close()
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--deal-key",
            DEAL_KEY,
            "--apply",
            "--sqlite-db",
            str(db),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 2
    assert "i-understand-this-writes-sqlite" in r.stderr.lower() or "--i-understand" in r.stderr


def test_apply_not_implemented_when_guarded(serva_preview_exists: None, tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    sqlite3.connect(str(db)).close()
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--deal-key",
            DEAL_KEY,
            "--apply",
            "--sqlite-db",
            str(db),
            "--i-understand-this-writes-sqlite",
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 3
    assert APPLY_NOT_IMPLEMENTED_MSG.split(".")[0] in r.stderr


def test_validate_apply_args_matrix() -> None:
    assert validate_apply_args(apply=False, sqlite_db=None, deal_key=DEAL_KEY, understand_writes=False) is None
    assert validate_apply_args(apply=True, sqlite_db=None, deal_key=DEAL_KEY, understand_writes=True) is not None
    assert (
        validate_apply_args(
            apply=True,
            sqlite_db=Path("/tmp/x.sqlite"),
            deal_key=None,
            understand_writes=True,
        )
        is not None
    )


def test_deal_status_maps_to_logistics_pending(serva_preview_exists: None) -> None:
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    assert plan.commercial_deal["columns"]["deal_status"] == "logistics_pending"


def test_default_preview_path() -> None:
    path = default_preview_path(DEAL_KEY, _REPO)
    assert path.name == f"{DEAL_KEY}.json"


def test_product_seed_rows(serva_preview_exists: None) -> None:
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    refs = {r["columns"]["ref_code"] for r in plan.commercial_product}
    assert refs == {"004250001", "003593002"}
    assert len(plan.commercial_product_alias) == 4
