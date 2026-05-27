"""Tests for catalog_seed_v1.json validation (Phase 8B)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from origenlab_email_pipeline.catalog.catalog_seed import (
    CatalogSeedValidationError,
    default_seed_path,
    load_seed_json,
    normalize_alias_code,
    validate_seed,
)

_REPO = Path(__file__).resolve().parents[1]
_SEED = _REPO / "data" / "catalog" / "catalog_seed_v1.json"


def test_default_seed_path_exists() -> None:
    path = default_seed_path(_REPO)
    assert path == _SEED
    assert path.is_file()


def test_seed_loads_successfully() -> None:
    data = load_seed_json(_SEED)
    meta = validate_seed(data)
    assert len(meta["product_keys"]) == 9
    assert "electrophoresis_reagent" in meta["category_keys"]


def test_normalize_serva_and_ika_alias_codes() -> None:
    assert normalize_alias_code("004250001") == "004250001"
    assert normalize_alias_code("42500") == "42500"
    assert normalize_alias_code("4250-001") == "4250001"
    assert normalize_alias_code("0003812200") == "0003812200"
    assert normalize_alias_code("3812200") == "3812200"
    assert normalize_alias_code("RV10.70") == "RV10.70"


def test_ika_price_ambiguity_required_in_seed() -> None:
    data = load_seed_json(_SEED)
    ika = next(p for p in data["products"] if p["product_key"] == "ika-rv10-70-vapor-tube")
    assert ika["display_name"] == "Tubo de vapor IKA RV10.70"
    assert ika["supplier_offers"][0]["quantity_offered"] == "1"
    snap = ika["price_snapshots"][0]
    assert snap["amount_decimal"] == "112.00"
    assert snap["currency"] is None
    assert snap["quantity"] == "3"
    notes = snap["price_notes"].lower()
    assert "ambigu" in notes
    assert "unitario" in notes or "unit" in notes
    assert "cantidad 3" in notes or "cantidad" in notes


def test_crtop_public_summary_has_no_supplier_price() -> None:
    data = load_seed_json(_SEED)
    crtop = next(p for p in data["products"] if p["product_key"] == "crtop-olt-hp-5l")
    summary = crtop["public_summary"].lower()
    assert "10600" not in summary
    assert "10,600" not in summary
    assert "usd" not in summary
    assert "exw" not in summary


def test_crtop_price_usd_exw_in_seed() -> None:
    data = load_seed_json(_SEED)
    crtop = next(p for p in data["products"] if p["product_key"] == "crtop-olt-hp-5l")
    snap = crtop["price_snapshots"][0]
    assert snap["currency"] == "USD"
    assert snap["amount_decimal"] == "10600.00"
    assert snap["amount_minor"] == 1060000
    assert snap["incoterm"] == "EXW"


def test_forbidden_bank_term_rejected() -> None:
    data = load_seed_json(_SEED)
    bad = copy.deepcopy(data)
    bad["products"][0]["public_summary"] = "Pay to bank account 123"
    with pytest.raises(CatalogSeedValidationError, match="forbidden"):
        validate_seed(bad)


def test_forbidden_gmail_url_rejected_in_link() -> None:
    data = load_seed_json(_SEED)
    bad = copy.deepcopy(data)
    bad["products"][0]["commercial_links"] = [
        {
            "link_kind": "warm_case",
            "link_ref": "https://mail.google.com/mail/u/0/",
            "confidence": "operator_confirmed",
        }
    ]
    with pytest.raises(CatalogSeedValidationError, match="forbidden"):
        validate_seed(bad)


def test_public_safe_supplier_price_rejected() -> None:
    data = load_seed_json(_SEED)
    bad = copy.deepcopy(data)
    bad["products"][3]["price_snapshots"][0]["is_public_safe"] = True
    with pytest.raises(CatalogSeedValidationError, match="is_public_safe"):
        validate_seed(bad)
