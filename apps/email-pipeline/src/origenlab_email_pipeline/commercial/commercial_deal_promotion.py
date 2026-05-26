"""Build insert/update plans for commercial_deal* tables from operator preview JSON."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    COMMERCIAL_DEAL_SCHEMA_VERSION,
    DEAL_STATUSES,
    decimal_to_minor,
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


APPLY_NOT_IMPLEMENTED_MSG = (
    "SQLite apply for commercial_deal promotion is not implemented until operator approval. "
    "Use dry-run (default) and review the JSON plan output."
)
