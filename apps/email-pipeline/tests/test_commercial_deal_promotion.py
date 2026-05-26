"""Tests for commercial deal promotion dry-run planner (Phase 2)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.commercial.commercial_deal_promotion import (
    apply_deal_promotion_plan,
    build_plan_for_deal_key,
    build_serva_ceaf_plan_from_default_preview,
    default_preview_path,
    iter_plan_entity_rows,
    plan_contains_forbidden_columns,
    validate_apply_args,
    validate_sqlite_apply_target,
)
from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    _FORBIDDEN_BODY_COLUMN_SUBSTRINGS,
    ensure_commercial_deal_tables,
    foreign_key_check_ok,
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

_SERVA_CEAF_EXPECTED_COUNTS = {
    "commercial_product": 2,
    "commercial_product_alias": 4,
    "commercial_deal": 1,
    "commercial_deal_evidence": 15,
    "commercial_deal_document": 4,
    "commercial_deal_payment": 2,
    "commercial_deal_line": 3,
    "commercial_deal_cost": 3,
    "commercial_deal_event": 7,
    "commercial_deal_field_evidence": 7,
    "commercial_deal_review": 1,
}

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


def test_cli_dry_run_stdout_is_valid_json_only(serva_preview_exists: None) -> None:
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--deal-key", DEAL_KEY],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip(), "stdout must not be empty"
    assert "DRY-RUN" not in r.stdout
    payload = json.loads(r.stdout)
    assert payload["deal_key"] == DEAL_KEY
    assert payload["counts"] == _SERVA_CEAF_EXPECTED_COUNTS

    r_summary = subprocess.run(
        [sys.executable, str(_SCRIPT), "--deal-key", DEAL_KEY, "--summary"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r_summary.returncode == 0, r_summary.stderr
    payload_summary = json.loads(r_summary.stdout)
    assert payload_summary["counts"] == _SERVA_CEAF_EXPECTED_COUNTS
    assert "DRY-RUN" in r_summary.stderr
    assert "counts=" in r_summary.stderr


def test_cli_dry_run_compact_json(serva_preview_exists: None) -> None:
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--deal-key", DEAL_KEY, "--no-pretty-json"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert "\n  " not in r.stdout
    payload = json.loads(r.stdout)
    assert payload["counts"]["commercial_deal_payment"] == 2


def test_cli_json_out_writes_file_and_empty_stdout(serva_preview_exists: None, tmp_path: Path) -> None:
    out_path = tmp_path / "plan.json"
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--deal-key",
            DEAL_KEY,
            "--json-out",
            str(out_path),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""
    assert out_path.is_file()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["counts"] == _SERVA_CEAF_EXPECTED_COUNTS
    assert "Wrote" in r.stderr


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
    json.loads(r.stdout)

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


def _memory_db_with_schema() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_commercial_deal_tables(conn)
    return conn


def _forbidden_values_in_db(conn: sqlite3.Connection) -> list[str]:
    hits: list[str] = []
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'commercial_%'"
    ).fetchall()
    for (table,) in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        for col in cols:
            if not any(sub in col for sub in _FORBIDDEN_BODY_COLUMN_SUBSTRINGS):
                continue
            row = conn.execute(
                f"SELECT {col} FROM {table} WHERE {col} IS NOT NULL AND TRIM({col}) != '' LIMIT 1"
            ).fetchone()
            if row and row[0]:
                hits.append(f"{table}.{col}")
    return hits


def test_apply_to_memory_db(serva_preview_exists: None) -> None:
    conn = _memory_db_with_schema()
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    result = apply_deal_promotion_plan(conn, plan)
    assert result.deal_key == DEAL_KEY
    assert result.deal_id > 0
    assert result.foreign_key_check_ok is True
    assert foreign_key_check_ok(conn) is True
    row = conn.execute("SELECT id FROM commercial_deal WHERE deal_key = ?", (DEAL_KEY,)).fetchone()
    assert row is not None
    pay_count = conn.execute(
        "SELECT COUNT(*) FROM commercial_deal_payment WHERE deal_id = ?",
        (result.deal_id,),
    ).fetchone()[0]
    assert pay_count == 2
    fe_count = conn.execute(
        "SELECT COUNT(*) FROM commercial_deal_field_evidence WHERE deal_id = ?",
        (result.deal_id,),
    ).fetchone()[0]
    assert fe_count == 7
    assert _forbidden_values_in_db(conn) == []
    conn.close()


def test_second_apply_is_idempotent(serva_preview_exists: None) -> None:
    conn = _memory_db_with_schema()
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    first = apply_deal_promotion_plan(conn, plan)
    second = apply_deal_promotion_plan(conn, plan)
    assert second.deal_action == "update"
    assert second.deal_id == first.deal_id
    assert second.row_counts == first.row_counts
    for table, count in first.row_counts.items():
        if table == "commercial_deal":
            continue
        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if table in ("commercial_product", "commercial_product_alias"):
            assert total == count
        else:
            scoped = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE deal_id = ?",
                (first.deal_id,),
            ).fetchone()[0]
            assert scoped == count
    conn.close()


def test_apply_cli_to_backup_db(serva_preview_exists: None, tmp_path: Path) -> None:
    db = tmp_path / "backup" / "ledger-dev.sqlite"
    db.parent.mkdir(parents=True)
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
            "--summary",
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""
    assert "APPLIED" in r.stderr
    assert "row_counts=" in r.stderr
    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT COUNT(*) FROM commercial_deal").fetchone()[0] == 1
    conn.close()


def test_apply_refuses_production_like_path(serva_preview_exists: None, tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    sqlite3.connect(str(db)).close()
    assert validate_sqlite_apply_target(db) is not None
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
    assert r.returncode == 4
    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='commercial_deal'").fetchone()[0] == 0
    conn.close()


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
