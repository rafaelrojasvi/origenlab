"""Mock Postgres connection for catalog mirror API tests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_LEGACY_BROKEN_PROSE_SANITIZER = re.compile(r"\s+(?=[a-z\d])")

from fake_conn import MirrorFakeConn, _FakeCursor

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SEED_PATH = (
    _REPO_ROOT
    / "email-pipeline"
    / "data"
    / "catalog"
    / "catalog_seed_v1.json"
)


def _build_catalog_fixture() -> dict[str, Any]:
    seed = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    categories = {
        c["category_key"]: {
            "category_key": c["category_key"],
            "display_name": c["display_name"],
            "equipment_class": c.get("equipment_class"),
        }
        for c in seed["categories"]
    }
    products: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    category_maps: list[dict[str, Any]] = []
    specs: list[dict[str, Any]] = []
    offers: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    commercial_history: list[dict[str, Any]] = []

    for prod in seed["products"]:
        pk = prod["product_key"]
        products.append(
            {
                "product_key": pk,
                "display_name": prod["display_name"],
                "brand": prod.get("brand"),
                "manufacturer_name": prod.get("manufacturer_name"),
                "product_kind": prod["product_kind"],
                "equipment_class": prod.get("equipment_class"),
                "model_number": prod.get("model_number"),
                "default_unit": prod.get("default_unit"),
                "website_slug": prod.get("website_slug"),
                "website_product_id": prod.get("website_product_id"),
                "public_summary": prod.get("public_summary"),
                "is_active": True,
                "confidence": prod["confidence"],
            }
        )
        for alias in prod.get("aliases") or []:
            aliases.append(
                {
                    "product_key": pk,
                    "alias_source": alias["alias_source"],
                    "alias_code": alias["alias_code"],
                    "alias_kind": alias.get("alias_kind"),
                }
            )
        for i, ck in enumerate(prod.get("category_keys") or []):
            category_maps.append(
                {
                    "product_key": pk,
                    "category_key": ck,
                    "is_primary": i == 0,
                }
            )
        for spec in prod.get("specs") or []:
            specs.append({"product_key": pk, **spec})
        for offer in prod.get("supplier_offers") or []:
            offers.append({"product_key": pk, **offer})
        for snap in prod.get("price_snapshots") or []:
            offer_key = snap.get("supplier_offer_key")
            snapshots.append(
                {
                    "product_key": pk,
                    "offer_key": offer_key,
                    "snapshot_key": snap["snapshot_key"],
                    "snapshot_kind": snap.get("snapshot_kind", "supplier_quote"),
                    "currency": snap.get("currency"),
                    "amount_decimal": snap.get("amount_decimal"),
                    "amount_minor": snap.get("amount_minor"),
                    "amount_clp_integer": snap.get("amount_clp_integer"),
                    "quantity": snap.get("quantity"),
                    "unit": snap.get("unit"),
                    "incoterm": snap.get("incoterm"),
                    "price_notes": snap.get("price_notes"),
                    "is_public_safe": False,
                    "confidence": snap.get("confidence", prod["confidence"]),
                    "observed_at": snap.get("observed_at"),
                }
            )
        for link in prod.get("commercial_links") or []:
            links.append({"product_key": pk, **link})
        for hist in prod.get("commercial_history") or []:
            commercial_history.append({"product_key": pk, **hist})

    return {
        "products": products,
        "categories": list(categories.values()),
        "aliases": aliases,
        "category_maps": category_maps,
        "specs": specs,
        "offers": offers,
        "snapshots": snapshots,
        "links": links,
        "commercial_history": commercial_history,
    }


class CatalogFakeConn(MirrorFakeConn):
    """Postgres fake with nine seed products in catalog.* tables."""

    def __init__(self, *, broken_prose: bool = False) -> None:
        super().__init__()
        fx = _build_catalog_fixture()
        self.tables[("catalog", "product")] = True
        self.tables[("catalog", "product_category")] = True
        self.tables[("catalog", "product_alias")] = True
        self.tables[("catalog", "product_category_map")] = True
        self.tables[("catalog", "product_spec")] = True
        self.tables[("catalog", "supplier_offer")] = True
        self.tables[("catalog", "price_snapshot")] = True
        self.tables[("catalog", "product_commercial_link")] = True
        self.tables[("catalog", "product_commercial_history")] = True
        self.products: list[dict[str, Any]] = fx["products"]
        self.categories: list[dict[str, Any]] = fx["categories"]
        self.aliases: list[dict[str, Any]] = fx["aliases"]
        self.category_maps: list[dict[str, Any]] = fx["category_maps"]
        self.specs: list[dict[str, Any]] = fx["specs"]
        self.offers: list[dict[str, Any]] = fx["offers"]
        self.snapshots: list[dict[str, Any]] = fx["snapshots"]
        self.links: list[dict[str, Any]] = fx["links"]
        self.commercial_history: list[dict[str, Any]] = fx["commercial_history"]
        if broken_prose:
            self._apply_legacy_broken_prose_fixture()

    @staticmethod
    def _legacy_join_prose(text: str) -> str:
        return _LEGACY_BROKEN_PROSE_SANITIZER.sub("", text)

    def _apply_legacy_broken_prose_fixture(self) -> None:
        """Simulate Postgres rows stored with legacy joined-word prose."""
        for product in self.products:
            if product["product_key"] == "serva-blueslick-250ml":
                product["public_summary"] = (
                    "Reactivo SERVA para tratamiento de placas en electroforesis; "
                    "cotizacióny disponibilidad sujetas a confirmación."
                )
            if product["product_key"] == "ika-rv10-70-vapor-tube":
                product["display_name"] = self._legacy_join_prose(product["display_name"])
                product["public_summary"] = (
                    "Tubo de vapor IKA RV10.70 solicitado porcliente (RG Energía), cantidad3; "
                    "precio proveedor pendiente de confirmar moneda."
                )
            if product["product_key"] == "crtop-olt-hp-5l":
                product["public_summary"] = (
                    "Reactor de laboratorio CRTOP OLT-HP-5L; confirmar flete e importación "
                    "antes decotizar al cliente."
                )
        for category in self.categories:
            if category["category_key"] == "heating_accessory":
                category["display_name"] = self._legacy_join_prose(category["display_name"])
        for offer in self.offers:
            if offer["product_key"] == "ika-rv10-70-vapor-tube":
                offer["availability_note"] = (
                    "Stock disponible según proveedor; confirmar moneda y si el montoes "
                    "precio unitario."
                )
        for snap in self.snapshots:
            if snap["snapshot_key"] == "ika-rv10-70-price-ambiguous":
                snap["price_notes"] = (
                    "Cliente solicitó cantidad3. Monto112,00 del proveedor; moneda ambigua — "
                    "confirmar antes decotizar."
                )

    def _apply_list_filters(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        rows = list(self.products)
        s = " ".join(sql.split()).lower()
        idx = 0
        if "display_name ilike" in s:
            pattern = str(params[idx]).strip("%").lower()
            rows = [
                r
                for r in rows
                if pattern
                in " ".join(
                    str(r.get(k) or "")
                    for k in ("display_name", "product_key", "brand", "public_summary")
                ).lower()
            ]
            idx += 4
        if "coalesce(p.brand" in s:
            brand = str(params[idx])
            rows = [r for r in rows if (r.get("brand") or "").lower() == brand.lower()]
            idx += 1
        if "p.equipment_class = %s" in s:
            equipment_class = str(params[idx])
            rows = [r for r in rows if r.get("equipment_class") == equipment_class]
            idx += 1
        if "product_category_map" in s and "exists" in s:
            category_key = str(params[idx])
            rows = [
                r
                for r in rows
                if any(
                    m["product_key"] == r["product_key"] and m["category_key"] == category_key
                    for m in self.category_maps
                )
            ]
        return rows

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        s = " ".join(sql.split()).lower()
        p = list(params) if params is not None else []

        if "information_schema.tables" in s and "catalog" in s:
            schema = params[0] if params else ""
            table = params[1] if params and len(params) > 1 else ""
            ok = self.tables.get((schema, table), False)
            return _FakeCursor([{"?": 1}] if ok else [])

        if "count(*)" in s and "from catalog.product p" in s:
            filtered = (
                self._apply_list_filters(sql, p) if "where" in s else list(self.products)
            )
            return _FakeCursor([{"n": len(filtered)}])

        if "from catalog.product p" in s and "order by" in s:
            if "where" in s:
                filter_params = p[:-1]
                limit = int(p[-1])
            else:
                filter_params = []
                limit = int(p[0])
            filtered = (
                self._apply_list_filters(sql, filter_params)
                if "where" in s
                else list(self.products)
            )
            filtered.sort(key=lambda r: (r["display_name"], r["product_key"]))
            return _FakeCursor(filtered[:limit])

        if "from catalog.product_alias" in s:
            key = str(p[0])
            rows = [r for r in self.aliases if r["product_key"] == key]
            return _FakeCursor(rows)

        if "from catalog.product_category_map" in s:
            key = str(p[0])
            rows = []
            for m in self.category_maps:
                if m["product_key"] != key:
                    continue
                cat = next(c for c in self.categories if c["category_key"] == m["category_key"])
                rows.append(
                    {
                        "category_key": cat["category_key"],
                        "display_name": cat["display_name"],
                        "equipment_class": cat.get("equipment_class"),
                        "is_primary": m["is_primary"],
                    }
                )
            rows.sort(key=lambda r: (not r["is_primary"], r["display_name"]))
            return _FakeCursor(rows)

        if "from catalog.product_spec" in s:
            key = str(p[0])
            rows = [r for r in self.specs if r["product_key"] == key]
            return _FakeCursor(rows)

        if "from catalog.supplier_offer" in s:
            key = str(p[0])
            rows = [r for r in self.offers if r["product_key"] == key]
            return _FakeCursor(rows)

        if "from catalog.price_snapshot" in s:
            key = str(p[0])
            rows = [r for r in self.snapshots if r["product_key"] == key]
            return _FakeCursor(rows)

        if "from catalog.product_commercial_link" in s:
            key = str(p[0])
            rows = [r for r in self.links if r["product_key"] == key]
            return _FakeCursor(rows)

        if "from catalog.product_commercial_history" in s:
            key = str(p[0])
            rows = [r for r in self.commercial_history if r["product_key"] == key]
            rows.sort(
                key=lambda r: (
                    r.get("deal_key") or "",
                    0 if (r.get("line_side") or "") == "supplier" else 1,
                    r.get("line_kind") or "",
                    r.get("history_key") or "",
                )
            )
            return _FakeCursor(rows)

        if "from catalog.product where" in s:
            key = str(p[0]).strip()
            rows = [r for r in self.products if r["product_key"] == key]
            return _FakeCursor(rows)

        return super().execute(sql, params)
