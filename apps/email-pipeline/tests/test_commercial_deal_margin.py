"""Tests for commercial deal margin cost update workflow."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.commercial.commercial_deal_margin import (
    MarginCostInputs,
    apply_margin_update_plan,
    build_margin_update_plan,
    compute_margin,
    remaining_margin_blockers,
)
from origenlab_email_pipeline.commercial.commercial_deal_promotion import (
    apply_deal_promotion_plan,
    build_serva_ceaf_plan_from_default_preview,
)
from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    ensure_commercial_deal_tables,
)
from origenlab_email_pipeline.commercial.serva_ceaf_deal_confirmed import (
    CLIENT_SALE_AMOUNT_NET_CLP,
    DEAL_KEY,
)

_REPO = Path(__file__).resolve().parents[1]
_PREVIEW = _REPO / "reports/out/active/current/commercial_deals_preview/serva-ceaf-oc-26172-po-174-26.json"
_SCRIPT = _REPO / "scripts/commercial/update_commercial_deal_costs.py"


@pytest.fixture
def serva_preview_exists() -> None:
    if not _PREVIEW.is_file():
        pytest.skip(f"preview fixture missing: {_PREVIEW}")


@pytest.fixture
def applied_db(tmp_path: Path, serva_preview_exists: None) -> Path:
    db = tmp_path / "backup" / "ledger-margin.sqlite"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_commercial_deal_tables(conn)
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    apply_deal_promotion_plan(conn, plan)
    conn.close()
    return db


def _apply_margin(db: Path, inputs: MarginCostInputs) -> dict:
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    plan = build_margin_update_plan(conn, DEAL_KEY, inputs, mode="apply")
    result = apply_margin_update_plan(conn, plan)
    conn.commit()
    conn.close()
    return result


def test_partial_cost_keeps_needs_review(applied_db: Path) -> None:
    conn = sqlite3.connect(str(applied_db))
    plan = build_margin_update_plan(
        conn, DEAL_KEY, MarginCostInputs(wise_clp_debit=400_000), mode="dry_run"
    )
    conn.close()
    assert plan.margin_status == "needs_review"
    assert plan.margin_net_clp is None
    assert len(plan.remaining_blockers) > 0


def test_all_required_costs_compute_margin(applied_db: Path) -> None:
    result = _apply_margin(
        applied_db,
        MarginCostInputs(
            wise_clp_debit=400_000,
            dhl_cost_clp=50_000,
            import_cost_clp=10_000,
            note="operator confirmed May 2026",
        ),
    )
    assert result["margin_status"] == "computed"
    expected_net = CLIENT_SALE_AMOUNT_NET_CLP - (400_000 + 50_000 + 10_000)
    assert result["margin_net_clp"] == expected_net
    assert result["margin_pct"] == pytest.approx(expected_net / CLIENT_SALE_AMOUNT_NET_CLP, rel=1e-4)

    conn = sqlite3.connect(str(applied_db))
    row = conn.execute(
        "SELECT margin_status, margin_net_clp FROM commercial_deal WHERE deal_key=?",
        (DEAL_KEY,),
    ).fetchone()
    conn.close()
    assert row[0] == "computed"
    assert row[1] == expected_net


def test_margin_uses_net_sale_not_gross(applied_db: Path) -> None:
    """Margin basis must be client_sale_net_clp, not payment gross."""
    wise = 100_000
    dhl = 0
    imp = 0
    note = "no dhl or import"
    _apply_margin(
        applied_db,
        MarginCostInputs(
            wise_clp_debit=wise,
            dhl_cost_clp=dhl,
            import_cost_clp=imp,
            note=note,
        ),
    )
    conn = sqlite3.connect(str(applied_db))
    deal = conn.execute(
        "SELECT client_sale_net_clp, client_sale_gross_clp FROM commercial_deal WHERE deal_key=?",
        (DEAL_KEY,),
    ).fetchone()
    margin = conn.execute(
        "SELECT margin_net_clp FROM commercial_deal WHERE deal_key=?",
        (DEAL_KEY,),
    ).fetchone()[0]
    conn.close()
    assert margin == deal[0] - wise
    assert margin != deal[1] - wise


def test_zero_cost_requires_note() -> None:
    merged = {"wise_clp_debit": 1, "dhl_cost_clp": 0, "import_cost_clp": 1, "bank_fee_clp": None}
    blockers = remaining_margin_blockers(merged, note=None)
    assert any("dhl_cost_clp" in b for b in blockers)


def test_zero_cost_with_note_allowed(applied_db: Path) -> None:
    result = _apply_margin(
        applied_db,
        MarginCostInputs(
            wise_clp_debit=300_000,
            dhl_cost_clp=0,
            import_cost_clp=0,
            note="DHL account; no import duty for this shipment",
        ),
    )
    assert result["margin_status"] == "computed"
    assert result["margin_net_clp"] == CLIENT_SALE_AMOUNT_NET_CLP - 300_000

    conn = sqlite3.connect(str(applied_db))
    row = conn.execute(
        """
        SELECT amount_integer, description FROM commercial_deal_cost
        WHERE deal_id=(SELECT id FROM commercial_deal WHERE deal_key=?)
          AND cost_kind='logistics_dhl'
        """,
        (DEAL_KEY,),
    ).fetchone()
    conn.close()
    assert row[0] == 0
    assert "zero confirmed" in row[1].lower() or "DHL" in row[1]


def test_idempotent_cost_upsert(applied_db: Path) -> None:
    inputs = MarginCostInputs(
        wise_clp_debit=200_000,
        dhl_cost_clp=30_000,
        import_cost_clp=5_000,
        note="first",
    )
    _apply_margin(applied_db, inputs)
    _apply_margin(applied_db, inputs)
    conn = sqlite3.connect(str(applied_db))
    count = conn.execute(
        """
        SELECT COUNT(*) FROM commercial_deal_cost
        WHERE deal_id=(SELECT id FROM commercial_deal WHERE deal_key=?)
          AND cost_kind IN ('fx_spread','logistics_dhl','logistics_import')
        """,
        (DEAL_KEY,),
    ).fetchone()[0]
    conn.close()
    assert count == 3


def test_apply_without_guard_fails(applied_db: Path) -> None:
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--sqlite-db",
            str(applied_db),
            "--deal-key",
            DEAL_KEY,
            "--wise-clp-debit",
            "1",
            "--apply",
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 2
    assert "i-understand-this-writes-sqlite" in r.stderr.lower() or "--i-understand" in r.stderr


def test_cli_dry_run_json(applied_db: Path) -> None:
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--sqlite-db",
            str(applied_db),
            "--deal-key",
            DEAL_KEY,
            "--wise-clp-debit",
            "100",
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["margin_status"] == "needs_review"


def test_compute_margin_unit() -> None:
    merged = {
        "wise_clp_debit": 100,
        "dhl_cost_clp": 50,
        "import_cost_clp": 25,
        "bank_fee_clp": None,
    }
    status, net, pct, total, blockers = compute_margin(1000, merged, note="ok")
    assert status == "computed"
    assert net == 825
    assert total == 175
    assert pct == pytest.approx(0.825)
    assert blockers == []
