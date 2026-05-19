"""Equipment queue path resolution (manifest + stale guards)."""

from __future__ import annotations

import json
from pathlib import Path

from origenlab_api.repositories.equipment_opportunities import (
    resolve_operator_queue_csv,
)


def _write_operator_csv(path: Path) -> None:
    path.write_text(
        "priority_rank,codigo_licitacion,buyer,region,close_date,equipment_category,"
        "item_description,next_action,contact_status,safe_channel,supplier_needed,"
        "supplier_contact,gmail_prior_thread,outreach_state,operator_note\n"
        "1,TEST-1,Buyer A,RM,01/01/2026,centrifuge,Item A,quote_now,x,mercado_publico_bid,yes,,,,note\n",
        encoding="utf-8",
    )


def test_resolve_prefers_manifest_canonical_not_stale_crosscheck(tmp_path: Path) -> None:
    active = tmp_path / "current"
    active.mkdir()
    _write_operator_csv(active / "equipment_first_operator_queue_20260518.csv")
    (active / "buyer_opportunity_crosscheck_20260518.csv").write_text(
        "priority_rank,codigo_licitacion\n99,STALE\n",
        encoding="utf-8",
    )
    manifest = {
        "campaign_mode": "equipment_first",
        "canonical_files": [
            "equipment_first_operator_queue_20260518.csv",
            "buyer_opportunity_crosscheck_20260518.csv",
        ],
        "stale_files": [{"path": "buyer_opportunity_crosscheck_20260518.csv"}],
    }
    (active / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    resolved = resolve_operator_queue_csv(active, manifest)
    assert resolved is not None
    assert resolved.name == "equipment_first_operator_queue_20260518.csv"
    assert "crosscheck" not in resolved.name


def test_resolve_never_picks_crosscheck_from_glob(tmp_path: Path) -> None:
    active = tmp_path / "current"
    active.mkdir()
    (active / "buyer_opportunity_crosscheck_20260518.csv").write_text("x\n", encoding="utf-8")
    manifest = {"canonical_files": [], "stale_files": []}
    assert resolve_operator_queue_csv(active, manifest) is None
