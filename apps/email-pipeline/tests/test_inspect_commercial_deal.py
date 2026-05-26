"""Tests for read-only commercial deal inspection CLI (Phase 2.6)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.commercial.commercial_deal_inspector import (
    build_deal_report,
    connect_readonly,
    format_deal_report,
    margin_blocker_explanation,
)
from origenlab_email_pipeline.commercial.commercial_deal_promotion import (
    apply_deal_promotion_plan,
    build_serva_ceaf_plan_from_default_preview,
)
from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    ensure_commercial_deal_tables,
)
from origenlab_email_pipeline.commercial.serva_ceaf_deal_confirmed import DEAL_KEY

_REPO = Path(__file__).resolve().parents[1]
_PREVIEW = _REPO / "reports/out/active/current/commercial_deals_preview/serva-ceaf-oc-26172-po-174-26.json"
_SCRIPT = _REPO / "scripts/commercial/inspect_commercial_deal.py"

_SENSITIVE_SUBSTRINGS = ("body", "full_body", "body_text", "full_text", "attachment_extract")


@pytest.fixture
def serva_preview_exists() -> None:
    if not _PREVIEW.is_file():
        pytest.skip(f"preview fixture missing: {_PREVIEW}")


@pytest.fixture
def applied_db(tmp_path: Path, serva_preview_exists: None) -> Path:
    """Return a tmp SQLite file with SERVA/CEAF deal applied."""
    db = tmp_path / "backup" / "ledger-test.sqlite"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_commercial_deal_tables(conn)
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    apply_deal_promotion_plan(conn, plan)
    conn.close()
    return db


def test_connect_readonly_refuses_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        connect_readonly(tmp_path / "nonexistent.sqlite")


def test_build_report_raises_on_missing_deal(applied_db: Path) -> None:
    conn = connect_readonly(applied_db)
    with pytest.raises(KeyError, match="deal not found"):
        build_deal_report(conn, "no-such-deal-key")
    conn.close()


def test_build_report_header_values(applied_db: Path) -> None:
    conn = connect_readonly(applied_db)
    report = build_deal_report(conn, DEAL_KEY)
    conn.close()
    h = report["header"]
    assert h["deal_key"] == DEAL_KEY
    assert h["deal_status"] == "logistics_pending"
    assert h["margin_status"] == "needs_review"
    assert h["reconciliation_status"] == "reconciled_excluding_supplier_freight"
    assert h["client_sale_net_clp"] == 1_260_000
    assert h["client_iva_amount_clp"] == 239_400
    assert h["client_sale_gross_clp"] == 1_499_400
    assert h["supplier_invoice_total_decimal"] == "363.00"
    assert h["supplier_invoice_total_minor"] == 36300
    assert h["supplier_amount_paid_decimal"] == "218.00"
    assert h["supplier_amount_paid_minor"] == 21800


def test_build_report_lines(applied_db: Path) -> None:
    conn = connect_readonly(applied_db)
    report = build_deal_report(conn, DEAL_KEY)
    conn.close()
    lines = report["lines"]
    assert len(lines) == 3
    ref_codes = {ln["ref_code"] for ln in lines}
    assert "4250001" in ref_codes
    assert "3593002" in ref_codes
    net_values = {ln["line_net_amount"] for ln in lines}
    assert 695_000 in net_values
    assert 545_000 in net_values


def test_build_report_costs(applied_db: Path) -> None:
    conn = connect_readonly(applied_db)
    report = build_deal_report(conn, DEAL_KEY)
    conn.close()
    costs = report["costs"]
    assert len(costs) == 3
    kinds = {c["cost_kind"] for c in costs}
    assert "supplier_product" in kinds
    assert "supplier_handling" in kinds
    assert "supplier_freight_quoted" in kinds
    freight = next(c for c in costs if c["cost_kind"] == "supplier_freight_quoted")
    assert freight["excluded_from_supplier_wire"] == 1


def test_build_report_payments_masked(applied_db: Path) -> None:
    conn = connect_readonly(applied_db)
    report = build_deal_report(conn, DEAL_KEY)
    conn.close()
    payments = report["payments"]
    assert len(payments) == 2
    for p in payments:
        assert p.get("transfer_id") != "2152655677", "transfer_id must be masked"
        assert p.get("operation_id") != "INT_EMP2605221134124589096100", "operation_id must be masked"
        if p.get("transfer_id") is not None:
            assert p["transfer_id"] == "***MASKED***"
    inbound = next(p for p in payments if p["direction"] == "inbound")
    assert inbound["amount_gross_integer"] == 1_499_400
    outbound = next(p for p in payments if p["direction"] == "outbound")
    assert outbound["amount_minor"] == 21800
    assert outbound["secondary_amount_minor"] == 26847


def test_build_report_events(applied_db: Path) -> None:
    conn = connect_readonly(applied_db)
    report = build_deal_report(conn, DEAL_KEY)
    conn.close()
    events = report["events"]
    assert len(events) >= 5
    types = {e["event_type"] for e in events}
    assert "client_payment_received" in types
    assert "supplier_payment_sent" in types


def test_build_report_field_evidence(applied_db: Path) -> None:
    conn = connect_readonly(applied_db)
    report = build_deal_report(conn, DEAL_KEY)
    conn.close()
    fe = {row["field_name"]: row for row in report["field_evidence"]}
    assert "client_sale_net_clp" in fe
    assert "supplier_amount_paid_decimal" in fe
    assert "reconciliation_status" in fe
    assert fe["client_sale_net_clp"]["normalized_value"] == "1260000"


def test_report_contains_no_body_columns(applied_db: Path) -> None:
    conn = connect_readonly(applied_db)
    report = build_deal_report(conn, DEAL_KEY)
    conn.close()
    report_str = json.dumps(report)
    for sub in _SENSITIVE_SUBSTRINGS:
        assert f'"{sub}"' not in report_str, f"forbidden column {sub!r} found in report"


def test_format_report_human_readable(applied_db: Path) -> None:
    conn = connect_readonly(applied_db)
    report = build_deal_report(conn, DEAL_KEY)
    conn.close()
    text = format_deal_report(report)
    assert "CEAF" in text
    assert "SERVA" in text
    assert "logistics_pending" in text
    assert "needs_review" in text
    assert "1,260,000" in text
    assert "363.00" in text
    assert "218.00" in text
    assert "client_payment_received" in text
    for sub in _SENSITIVE_SUBSTRINGS:
        assert sub not in text


def test_format_report_masks_transfer_id(applied_db: Path) -> None:
    conn = connect_readonly(applied_db)
    report = build_deal_report(conn, DEAL_KEY)
    conn.close()
    text = format_deal_report(report)
    assert "2152655677" not in text
    assert "***MASKED***" in text


def test_margin_blocker_explanation_needs_review() -> None:
    explanation = margin_blocker_explanation("needs_review")
    assert "Wise" in explanation or "logistics" in explanation.lower()


def test_cli_human_report_exit_zero(applied_db: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--sqlite-db", str(applied_db), "--deal-key", DEAL_KEY],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert "CEAF" in r.stdout
    assert "SERVA" in r.stdout
    assert "2152655677" not in r.stdout
    for sub in _SENSITIVE_SUBSTRINGS:
        assert sub not in r.stdout


def test_cli_json_output_parseable(applied_db: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--sqlite-db", str(applied_db), "--deal-key", DEAL_KEY, "--json"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["deal_key"] == DEAL_KEY
    assert payload["header"]["client_sale_net_clp"] == 1_260_000
    payments = payload["payments"]
    for p in payments:
        assert p.get("transfer_id") != "2152655677"


def test_cli_missing_deal_exits_nonzero(applied_db: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--sqlite-db", str(applied_db), "--deal-key", "no-such-deal"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode != 0
    assert "ERROR" in r.stderr


def test_cli_missing_db_exits_nonzero(tmp_path: Path) -> None:
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--sqlite-db",
            str(tmp_path / "doesnotexist.sqlite"),
            "--deal-key",
            DEAL_KEY,
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode != 0
    assert "ERROR" in r.stderr


def test_cli_no_writes_to_db(applied_db: Path) -> None:
    before = applied_db.stat().st_mtime_ns
    subprocess.run(
        [sys.executable, str(_SCRIPT), "--sqlite-db", str(applied_db), "--deal-key", DEAL_KEY],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert applied_db.stat().st_mtime_ns == before, "SQLite file must not be modified"
