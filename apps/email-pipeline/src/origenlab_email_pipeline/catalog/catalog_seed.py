"""Load and validate catalog_seed_v1.json (Phase 8B)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.catalog.catalog_mirror_safety import (
    CatalogMirrorSafetyError,
    assert_catalog_prose_spacing,
)
from origenlab_email_pipeline.catalog.catalog_schema import (
    COMMERCIAL_HISTORY_LINE_KINDS,
    COMMERCIAL_HISTORY_LINE_SIDES,
    CONFIDENCE_LEVELS,
    LINK_KINDS,
    OFFER_STATUSES,
    PRODUCT_KINDS,
    SNAPSHOT_KINDS,
)
from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    decimal_to_minor,
    validate_decimal_minor_pair,
)

CATALOG_SEED_VERSION = "1.0.0"

_FORBIDDEN_SAFE_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\bbank\b",
        r"\bbanco\b",
        r"\bswift\b",
        r"\biban\b",
        r"\bcuenta\b",
        r"\bbeneficiario\b",
        r"\brut\b",
        r"gmail\.com",
        r"mail\.google",
        r"source_file",
        r"transfer_id",
        r"operation_id",
        r"https?://",
    )
)

_ALIAS_CODE_RE = re.compile(r"^[\w.\-/]+$", re.I)

_REQUIRED_PRODUCT_KEYS = frozenset(
    {
        "product_key",
        "display_name",
        "product_kind",
        "public_summary",
        "confidence",
    }
)


class CatalogSeedValidationError(ValueError):
    """Raised when seed JSON fails validation."""


def default_seed_path(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[3]
    return root / "data" / "catalog" / "catalog_seed_v1.json"


def normalize_alias_code(raw: str) -> str:
    """Normalize SKU/part codes: strip whitespace, remove internal spaces/dashes, uppercase."""
    text = raw.strip()
    if not text:
        raise CatalogSeedValidationError("alias_code must not be empty")
    collapsed = re.sub(r"[\s\-]+", "", text)
    return collapsed.upper()


def assert_safe_text(value: str | None, *, field: str) -> None:
    if value is None or value == "":
        return
    for pat in _FORBIDDEN_SAFE_TEXT_PATTERNS:
        if pat.search(value):
            raise CatalogSeedValidationError(
                f"forbidden content in {field}: matched {pat.pattern!r}"
            )


def _assert_prose_spacing(value: str | None, *, field: str) -> None:
    try:
        assert_catalog_prose_spacing(value, field=field)
    except CatalogMirrorSafetyError as exc:
        raise CatalogSeedValidationError(str(exc)) from exc


def load_seed_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CatalogSeedValidationError("seed root must be an object")
    return data


def validate_seed(data: dict[str, Any]) -> dict[str, list[str]]:
    """Validate seed structure and cross-references. Returns product_keys list."""
    version = data.get("seed_version")
    if version != CATALOG_SEED_VERSION:
        raise CatalogSeedValidationError(
            f"seed_version must be {CATALOG_SEED_VERSION!r}, got {version!r}"
        )

    categories = data.get("categories")
    if not isinstance(categories, list) or not categories:
        raise CatalogSeedValidationError("categories must be a non-empty list")

    category_keys: set[str] = set()
    for cat in categories:
        if not isinstance(cat, dict):
            raise CatalogSeedValidationError("each category must be an object")
        ck = cat.get("category_key")
        if not ck or ck in category_keys:
            raise CatalogSeedValidationError(f"duplicate or missing category_key: {ck!r}")
        category_keys.add(str(ck))
        assert_safe_text(cat.get("display_name"), field="category.display_name")

    products = data.get("products")
    if not isinstance(products, list) or not products:
        raise CatalogSeedValidationError("products must be a non-empty list")

    product_keys: list[str] = []
    seen_product_keys: set[str] = set()
    seen_offer_keys: set[str] = set()
    seen_snapshot_keys: set[str] = set()
    seen_links: set[tuple[str, str]] = set()
    seen_history_keys: set[str] = set()

    for prod in products:
        if not isinstance(prod, dict):
            raise CatalogSeedValidationError("each product must be an object")
        missing = _REQUIRED_PRODUCT_KEYS - prod.keys()
        if missing:
            raise CatalogSeedValidationError(
                f"product missing fields {sorted(missing)}: {prod.get('product_key')}"
            )
        pk = str(prod["product_key"])
        if pk in seen_product_keys:
            raise CatalogSeedValidationError(f"duplicate product_key: {pk}")
        seen_product_keys.add(pk)
        product_keys.append(pk)

        kind = prod["product_kind"]
        if kind not in PRODUCT_KINDS:
            raise CatalogSeedValidationError(f"{pk}: invalid product_kind {kind!r}")
        conf = prod["confidence"]
        if conf not in CONFIDENCE_LEVELS:
            raise CatalogSeedValidationError(f"{pk}: invalid confidence {conf!r}")

        for field in (
            "display_name",
            "brand",
            "manufacturer_name",
            "public_summary",
            "model_number",
            "website_slug",
        ):
            assert_safe_text(prod.get(field), field=f"{pk}.{field}")
            if field in ("public_summary", "display_name"):
                _assert_prose_spacing(prod.get(field), field=f"{pk}.{field}")

        aliases = prod.get("aliases") or []
        if not isinstance(aliases, list):
            raise CatalogSeedValidationError(f"{pk}: aliases must be a list")
        seen_alias: set[tuple[str, str]] = set()
        for alias in aliases:
            raw_code = str(alias["alias_code"])
            if not _ALIAS_CODE_RE.match(raw_code.strip()):
                raise CatalogSeedValidationError(f"{pk}: invalid alias_code {raw_code!r}")
            norm = normalize_alias_code(raw_code)
            src = str(alias["alias_source"])
            key = (src, norm)
            if key in seen_alias:
                raise CatalogSeedValidationError(f"{pk}: duplicate alias {key}")
            seen_alias.add(key)
            assert_safe_text(alias.get("notes"), field=f"{pk}.alias.notes")

        cat_keys = prod.get("category_keys") or []
        for ck in cat_keys:
            if ck not in category_keys:
                raise CatalogSeedValidationError(f"{pk}: unknown category_key {ck!r}")

        for spec in prod.get("specs") or []:
            assert_safe_text(spec.get("spec_value"), field=f"{pk}.spec_value")
            assert_safe_text(spec.get("spec_key"), field=f"{pk}.spec_key")

        for offer in prod.get("supplier_offers") or []:
            ok = str(offer["offer_key"])
            if ok in seen_offer_keys:
                raise CatalogSeedValidationError(f"duplicate offer_key: {ok}")
            seen_offer_keys.add(ok)
            status = offer.get("offer_status", "received")
            if status not in OFFER_STATUSES:
                raise CatalogSeedValidationError(f"{ok}: invalid offer_status")
            for field in ("payment_terms", "delivery_terms", "availability_note"):
                assert_safe_text(offer.get(field), field=f"{ok}.{field}")
                if field == "availability_note":
                    _assert_prose_spacing(offer.get(field), field=f"{ok}.{field}")

        for snap in prod.get("price_snapshots") or []:
            sk = str(snap["snapshot_key"])
            if sk in seen_snapshot_keys:
                raise CatalogSeedValidationError(f"duplicate snapshot_key: {sk}")
            seen_snapshot_keys.add(sk)
            kind = snap.get("snapshot_kind", "supplier_quote")
            if kind not in SNAPSHOT_KINDS:
                raise CatalogSeedValidationError(f"{sk}: invalid snapshot_kind")
            _validate_price_snapshot(snap, product_key=pk)

        for link in prod.get("commercial_links") or []:
            lk = str(link["link_kind"])
            ref = str(link["link_ref"])
            if lk not in LINK_KINDS:
                raise CatalogSeedValidationError(f"{pk}: invalid link_kind {lk!r}")
            assert_safe_text(ref, field=f"{pk}.link_ref")
            if (lk, ref) in seen_links:
                raise CatalogSeedValidationError(f"duplicate link: {lk}:{ref}")
            seen_links.add((lk, ref))

        for row in prod.get("commercial_history") or []:
            _validate_commercial_history_row(row, product_key=pk, seen_history_keys=seen_history_keys)

    return {"product_keys": product_keys, "category_keys": sorted(category_keys)}


def _validate_commercial_history_row(
    row: dict[str, Any],
    *,
    product_key: str,
    seen_history_keys: set[str],
) -> None:
    if not isinstance(row, dict):
        raise CatalogSeedValidationError(f"{product_key}: commercial_history row must be object")
    hk = str(row.get("history_key", ""))
    if not hk or hk in seen_history_keys:
        raise CatalogSeedValidationError(f"{product_key}: duplicate or missing history_key {hk!r}")
    seen_history_keys.add(hk)
    if not hk.startswith(f"{product_key}:"):
        raise CatalogSeedValidationError(
            f"{product_key}: history_key must start with product_key prefix: {hk!r}"
        )
    side = str(row.get("line_side", ""))
    kind = str(row.get("line_kind", ""))
    if side not in COMMERCIAL_HISTORY_LINE_SIDES:
        raise CatalogSeedValidationError(f"{hk}: invalid line_side {side!r}")
    if kind not in COMMERCIAL_HISTORY_LINE_KINDS:
        raise CatalogSeedValidationError(f"{hk}: invalid line_kind {kind!r}")
    conf = row.get("confidence")
    if conf not in CONFIDENCE_LEVELS:
        raise CatalogSeedValidationError(f"{hk}: invalid confidence {conf!r}")
    if row.get("is_public_safe") and side == "supplier":
        raise CatalogSeedValidationError(f"{hk}: supplier commercial history must not be public_safe")
    if kind != "product" and side == "supplier":
        raise CatalogSeedValidationError(
            f"{hk}: deal-level supplier costs must not be attached as product commercial_history"
        )
    for field in (
        "deal_key",
        "deal_label",
        "client_org_name",
        "supplier_org_name",
        "source_summary",
        "margin_status",
        "deal_status",
        "quantity",
        "unit",
        "currency",
    ):
        assert_safe_text(row.get(field), field=f"{hk}.{field}")
    amount_net_clp = row.get("amount_net_clp")
    amount_decimal = row.get("amount_decimal")
    if side == "client" and kind == "product":
        if amount_net_clp is None or not isinstance(amount_net_clp, int):
            raise CatalogSeedValidationError(f"{hk}: client product line requires amount_net_clp int")
    if side == "supplier" and kind == "product":
        if amount_decimal is None:
            raise CatalogSeedValidationError(f"{hk}: supplier product line requires amount_decimal")
        cur = str(row.get("currency") or "").strip().upper()
        if not cur:
            raise CatalogSeedValidationError(f"{hk}: supplier product line requires currency")
        minor = row.get("amount_minor")
        if minor is None:
            minor = decimal_to_minor(str(amount_decimal), cur)
        if not validate_decimal_minor_pair(str(amount_decimal), int(minor), cur):
            raise CatalogSeedValidationError(f"{hk}: amount_decimal/minor mismatch")


def _validate_price_snapshot(snap: dict[str, Any], *, product_key: str) -> None:
    sk = snap.get("snapshot_key", "?")
    assert_safe_text(snap.get("price_notes"), field=f"{sk}.price_notes")
    _assert_prose_spacing(snap.get("price_notes"), field=f"{sk}.price_notes")

    is_public = snap.get("is_public_safe", False)
    if is_public:
        raise CatalogSeedValidationError(
            f"{product_key}/{sk}: supplier prices must not be is_public_safe=true in v1"
        )

    amount_decimal = snap.get("amount_decimal")
    currency = snap.get("currency")
    price_notes = (snap.get("price_notes") or "").strip()
    amount_clp = snap.get("amount_clp_integer")

    if amount_decimal is not None:
        cur = (currency or "").strip().upper() or None
        if cur is None:
            if "ambiguous" not in price_notes.lower() and "confirm" not in price_notes.lower():
                raise CatalogSeedValidationError(
                    f"{product_key}/{sk}: amount_decimal requires currency or explicit "
                    "ambiguity in price_notes"
                )
        else:
            minor = snap.get("amount_minor")
            if minor is None:
                minor = decimal_to_minor(str(amount_decimal), cur)
            if not validate_decimal_minor_pair(str(amount_decimal), int(minor), cur):
                raise CatalogSeedValidationError(
                    f"{product_key}/{sk}: amount_decimal/minor mismatch for {cur}"
                )

    if amount_clp is not None and not isinstance(amount_clp, int):
        raise CatalogSeedValidationError(f"{product_key}/{sk}: amount_clp_integer must be int")

    offer_key = snap.get("supplier_offer_key")
    if offer_key is not None:
        assert_safe_text(str(offer_key), field=f"{sk}.supplier_offer_key")
