"""Build insert/update plans for commercial_deal* tables from operator preview JSON."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    COMMERCIAL_DEAL_SCHEMA_VERSION,
    COMMERCIAL_DEAL_TABLE_NAMES,
    DEAL_STATUSES,
    _FORBIDDEN_BODY_COLUMN_SUBSTRINGS,
    commercial_deal_tables_exist,
    decimal_to_minor,
    ensure_commercial_deal_tables,
    foreign_key_check_ok,
    table_column_names,
)
from origenlab_email_pipeline.commercial.serva_ceaf_deal_confirmed import (
    CLIENT_IVA_AMOUNT_CLP,
    CLIENT_IVA_RATE,
    CLIENT_PAYMENT_AT,
    CLIENT_PAYMENT_RECEIVED_CLP,
    CLIENT_PO_NUMBER,
    CLIENT_SALE_AMOUNT_GROSS_CLP,
    CLIENT_SALE_AMOUNT_NET_CLP,
    DEAL_KEY as SERVA_CEAF_DEAL_KEY,
    SUPPLIER_AMOUNT_PAID_EUR,
    SUPPLIER_FREIGHT_QUOTED_EUR,
    SUPPLIER_HANDLING_COST_EUR,
    SUPPLIER_INVOICE_TOTAL_EUR,
    SUPPLIER_PAYMENT_TRANSFER_ID,
    SUPPLIER_PRODUCT_COST_EUR,
    SUPPLIER_PROFORMA_DATE,
    SUPPLIER_PROFORMA_NUMBER,
    WISE_FUNDED_AT,
    WISE_TOTAL_PAID_USD,
    build_client_vat_breakdown,
    build_confirmed_events,
)
from origenlab_email_pipeline.timeutil import now_iso

PARSER_VERSION = "deal_field_parsers@2026-05-26"
CONFIRMED_FACTS_VERSION = "serva_ceaf_deal_confirmed@2026-05-26"

_FORBIDDEN_ROW_KEYS = frozenset(
    {
        "body",
        "body_text",
        "body_clean",
        "full_body",
        "full_text",
        "attachment_extract",
        "extract_snippet",
    }
)

_COMPOSITE_DEAL_STATUS_MAP = {
    "paid_by_client__supplier_payment_sent__logistics_pending": "logistics_pending",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_preview_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _eur_pair(amount: str | float) -> tuple[str, int]:
    dec = format(amount, "f") if not isinstance(amount, str) else amount
    if "." not in dec:
        dec = f"{dec}.00"
    return dec, decimal_to_minor(dec, "EUR")


def _usd_pair(amount: str | float) -> tuple[str, int]:
    dec = format(amount, "f") if not isinstance(amount, str) else amount
    return dec, decimal_to_minor(dec, "USD")


def _field_value(preview: dict[str, Any], key: str, default: Any = None) -> Any:
    meta = (preview.get("fields") or {}).get(key)
    if not meta:
        return default
    return meta.get("value", default)


def _map_deal_status(preview: dict[str, Any]) -> str:
    raw = str(_field_value(preview, "deal_status", "logistics_pending") or "")
    mapped = _COMPOSITE_DEAL_STATUS_MAP.get(raw, raw)
    if mapped in DEAL_STATUSES:
        return mapped
    return "logistics_pending"


def default_preview_path(deal_key: str, pipeline_root: Path | None = None) -> Path:
    root = pipeline_root or Path(__file__).resolve().parents[3]
    return root / "reports/out/active/current/commercial_deals_preview" / f"{deal_key}.json"


def iter_plan_entity_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten planned upsert rows from a plan dict (for validation/tests)."""
    rows: list[dict[str, Any]] = []
    for key in (
        "commercial_product",
        "commercial_product_alias",
        "commercial_deal_evidence",
        "commercial_deal_document",
        "commercial_deal_payment",
        "commercial_deal_line",
        "commercial_deal_cost",
        "commercial_deal_event",
        "commercial_deal_field_evidence",
    ):
        rows.extend(plan.get(key) or [])
    for singleton in ("commercial_deal", "commercial_deal_review"):
        row = plan.get(singleton)
        if row:
            rows.append(row)
    return rows


def plan_contains_forbidden_columns(plan: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for row in iter_plan_entity_rows(plan):
        for key in row.get("columns") or {}:
            if key in _FORBIDDEN_ROW_KEYS:
                found.append(key)
    return found


def _plan_row(
    *,
    upsert_key: dict[str, Any],
    columns: dict[str, Any],
    ref: str,
    action: str = "upsert",
) -> dict[str, Any]:
    for key in columns:
        if key in _FORBIDDEN_ROW_KEYS:
            raise ValueError(f"forbidden column in plan row: {key}")
    return {
        "ref": ref,
        "action": action,
        "upsert_key": upsert_key,
        "columns": columns,
    }


@dataclass
class DealPromotionPlan:
    deal_key: str
    mode: str
    deal_action: str
    source_preview_path: str
    source_preview_sha256: str
    schema_version: str
    parser_version: str
    confirmed_facts_version: str
    commercial_product: list[dict[str, Any]] = field(default_factory=list)
    commercial_product_alias: list[dict[str, Any]] = field(default_factory=list)
    commercial_deal: dict[str, Any] | None = None
    commercial_deal_evidence: list[dict[str, Any]] = field(default_factory=list)
    commercial_deal_document: list[dict[str, Any]] = field(default_factory=list)
    commercial_deal_payment: list[dict[str, Any]] = field(default_factory=list)
    commercial_deal_line: list[dict[str, Any]] = field(default_factory=list)
    commercial_deal_cost: list[dict[str, Any]] = field(default_factory=list)
    commercial_deal_event: list[dict[str, Any]] = field(default_factory=list)
    commercial_deal_field_evidence: list[dict[str, Any]] = field(default_factory=list)
    commercial_deal_review: dict[str, Any] | None = None
    reconciliation: dict[str, Any] = field(default_factory=dict)
    gross_margin: dict[str, Any] = field(default_factory=dict)
    idempotency: dict[str, Any] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "deal_key": self.deal_key,
            "mode": self.mode,
            "schema_version": self.schema_version,
            "parser_version": self.parser_version,
            "confirmed_facts_version": self.confirmed_facts_version,
            "source_preview_path": self.source_preview_path,
            "source_preview_sha256": self.source_preview_sha256,
            "deal_action": self.deal_action,
            "idempotency": self.idempotency,
            "reconciliation": self.reconciliation,
            "gross_margin": self.gross_margin,
            "counts": self.counts,
            "commercial_product": self.commercial_product,
            "commercial_product_alias": self.commercial_product_alias,
            "commercial_deal": self.commercial_deal,
            "commercial_deal_evidence": self.commercial_deal_evidence,
            "commercial_deal_document": self.commercial_deal_document,
            "commercial_deal_payment": self.commercial_deal_payment,
            "commercial_deal_line": self.commercial_deal_line,
            "commercial_deal_cost": self.commercial_deal_cost,
            "commercial_deal_event": self.commercial_deal_event,
            "commercial_deal_field_evidence": self.commercial_deal_field_evidence,
            "commercial_deal_review": self.commercial_deal_review,
        }


def _reconciliation_block(preview: dict[str, Any]) -> dict[str, Any]:
    block = dict(preview.get("reconciliation") or {})
    if block:
        return block
    inv = str(SUPPLIER_INVOICE_TOTAL_EUR)
    freight = str(SUPPLIER_FREIGHT_QUOTED_EUR)
    paid = str(SUPPLIER_AMOUNT_PAID_EUR)
    return {
        "reconciliation_status": "reconciled_excluding_supplier_freight",
        "supplier_invoice_total_eur": inv,
        "supplier_freight_quoted_eur": freight,
        "supplier_amount_paid_eur": paid,
        "expected_payment_excluding_freight_eur": paid,
        "arithmetic": f"{inv} - {freight} = {paid}",
        "freight_excluded_from_wire": True,
    }


def _existing_deal_id(conn: sqlite3.Connection, deal_key: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM commercial_deal WHERE deal_key = ? LIMIT 1",
        (deal_key,),
    ).fetchone()
    return int(row[0]) if row else None


def build_deal_promotion_plan(
    preview: dict[str, Any],
    *,
    preview_path: Path,
    preview_sha256: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> DealPromotionPlan:
    """Build a dry-run promotion plan from operator preview JSON (SERVA/CEAF v1)."""
    deal_key = str(preview.get("deal_key") or "")
    if not deal_key:
        raise ValueError("preview missing deal_key")

    sha = preview_sha256 or sha256_file(preview_path)
    ts = now_iso()
    deal_action = "insert"
    existing_id: int | None = None
    if conn is not None:
        existing_id = _existing_deal_id(conn, deal_key)
        if existing_id is not None:
            deal_action = "update"

    supplier = preview.get("supplier") or {}
    client = preview.get("client") or {}
    client_emails = client.get("contact_emails") or []
    vat = build_client_vat_breakdown()

    inv_dec, inv_minor = _eur_pair(str(SUPPLIER_INVOICE_TOTAL_EUR))
    paid_dec, paid_minor = _eur_pair(str(SUPPLIER_AMOUNT_PAID_EUR))
    prod_dec, prod_minor = _eur_pair(str(SUPPLIER_PRODUCT_COST_EUR))
    hand_dec, hand_minor = _eur_pair(str(SUPPLIER_HANDLING_COST_EUR))
    freight_dec, freight_minor = _eur_pair(str(SUPPLIER_FREIGHT_QUOTED_EUR))
    wise_usd_dec, wise_usd_minor = _usd_pair(str(WISE_TOTAL_PAID_USD))

    plan = DealPromotionPlan(
        deal_key=deal_key,
        mode="dry_run",
        deal_action=deal_action,
        source_preview_path=str(preview_path.resolve()),
        source_preview_sha256=sha,
        schema_version=COMMERCIAL_DEAL_SCHEMA_VERSION,
        parser_version=PARSER_VERSION,
        confirmed_facts_version=CONFIRMED_FACTS_VERSION,
        reconciliation=_reconciliation_block(preview),
        gross_margin=dict(preview.get("gross_margin") or {"status": "needs_review", "margin_status": "needs_review"}),
        idempotency={
            "commercial_deal": {"upsert_key": "deal_key", "deal_key": deal_key},
            "commercial_product": {"upsert_key": "ref_code"},
            "commercial_product_alias": {"upsert_key": ["alias_source", "alias_code"]},
            "commercial_deal_line": {"upsert_key": ["deal_key", "side", "line_number"]},
            "commercial_deal_cost": {"upsert_key": ["deal_key", "cost_kind"]},
            "commercial_deal_payment": {
                "upsert_key": ["deal_key", "direction", "payment_method", "paid_at"]
            },
            "commercial_deal_document": {"upsert_key": ["deal_key", "document_type", "doc_number"]},
            "commercial_deal_event": {"upsert_key": ["deal_key", "event_type", "event_at"]},
            "commercial_deal_evidence": {
                "upsert_key": ["deal_key", "evidence_kind", "email_id", "attachment_id", "source_path"]
            },
            "commercial_deal_field_evidence": {
                "upsert_key": ["entity_table", "entity_id", "field_name", "created_at"]
            },
            "existing_deal_id": existing_id,
        },
    )

    # Products
    products = [
        {
            "ref_code": "004250001",
            "brand": "SERVA",
            "name": "BlueSlick™ 250 ml",
            "category": "electrophoresis_reagent",
            "subcategory": "lab_consumable",
            "is_hazardous": 0,
            "requires_special_shipping": 0,
            "unit": "250 ml",
        },
        {
            "ref_code": "003593002",
            "brand": "SERVA",
            "name": "N,N,N',N'-Tetramethyl-ethylenediamine 25 ml",
            "category": "electrophoresis_reagent",
            "subcategory": "chemical_reagent",
            "is_hazardous": 0,
            "requires_special_shipping": 1,
            "unit": "25 ml",
        },
    ]
    for p in products:
        plan.commercial_product.append(
            _plan_row(
                ref=f"product:{p['ref_code']}",
                upsert_key={"ref_code": p["ref_code"]},
                columns={**p, "is_active": 1, "created_at": ts, "updated_at": ts},
            )
        )
    for product_ref, alias_code, alias_source in (
        ("004250001", "4250001", "serva"),
        ("004250001", "4250001", "ceaf"),
        ("003593002", "3593002", "serva"),
        ("003593002", "3593002", "ceaf"),
    ):
        plan.commercial_product_alias.append(
            _plan_row(
                ref=f"alias:{alias_source}:{alias_code}",
                upsert_key={"alias_source": alias_source, "alias_code": alias_code},
                columns={
                    "product_ref": product_ref,
                    "alias_code": alias_code,
                    "alias_source": alias_source,
                    "created_at": ts,
                },
            )
        )

    # Evidence (metadata only — no bodies)
    plan.commercial_deal_evidence.append(
        _plan_row(
            ref="evidence:preview_source",
            upsert_key={
                "deal_key": deal_key,
                "evidence_kind": "preview_json",
                "source_path": str(preview_path.resolve()),
            },
            columns={
                "deal_key": deal_key,
                "evidence_kind": "preview_json",
                "source_path": str(preview_path.resolve()),
                "operator_note": f"Promotion source preview sha256={sha}",
                "confidence": "operator_confirmed",
                "created_at": ts,
            },
        )
    )
    for em in (preview.get("evidence") or {}).get("emails") or []:
        if not em.get("known_hint") and (em.get("relevance_score") or 0) < 5:
            continue
        eid = em.get("email_id")
        if eid is None:
            continue
        plan.commercial_deal_evidence.append(
            _plan_row(
                ref=f"evidence:email:{eid}",
                upsert_key={
                    "deal_key": deal_key,
                    "evidence_kind": "email",
                    "email_id": eid,
                },
                columns={
                    "deal_key": deal_key,
                    "evidence_kind": "email",
                    "email_id": int(eid),
                    "email_subject": (em.get("subject") or "")[:200],
                    "email_date_iso": em.get("date_iso"),
                    "confidence": "operator_confirmed",
                    "created_at": ts,
                },
            )
        )
    for att in (preview.get("evidence") or {}).get("attachments") or []:
        if not att.get("known_hint"):
            continue
        aid = att.get("attachment_id")
        if aid is None:
            continue
        plan.commercial_deal_evidence.append(
            _plan_row(
                ref=f"evidence:attachment:{aid}",
                upsert_key={
                    "deal_key": deal_key,
                    "evidence_kind": "attachment",
                    "attachment_id": aid,
                },
                columns={
                    "deal_key": deal_key,
                    "evidence_kind": "attachment",
                    "attachment_id": int(aid),
                    "filename": att.get("filename"),
                    "confidence": "operator_confirmed",
                    "created_at": ts,
                },
            )
        )

    # Deal header
    plan.commercial_deal = _plan_row(
        ref="deal",
        upsert_key={"deal_key": deal_key},
        action=deal_action,
        columns={
            "deal_key": deal_key,
            "title": f"SERVA → CEAF OC {CLIENT_PO_NUMBER}",
            "deal_status": _map_deal_status(preview),
            "margin_status": "needs_review",
            "reconciliation_status": str(
                _field_value(preview, "reconciliation_status", "reconciled_excluding_supplier_freight")
            ),
            "freight_status": str(
                _field_value(preview, "freight_status", "dhl_account_or_external_freight")
            ),
            "client_org_name": client.get("org") or "CEAF",
            "client_domain": client.get("domain") or "ceaf.cl",
            "client_contact_email": client_emails[0] if client_emails else None,
            "client_po_number": str(_field_value(preview, "client_po_number", CLIENT_PO_NUMBER)),
            "client_invoice_number": str(_field_value(preview, "client_invoice_number", "6")),
            "supplier_org_name": supplier.get("org"),
            "supplier_domain": supplier.get("domain"),
            "supplier_contact_email": supplier.get("contact_email"),
            "supplier_customer_code": str(_field_value(preview, "supplier_customer_code", "310471")),
            "supplier_po_number": str(_field_value(preview, "supplier_po_number", "174-26")),
            "supplier_invoice_number": SUPPLIER_PROFORMA_NUMBER,
            "client_sale_net_clp": CLIENT_SALE_AMOUNT_NET_CLP,
            "client_iva_amount_clp": CLIENT_IVA_AMOUNT_CLP,
            "client_iva_rate": float(CLIENT_IVA_RATE),
            "client_sale_gross_clp": CLIENT_SALE_AMOUNT_GROSS_CLP,
            "client_payment_received_clp": CLIENT_PAYMENT_RECEIVED_CLP,
            "supplier_invoice_total_decimal": inv_dec,
            "supplier_invoice_total_minor": inv_minor,
            "supplier_amount_paid_decimal": paid_dec,
            "supplier_amount_paid_minor": paid_minor,
            "schema_version": COMMERCIAL_DEAL_SCHEMA_VERSION,
            "source_preview_path": str(preview_path.resolve()),
            "source_preview_sha256": sha,
            "parser_version": PARSER_VERSION,
            "confirmed_facts_version": CONFIRMED_FACTS_VERSION,
            "margin_net_clp": None,
            "confidence": "operator_confirmed",
            "notes_json": json.dumps(
                {"preview_generated_at": preview.get("generated_at")},
                ensure_ascii=False,
            ),
            "created_at": ts,
            "updated_at": ts,
        },
    )

    # Documents
    doc_specs = [
        ("doc:client_po", "client_po", CLIENT_PO_NUMBER, "OC N º 26172.pdf", None, None),
        ("doc:client_invoice", "client_invoice", "6", "Factura N°6.pdf", None, None),
        (
            "doc:supplier_proforma",
            "supplier_proforma",
            SUPPLIER_PROFORMA_NUMBER,
            "A2602545 OrigenLab.pdf",
            inv_dec,
            inv_minor,
        ),
        (
            "doc:wise_voucher",
            "payment_voucher",
            SUPPLIER_PAYMENT_TRANSFER_ID,
            "wise_transfer_confirmation__transfer__2152655677.pdf",
            paid_dec,
            paid_minor,
        ),
    ]
    for ref, dtype, doc_num, filename, amt_dec, amt_minor in doc_specs:
        cols: dict[str, Any] = {
            "deal_key": deal_key,
            "document_type": dtype,
            "doc_number": doc_num,
            "filename": filename,
            "confidence": "operator_confirmed",
            "evidence_ref": "evidence:preview_source",
            "created_at": ts,
        }
        if amt_dec is not None:
            cols["currency"] = "EUR"
            cols["amount_decimal"] = amt_dec
            cols["amount_minor"] = amt_minor
        if dtype == "supplier_proforma":
            cols["issued_at"] = f"{SUPPLIER_PROFORMA_DATE}T12:00:00+02:00"
        plan.commercial_deal_document.append(
            _plan_row(
                ref=ref,
                upsert_key={"deal_key": deal_key, "document_type": dtype, "doc_number": doc_num},
                columns=cols,
            )
        )

    # Payments
    plan.commercial_deal_payment.append(
        _plan_row(
            ref="payment:inbound",
            upsert_key={
                "deal_key": deal_key,
                "direction": "inbound",
                "payment_method": "bank_transfer",
                "paid_at": CLIENT_PAYMENT_AT,
            },
            columns={
                "deal_key": deal_key,
                "direction": "inbound",
                "payment_method": "bank_transfer",
                "paid_at": CLIENT_PAYMENT_AT,
                "currency": "CLP",
                "amount_gross_integer": CLIENT_PAYMENT_RECEIVED_CLP,
                "amount_net_integer": CLIENT_SALE_AMOUNT_NET_CLP,
                "iva_amount_integer": CLIENT_IVA_AMOUNT_CLP,
                "subject": "FACTURA 6",
                "counterparty_email": "fgonzalez@ceaf.cl",
                "confidence": "operator_confirmed",
                "evidence_ref": "evidence:preview_source",
                "created_at": ts,
            },
        )
    )
    plan.commercial_deal_payment.append(
        _plan_row(
            ref="payment:outbound",
            upsert_key={
                "deal_key": deal_key,
                "direction": "outbound",
                "payment_method": "wise",
                "paid_at": WISE_FUNDED_AT,
            },
            columns={
                "deal_key": deal_key,
                "direction": "outbound",
                "payment_method": "wise",
                "paid_at": WISE_FUNDED_AT,
                "currency": "EUR",
                "amount_decimal": paid_dec,
                "amount_minor": paid_minor,
                "secondary_currency": "USD",
                "secondary_amount_decimal": wise_usd_dec,
                "secondary_amount_minor": wise_usd_minor,
                "transfer_id": SUPPLIER_PAYMENT_TRANSFER_ID,
                "counterparty_email": "order@serva.de",
                "confidence": "operator_confirmed",
                "evidence_ref": "evidence:preview_source",
                "created_at": ts,
            },
        )
    )

    # Client lines from VAT breakdown
    line_no = 0
    for line in vat["lines"]:
        line_no += 1
        kind = "shipping" if line.get("ref_code") == "E01" else "product"
        ref_code = line.get("ref_code", "")
        canonical = "004250001" if ref_code == "4250001" else "003593002" if ref_code == "3593002" else ref_code
        plan.commercial_deal_line.append(
            _plan_row(
                ref=f"line:client:{line_no}",
                upsert_key={"deal_key": deal_key, "side": "client", "line_number": line_no},
                columns={
                    "deal_key": deal_key,
                    "line_number": line_no,
                    "side": "client",
                    "line_kind": kind,
                    "product_ref": canonical if kind == "product" else None,
                    "ref_code": ref_code,
                    "description": line["description"],
                    "brand": "SERVA" if kind == "product" else None,
                    "quantity": "1",
                    "currency": "CLP",
                    "line_net_amount": int(line["net_clp"]),
                    "confidence": "operator_confirmed",
                    "evidence_ref": "evidence:preview_source",
                    "created_at": ts,
                },
            )
        )

    # Costs
    cost_specs = [
        ("supplier_product", "SERVA product lines (BlueSlick + TEMED)", prod_dec, prod_minor, 0, "doc:supplier_proforma", None),
        ("supplier_handling", "SERVA handling fees", hand_dec, hand_minor, 0, "doc:supplier_proforma", None),
        (
            "supplier_freight_quoted",
            "SERVA freight quoted (excluded from Wise wire)",
            freight_dec,
            freight_minor,
            1,
            "doc:supplier_proforma",
            None,
        ),
    ]
    for kind, desc, dec, minor, excluded, doc_ref, pay_ref in cost_specs:
        plan.commercial_deal_cost.append(
            _plan_row(
                ref=f"cost:{kind}",
                upsert_key={"deal_key": deal_key, "cost_kind": kind},
                columns={
                    "deal_key": deal_key,
                    "cost_kind": kind,
                    "description": desc,
                    "currency": "EUR",
                    "amount_decimal": dec,
                    "amount_minor": minor,
                    "document_ref": doc_ref,
                    "payment_ref": pay_ref,
                    "is_estimated": 0,
                    "excluded_from_supplier_wire": excluded,
                    "confidence": "operator_confirmed",
                    "evidence_ref": "evidence:preview_source",
                    "created_at": ts,
                    "updated_at": ts,
                },
            )
        )

    # Events
    for ev in build_confirmed_events():
        payload = {k: v for k, v in ev.items() if k not in ("event_type", "event_at", "summary", "confidence")}
        plan.commercial_deal_event.append(
            _plan_row(
                ref=f"event:{ev['event_type']}",
                upsert_key={
                    "deal_key": deal_key,
                    "event_type": ev["event_type"],
                    "event_at": ev["event_at"],
                },
                columns={
                    "deal_key": deal_key,
                    "event_type": ev["event_type"],
                    "event_at": ev["event_at"],
                    "actor_email": ev.get("actor_email"),
                    "counterparty_email": ev.get("counterparty_email"),
                    "subject": ev.get("subject"),
                    "summary": ev["summary"],
                    "payload_json": json.dumps(payload, ensure_ascii=False, default=str),
                    "confidence": ev.get("confidence", "operator_confirmed"),
                    "created_at": ts,
                },
            )
        )

    # Field-level evidence for key deal columns
    field_specs = [
        ("client_sale_net_clp", str(CLIENT_SALE_AMOUNT_NET_CLP)),
        ("client_iva_amount_clp", str(CLIENT_IVA_AMOUNT_CLP)),
        ("client_sale_gross_clp", str(CLIENT_SALE_AMOUNT_GROSS_CLP)),
        ("client_payment_received_clp", str(CLIENT_PAYMENT_RECEIVED_CLP)),
        ("supplier_invoice_total_decimal", inv_dec),
        ("supplier_amount_paid_decimal", paid_dec),
        ("reconciliation_status", str(plan.commercial_deal["columns"]["reconciliation_status"])),
    ]
    for fname, norm in field_specs:
        plan.commercial_deal_field_evidence.append(
            _plan_row(
                ref=f"field:deal:{fname}",
                upsert_key={
                    "entity_table": "commercial_deal",
                    "entity_key": deal_key,
                    "field_name": fname,
                },
                columns={
                    "deal_key": deal_key,
                    "entity_table": "commercial_deal",
                    "entity_key": deal_key,
                    "field_name": fname,
                    "normalized_value": norm,
                    "extracted_value": norm,
                    "evidence_ref": "evidence:preview_source",
                    "confidence": "operator_confirmed",
                    "parser_name": "operator_confirmed",
                    "parser_version": CONFIRMED_FACTS_VERSION,
                    "operator_confirmed": 1,
                    "created_at": ts,
                },
            )
        )

    plan.commercial_deal_review = _plan_row(
        ref="review:initial",
        upsert_key={"deal_key": deal_key, "outcome": "approved"},
        columns={
            "deal_key": deal_key,
            "reviewer": "operator",
            "outcome": "approved",
            "reason_code": "preview_promotion_dry_run",
            "reason_text": "Dry-run plan generated from operator-confirmed SERVA/CEAF preview.",
            "fields_reviewed_json": json.dumps(
                ["client_sale_net_clp", "supplier_amount_paid_decimal", "reconciliation_status"],
                ensure_ascii=False,
            ),
            "schema_version": COMMERCIAL_DEAL_SCHEMA_VERSION,
            "source_preview_path": str(preview_path.resolve()),
            "source_preview_sha256": sha,
            "parser_version": PARSER_VERSION,
            "confirmed_facts_version": CONFIRMED_FACTS_VERSION,
            "created_at": ts,
        },
    )

    plan.counts = {
        "commercial_product": len(plan.commercial_product),
        "commercial_product_alias": len(plan.commercial_product_alias),
        "commercial_deal": 1 if plan.commercial_deal else 0,
        "commercial_deal_evidence": len(plan.commercial_deal_evidence),
        "commercial_deal_document": len(plan.commercial_deal_document),
        "commercial_deal_payment": len(plan.commercial_deal_payment),
        "commercial_deal_line": len(plan.commercial_deal_line),
        "commercial_deal_cost": len(plan.commercial_deal_cost),
        "commercial_deal_event": len(plan.commercial_deal_event),
        "commercial_deal_field_evidence": len(plan.commercial_deal_field_evidence),
        "commercial_deal_review": 1 if plan.commercial_deal_review else 0,
    }
    return plan


def build_plan_for_deal_key(
    deal_key: str,
    *,
    preview_path: Path | None = None,
    pipeline_root: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> DealPromotionPlan:
    path = preview_path or default_preview_path(deal_key, pipeline_root)
    if not path.is_file():
        raise FileNotFoundError(f"preview JSON not found: {path}")
    preview = load_preview_json(path)
    if str(preview.get("deal_key") or "") != deal_key:
        raise ValueError(f"preview deal_key mismatch: expected {deal_key!r}, got {preview.get('deal_key')!r}")
    return build_deal_promotion_plan(preview, preview_path=path, conn=conn)


def build_serva_ceaf_plan_from_default_preview(
    preview_root: Path | None = None,
    *,
    pipeline_root: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> DealPromotionPlan:
    root = pipeline_root or preview_root
    return build_plan_for_deal_key(SERVA_CEAF_DEAL_KEY, pipeline_root=root, conn=conn)


def validate_apply_args(
    *,
    apply: bool,
    sqlite_db: Path | None,
    deal_key: str | None,
    understand_writes: bool,
) -> str | None:
    """Return an error message when --apply prerequisites are missing; None if OK."""
    if not apply:
        return None
    if sqlite_db is None:
        return "--apply requires --sqlite-db PATH"
    if not deal_key:
        return "--apply requires --deal-key"
    if not understand_writes:
        return "--apply requires --i-understand-this-writes-sqlite"
    return None


_SAFE_DB_DIR_NAMES: frozenset[str] = frozenset(
    {
        "backup",
        "backups",
        "dev",
        "scratch",
        "fixture",
        "fixtures",
        "pytest-of",
    }
)

_PRODUCTION_DB_BASENAMES: frozenset[str] = frozenset(
    {"emails.sqlite", "email.sqlite", "origenlab.sqlite"}
)


def _sqlite_path_is_ephemeral_or_dev(resolved: Path) -> bool:
    parts_lower = [p.lower() for p in resolved.parts]
    return any(part in _SAFE_DB_DIR_NAMES for part in parts_lower)


def _looks_like_production_layout(resolved: Path) -> bool:
    if resolved.name.lower() not in _PRODUCTION_DB_BASENAMES:
        return False
    if _sqlite_path_is_ephemeral_or_dev(resolved):
        return False
    parts_lower = [p.lower() for p in resolved.parts]
    if len(parts_lower) >= 2 and parts_lower[-2] == "sqlite":
        return True
    return True


def connect_sqlite_rw(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path.expanduser().resolve()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _resolved_production_sqlite_paths() -> list[Path]:
    paths: list[Path] = []
    env = (os.environ.get("ORIGENLAB_SQLITE_PATH") or "").strip()
    if env:
        paths.append(Path(env).expanduser().resolve())
    try:
        from origenlab_email_pipeline.config import load_settings

        paths.append(load_settings().resolved_sqlite_path().expanduser().resolve())
    except Exception:
        pass
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def validate_sqlite_apply_target(
    sqlite_db: Path,
    *,
    allow_production: bool = False,
) -> str | None:
    """Refuse production-like SQLite paths unless allow_production is set."""
    if allow_production:
        return None
    resolved = sqlite_db.expanduser().resolve()
    if not resolved.parent.is_dir():
        return f"parent directory missing: {resolved.parent}"
    for prod in _resolved_production_sqlite_paths():
        if resolved == prod:
            return f"refusing to write production SQLite: {resolved}"
    if _looks_like_production_layout(resolved):
        return f"refusing path that looks like production SQLite: {resolved}"
    return None


def _column_names_cached(conn: sqlite3.Connection) -> dict[str, set[str]]:
    return {name: set(table_column_names(conn, name)) for name in COMMERCIAL_DEAL_TABLE_NAMES}


def _filter_db_columns(columns: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in columns.items():
        if key in _FORBIDDEN_ROW_KEYS:
            raise ValueError(f"forbidden column in apply row: {key}")
        if any(sub in key for sub in _FORBIDDEN_BODY_COLUMN_SUBSTRINGS):
            raise ValueError(f"forbidden body-like column in apply row: {key}")
        if key not in allowed:
            continue
        out[key] = value
    return out


def _product_id_by_ref(conn: sqlite3.Connection, ref_code: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM commercial_product WHERE ref_code = ? LIMIT 1",
        (ref_code,),
    ).fetchone()
    return int(row[0]) if row else None


@dataclass
class DealPromotionApplyResult:
    deal_id: int
    deal_key: str
    deal_action: str
    inserted: dict[str, int]
    updated: dict[str, int]
    row_counts: dict[str, int]
    foreign_key_check_ok: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "deal_id": self.deal_id,
            "deal_key": self.deal_key,
            "deal_action": self.deal_action,
            "inserted": dict(self.inserted),
            "updated": dict(self.updated),
            "row_counts": dict(self.row_counts),
            "foreign_key_check_ok": self.foreign_key_check_ok,
        }


def _upsert_product(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    allowed: set[str],
    ref_ids: dict[str, int],
    inserted: dict[str, int],
    updated: dict[str, int],
) -> None:
    cols = _filter_db_columns(row["columns"], allowed)
    ref_code = str(cols["ref_code"])
    existing = _product_id_by_ref(conn, ref_code)
    if existing is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_product ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        pid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        inserted["commercial_product"] += 1
    else:
        upd = {k: v for k, v in cols.items() if k not in ("ref_code", "created_at")}
        set_clause = ", ".join(f"{k}=?" for k in upd)
        conn.execute(
            f"UPDATE commercial_product SET {set_clause} WHERE id=?",
            (*upd.values(), existing),
        )
        pid = existing
        updated["commercial_product"] += 1
    ref_ids[row["ref"]] = pid
    ref_ids[f"product:{ref_code}"] = pid


def _upsert_product_alias(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    allowed: set[str],
    ref_ids: dict[str, int],
    inserted: dict[str, int],
    updated: dict[str, int],
) -> None:
    cols = dict(row["columns"])
    product_ref = str(cols.pop("product_ref", ""))
    product_id = ref_ids.get(f"product:{product_ref}") or _product_id_by_ref(conn, product_ref)
    if product_id is None:
        raise ValueError(f"product_ref not found for alias: {product_ref!r}")
    cols["product_id"] = product_id
    cols = _filter_db_columns(cols, allowed)
    existing = conn.execute(
        """
        SELECT id FROM commercial_product_alias
        WHERE alias_source = ? AND alias_code = ?
        LIMIT 1
        """,
        (cols["alias_source"], cols["alias_code"]),
    ).fetchone()
    if existing is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_product_alias ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        inserted["commercial_product_alias"] += 1
    else:
        conn.execute(
            "UPDATE commercial_product_alias SET product_id = ? WHERE id = ?",
            (product_id, int(existing[0])),
        )
        updated["commercial_product_alias"] += 1


def _upsert_deal(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    allowed: set[str],
    ref_ids: dict[str, int],
    inserted: dict[str, int],
    updated: dict[str, int],
) -> tuple[int, str]:
    cols = _filter_db_columns(row["columns"], allowed)
    deal_key = str(cols["deal_key"])
    existing = _existing_deal_id(conn, deal_key)
    if existing is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_deal ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        deal_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        inserted["commercial_deal"] += 1
        action = "insert"
    else:
        upd = {k: v for k, v in cols.items() if k not in ("deal_key", "created_at")}
        set_clause = ", ".join(f"{k}=?" for k in upd)
        conn.execute(
            f"UPDATE commercial_deal SET {set_clause} WHERE id=?",
            (*upd.values(), existing),
        )
        deal_id = existing
        updated["commercial_deal"] += 1
        action = "update"
    ref_ids[row["ref"]] = deal_id
    ref_ids["deal"] = deal_id
    ref_ids[f"deal:{deal_key}"] = deal_id
    return deal_id, action


def _resolve_evidence_id(
    conn: sqlite3.Connection,
    deal_id: int,
    cols: dict[str, Any],
) -> int | None:
    kind = cols.get("evidence_kind")
    if kind == "preview_json":
        row = conn.execute(
            """
            SELECT id FROM commercial_deal_evidence
            WHERE deal_id = ? AND evidence_kind = 'preview_json' AND source_path = ?
            LIMIT 1
            """,
            (deal_id, cols.get("source_path")),
        ).fetchone()
    elif kind == "email" and cols.get("email_id") is not None:
        row = conn.execute(
            """
            SELECT id FROM commercial_deal_evidence
            WHERE deal_id = ? AND evidence_kind = 'email' AND email_id = ?
            LIMIT 1
            """,
            (deal_id, cols["email_id"]),
        ).fetchone()
    elif kind == "attachment" and cols.get("attachment_id") is not None:
        row = conn.execute(
            """
            SELECT id FROM commercial_deal_evidence
            WHERE deal_id = ? AND evidence_kind = 'attachment' AND attachment_id = ?
            LIMIT 1
            """,
            (deal_id, cols["attachment_id"]),
        ).fetchone()
    else:
        row = None
    return int(row[0]) if row else None


def _upsert_evidence(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    deal_id: int,
    allowed: set[str],
    ref_ids: dict[str, int],
    inserted: dict[str, int],
    updated: dict[str, int],
) -> None:
    cols = dict(row["columns"])
    cols.pop("deal_key", None)
    cols["deal_id"] = deal_id
    cols = _filter_db_columns(cols, allowed)
    existing_id = _resolve_evidence_id(conn, deal_id, cols)
    if existing_id is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_deal_evidence ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        eid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        inserted["commercial_deal_evidence"] += 1
    else:
        upd = {k: v for k, v in cols.items() if k not in ("deal_id", "created_at")}
        set_clause = ", ".join(f"{k}=?" for k in upd)
        conn.execute(
            f"UPDATE commercial_deal_evidence SET {set_clause} WHERE id=?",
            (*upd.values(), existing_id),
        )
        eid = existing_id
        updated["commercial_deal_evidence"] += 1
    ref_ids[row["ref"]] = eid


def _evidence_id_from_ref(ref_ids: dict[str, int], ref: str | None) -> int | None:
    if not ref:
        return None
    return ref_ids.get(ref)


def _upsert_document(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    deal_id: int,
    allowed: set[str],
    ref_ids: dict[str, int],
    inserted: dict[str, int],
    updated: dict[str, int],
) -> None:
    cols = dict(row["columns"])
    evidence_ref = cols.pop("evidence_ref", None)
    cols.pop("deal_key", None)
    evidence_id = _evidence_id_from_ref(ref_ids, evidence_ref)
    if evidence_id is not None:
        cols["evidence_id"] = evidence_id
    cols["deal_id"] = deal_id
    cols = _filter_db_columns(cols, allowed)
    existing = conn.execute(
        """
        SELECT id FROM commercial_deal_document
        WHERE deal_id = ? AND document_type = ? AND doc_number IS ?
        LIMIT 1
        """,
        (deal_id, cols["document_type"], cols.get("doc_number")),
    ).fetchone()
    if existing is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_deal_document ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        did = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        inserted["commercial_deal_document"] += 1
    else:
        upd = {k: v for k, v in cols.items() if k not in ("deal_id", "document_type", "doc_number", "created_at")}
        set_clause = ", ".join(f"{k}=?" for k in upd)
        conn.execute(
            f"UPDATE commercial_deal_document SET {set_clause} WHERE id=?",
            (*upd.values(), int(existing[0])),
        )
        did = int(existing[0])
        updated["commercial_deal_document"] += 1
    ref_ids[row["ref"]] = did


def _upsert_payment(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    deal_id: int,
    allowed: set[str],
    ref_ids: dict[str, int],
    inserted: dict[str, int],
    updated: dict[str, int],
) -> None:
    cols = dict(row["columns"])
    evidence_ref = cols.pop("evidence_ref", None)
    cols.pop("deal_key", None)
    evidence_id = _evidence_id_from_ref(ref_ids, evidence_ref)
    if evidence_id is not None:
        cols["evidence_id"] = evidence_id
    cols["deal_id"] = deal_id
    cols = _filter_db_columns(cols, allowed)
    existing = conn.execute(
        """
        SELECT id FROM commercial_deal_payment
        WHERE deal_id = ? AND direction = ? AND payment_method IS ? AND paid_at IS ?
        LIMIT 1
        """,
        (deal_id, cols["direction"], cols.get("payment_method"), cols.get("paid_at")),
    ).fetchone()
    if existing is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_deal_payment ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        pid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        inserted["commercial_deal_payment"] += 1
    else:
        upd = {
            k: v
            for k, v in cols.items()
            if k
            not in ("deal_id", "direction", "payment_method", "paid_at", "created_at")
        }
        set_clause = ", ".join(f"{k}=?" for k in upd)
        conn.execute(
            f"UPDATE commercial_deal_payment SET {set_clause} WHERE id=?",
            (*upd.values(), int(existing[0])),
        )
        pid = int(existing[0])
        updated["commercial_deal_payment"] += 1
    ref_ids[row["ref"]] = pid


def _upsert_line(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    deal_id: int,
    allowed: set[str],
    ref_ids: dict[str, int],
    inserted: dict[str, int],
    updated: dict[str, int],
) -> None:
    cols = dict(row["columns"])
    evidence_ref = cols.pop("evidence_ref", None)
    cols.pop("deal_key", None)
    product_ref = cols.pop("product_ref", None)
    if product_ref:
        pid = ref_ids.get(f"product:{product_ref}") or _product_id_by_ref(conn, str(product_ref))
        if pid is not None:
            cols["product_id"] = pid
    evidence_id = _evidence_id_from_ref(ref_ids, evidence_ref)
    if evidence_id is not None:
        cols["evidence_id"] = evidence_id
    cols["deal_id"] = deal_id
    cols = _filter_db_columns(cols, allowed)
    existing = conn.execute(
        """
        SELECT id FROM commercial_deal_line
        WHERE deal_id = ? AND side = ? AND line_number = ?
        LIMIT 1
        """,
        (deal_id, cols["side"], cols["line_number"]),
    ).fetchone()
    if existing is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_deal_line ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        inserted["commercial_deal_line"] += 1
    else:
        upd = {
            k: v
            for k, v in cols.items()
            if k not in ("deal_id", "side", "line_number", "created_at")
        }
        set_clause = ", ".join(f"{k}=?" for k in upd)
        conn.execute(
            f"UPDATE commercial_deal_line SET {set_clause} WHERE id=?",
            (*upd.values(), int(existing[0])),
        )
        updated["commercial_deal_line"] += 1


def _upsert_cost(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    deal_id: int,
    allowed: set[str],
    ref_ids: dict[str, int],
    inserted: dict[str, int],
    updated: dict[str, int],
) -> None:
    cols = dict(row["columns"])
    evidence_ref = cols.pop("evidence_ref", None)
    cols.pop("deal_key", None)
    doc_ref = cols.pop("document_ref", None)
    pay_ref = cols.pop("payment_ref", None)
    if doc_ref:
        doc_id = ref_ids.get(str(doc_ref))
        if doc_id is not None:
            cols["document_id"] = doc_id
    if pay_ref:
        pay_id = ref_ids.get(str(pay_ref))
        if pay_id is not None:
            cols["payment_id"] = pay_id
    evidence_id = _evidence_id_from_ref(ref_ids, evidence_ref)
    if evidence_id is not None:
        cols["evidence_id"] = evidence_id
    cols["deal_id"] = deal_id
    cols = _filter_db_columns(cols, allowed)
    existing = conn.execute(
        """
        SELECT id FROM commercial_deal_cost
        WHERE deal_id = ? AND cost_kind = ?
        LIMIT 1
        """,
        (deal_id, cols["cost_kind"]),
    ).fetchone()
    if existing is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_deal_cost ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        inserted["commercial_deal_cost"] += 1
    else:
        upd = {k: v for k, v in cols.items() if k not in ("deal_id", "cost_kind", "created_at")}
        set_clause = ", ".join(f"{k}=?" for k in upd)
        conn.execute(
            f"UPDATE commercial_deal_cost SET {set_clause} WHERE id=?",
            (*upd.values(), int(existing[0])),
        )
        updated["commercial_deal_cost"] += 1


def _upsert_event(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    deal_id: int,
    allowed: set[str],
    inserted: dict[str, int],
    updated: dict[str, int],
) -> None:
    cols = dict(row["columns"])
    cols.pop("deal_key", None)
    cols["deal_id"] = deal_id
    cols = _filter_db_columns(cols, allowed)
    existing = conn.execute(
        """
        SELECT id FROM commercial_deal_event
        WHERE deal_id = ? AND event_type = ? AND event_at = ?
        LIMIT 1
        """,
        (deal_id, cols["event_type"], cols["event_at"]),
    ).fetchone()
    if existing is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_deal_event ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        inserted["commercial_deal_event"] += 1
    else:
        upd = {
            k: v
            for k, v in cols.items()
            if k not in ("deal_id", "event_type", "event_at", "created_at")
        }
        set_clause = ", ".join(f"{k}=?" for k in upd)
        conn.execute(
            f"UPDATE commercial_deal_event SET {set_clause} WHERE id=?",
            (*upd.values(), int(existing[0])),
        )
        updated["commercial_deal_event"] += 1


def _upsert_field_evidence(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    deal_id: int,
    allowed: set[str],
    ref_ids: dict[str, int],
    inserted: dict[str, int],
    updated: dict[str, int],
) -> None:
    cols = dict(row["columns"])
    evidence_ref = cols.pop("evidence_ref", None)
    cols.pop("deal_key", None)
    cols.pop("entity_key", None)
    entity_table = cols.get("entity_table")
    if entity_table == "commercial_deal":
        cols["entity_id"] = deal_id
    evidence_id = _evidence_id_from_ref(ref_ids, evidence_ref)
    if evidence_id is not None:
        cols["evidence_id"] = evidence_id
    cols["deal_id"] = deal_id
    cols = _filter_db_columns(cols, allowed)
    existing = conn.execute(
        """
        SELECT id FROM commercial_deal_field_evidence
        WHERE deal_id = ? AND entity_table = ? AND entity_id = ? AND field_name = ?
        LIMIT 1
        """,
        (deal_id, cols["entity_table"], cols["entity_id"], cols["field_name"]),
    ).fetchone()
    if existing is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_deal_field_evidence ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        inserted["commercial_deal_field_evidence"] += 1
    else:
        upd = {
            k: v
            for k, v in cols.items()
            if k
            not in ("deal_id", "entity_table", "entity_id", "field_name", "created_at")
        }
        set_clause = ", ".join(f"{k}=?" for k in upd)
        conn.execute(
            f"UPDATE commercial_deal_field_evidence SET {set_clause} WHERE id=?",
            (*upd.values(), int(existing[0])),
        )
        updated["commercial_deal_field_evidence"] += 1


def _upsert_review(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    *,
    deal_id: int,
    allowed: set[str],
    inserted: dict[str, int],
    updated: dict[str, int],
) -> None:
    cols = dict(row["columns"])
    cols.pop("deal_key", None)
    cols["deal_id"] = deal_id
    outcome = cols.get("outcome")
    cols = _filter_db_columns(cols, allowed)
    existing = conn.execute(
        """
        SELECT id FROM commercial_deal_review
        WHERE deal_id = ? AND outcome = ?
        LIMIT 1
        """,
        (deal_id, outcome),
    ).fetchone()
    if existing is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_deal_review ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        inserted["commercial_deal_review"] += 1
    else:
        upd = {k: v for k, v in cols.items() if k not in ("deal_id", "outcome", "created_at")}
        set_clause = ", ".join(f"{k}=?" for k in upd)
        conn.execute(
            f"UPDATE commercial_deal_review SET {set_clause} WHERE id=?",
            (*upd.values(), int(existing[0])),
        )
        updated["commercial_deal_review"] += 1


def _deal_row_counts(conn: sqlite3.Connection, deal_id: int) -> dict[str, int]:
    counts: dict[str, int] = {"commercial_deal": 1}
    child_tables = [
        "commercial_deal_evidence",
        "commercial_deal_document",
        "commercial_deal_payment",
        "commercial_deal_line",
        "commercial_deal_cost",
        "commercial_deal_event",
        "commercial_deal_field_evidence",
        "commercial_deal_review",
    ]
    for table in child_tables:
        row = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE deal_id = ?", (deal_id,)).fetchone()
        counts[table] = int(row[0]) if row else 0
    product_refs = conn.execute(
        """
        SELECT DISTINCT p.ref_code
        FROM commercial_deal_line l
        JOIN commercial_product p ON p.id = l.product_id
        WHERE l.deal_id = ?
        """,
        (deal_id,),
    ).fetchall()
    ref_codes = [str(r[0]) for r in product_refs]
    if ref_codes:
        placeholders = ", ".join("?" * len(ref_codes))
        prow = conn.execute(
            f"SELECT COUNT(*) FROM commercial_product WHERE ref_code IN ({placeholders})",
            ref_codes,
        ).fetchone()
        counts["commercial_product"] = int(prow[0]) if prow else 0
        arow = conn.execute(
            f"""
            SELECT COUNT(*) FROM commercial_product_alias a
            JOIN commercial_product p ON p.id = a.product_id
            WHERE p.ref_code IN ({placeholders})
            """,
            ref_codes,
        ).fetchone()
        counts["commercial_product_alias"] = int(arow[0]) if arow else 0
    else:
        counts["commercial_product"] = 0
        counts["commercial_product_alias"] = 0
    return counts


def apply_deal_promotion_plan(conn: sqlite3.Connection, plan: DealPromotionPlan) -> DealPromotionApplyResult:
    """Apply plan rows to SQLite inside a single transaction (idempotent upsert)."""
    if plan.commercial_deal is None:
        raise ValueError("plan missing commercial_deal row")
    ensure_commercial_deal_tables(conn)
    if not commercial_deal_tables_exist(conn):
        raise RuntimeError("commercial_deal tables missing after ensure")

    colmap = _column_names_cached(conn)
    ref_ids: dict[str, int] = {}
    inserted: dict[str, int] = defaultdict(int)
    updated: dict[str, int] = defaultdict(int)

    try:
        conn.execute("BEGIN IMMEDIATE")
        for row in plan.commercial_product:
            _upsert_product(
                conn,
                row,
                allowed=colmap["commercial_product"],
                ref_ids=ref_ids,
                inserted=inserted,
                updated=updated,
            )
        for row in plan.commercial_product_alias:
            _upsert_product_alias(
                conn,
                row,
                allowed=colmap["commercial_product_alias"],
                ref_ids=ref_ids,
                inserted=inserted,
                updated=updated,
            )
        deal_id, deal_action = _upsert_deal(
            conn,
            plan.commercial_deal,
            allowed=colmap["commercial_deal"],
            ref_ids=ref_ids,
            inserted=inserted,
            updated=updated,
        )
        for row in plan.commercial_deal_evidence:
            _upsert_evidence(
                conn,
                row,
                deal_id=deal_id,
                allowed=colmap["commercial_deal_evidence"],
                ref_ids=ref_ids,
                inserted=inserted,
                updated=updated,
            )
        for row in plan.commercial_deal_document:
            _upsert_document(
                conn,
                row,
                deal_id=deal_id,
                allowed=colmap["commercial_deal_document"],
                ref_ids=ref_ids,
                inserted=inserted,
                updated=updated,
            )
        for row in plan.commercial_deal_payment:
            _upsert_payment(
                conn,
                row,
                deal_id=deal_id,
                allowed=colmap["commercial_deal_payment"],
                ref_ids=ref_ids,
                inserted=inserted,
                updated=updated,
            )
        for row in plan.commercial_deal_line:
            _upsert_line(
                conn,
                row,
                deal_id=deal_id,
                allowed=colmap["commercial_deal_line"],
                ref_ids=ref_ids,
                inserted=inserted,
                updated=updated,
            )
        for row in plan.commercial_deal_cost:
            _upsert_cost(
                conn,
                row,
                deal_id=deal_id,
                allowed=colmap["commercial_deal_cost"],
                ref_ids=ref_ids,
                inserted=inserted,
                updated=updated,
            )
        for row in plan.commercial_deal_event:
            _upsert_event(
                conn,
                row,
                deal_id=deal_id,
                allowed=colmap["commercial_deal_event"],
                inserted=inserted,
                updated=updated,
            )
        if plan.commercial_deal_review is not None:
            _upsert_review(
                conn,
                plan.commercial_deal_review,
                deal_id=deal_id,
                allowed=colmap["commercial_deal_review"],
                inserted=inserted,
                updated=updated,
            )
        for row in plan.commercial_deal_field_evidence:
            _upsert_field_evidence(
                conn,
                row,
                deal_id=deal_id,
                allowed=colmap["commercial_deal_field_evidence"],
                ref_ids=ref_ids,
                inserted=inserted,
                updated=updated,
            )
        fk_ok = foreign_key_check_ok(conn)
        if not fk_ok:
            raise RuntimeError("PRAGMA foreign_key_check reported violations after apply")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    row_counts = _deal_row_counts(conn, deal_id)
    row_counts["commercial_product"] = len(plan.commercial_product)
    row_counts["commercial_product_alias"] = len(plan.commercial_product_alias)

    return DealPromotionApplyResult(
        deal_id=deal_id,
        deal_key=plan.deal_key,
        deal_action=deal_action,
        inserted=dict(inserted),
        updated=dict(updated),
        row_counts=row_counts,
        foreign_key_check_ok=fk_ok,
    )
