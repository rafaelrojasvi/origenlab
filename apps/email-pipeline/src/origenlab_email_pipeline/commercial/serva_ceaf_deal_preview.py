"""Read-only SERVA → CEAF deal preview from local SQLite (no writes, no Gmail)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.commercial.deal_field_parsers import (
    extraction_to_json,
    parse_ceaf_oc_number,
    parse_client_invoice_number,
    parse_serva_customer_code,
    parse_supplier_payment_eur,
    parse_supplier_po_number,
    parse_supplier_proforma_number,
    reconcile_supplier_payment_excluding_freight,
)
from origenlab_email_pipeline.commercial.deal_preview_redaction import redact_preview_for_public
from origenlab_email_pipeline.commercial.deal_field_parsers import chilean_iva_gross_from_net
from origenlab_email_pipeline.commercial.serva_ceaf_deal_confirmed import (
    CLIENT_IVA_RATE,
    CLIENT_PAYMENT_RECEIVED_CLP,
    CLIENT_SALE_AMOUNT_NET_CLP,
    SUPPLIER_AMOUNT_PAID_EUR,
    SUPPLIER_FREIGHT_QUOTED_EUR,
    SUPPLIER_HANDLING_COST_EUR,
    SUPPLIER_INVOICE_TOTAL_EUR,
    SUPPLIER_PRODUCT_COST_EUR,
    build_client_vat_breakdown,
    build_confirmed_events,
    build_confirmed_fields,
)
from origenlab_email_pipeline.timeutil import now_iso

DEAL_KEY = "serva-ceaf-oc-26172-po-174-26"
MAX_PREVIEW_EMAILS = 40
MAX_PREVIEW_ATTACHMENTS = 80

EMAIL_WHERE_SQL = """
(
  lower(coalesce(e.subject, '')) LIKE '%serva%'
  OR lower(coalesce(e.sender, '')) LIKE '%serva%'
  OR lower(coalesce(e.sender, '')) LIKE '%order@serva.de%'
  OR lower(coalesce(e.recipients, '')) LIKE '%serva%'
  OR lower(coalesce(e.subject, '')) LIKE '%ceaf%'
  OR lower(coalesce(e.sender, '')) LIKE '%ceaf%'
  OR lower(coalesce(e.recipients, '')) LIKE '%ceaf%'
  OR lower(coalesce(e.subject, '')) LIKE '%26172%'
  OR lower(coalesce(e.body_text_clean, '')) LIKE '%26172%'
  OR lower(coalesce(e.subject, '')) LIKE '%174-26%'
  OR lower(coalesce(e.subject, '')) LIKE '%174%26%'
  OR lower(coalesce(e.subject, '')) LIKE '%310471%'
  OR lower(coalesce(e.subject, '')) LIKE '%a2602545%'
  OR lower(coalesce(e.subject, '')) LIKE '%wise%'
  OR lower(coalesce(e.subject, '')) LIKE '%bancochile%'
  OR lower(coalesce(e.subject, '')) LIKE '%factura%'
  OR lower(coalesce(e.subject, '')) LIKE '%int_emp%'
  OR EXISTS (
    SELECT 1 FROM attachments a
    WHERE a.email_id = e.id
      AND (
        lower(coalesce(a.filename, '')) LIKE '%serva%'
        OR lower(coalesce(a.filename, '')) LIKE '%ceaf%'
        OR lower(coalesce(a.filename, '')) LIKE '%26172%'
        OR lower(coalesce(a.filename, '')) LIKE '%a2602545%'
        OR lower(coalesce(a.filename, '')) LIKE '%wise%'
        OR lower(coalesce(a.filename, '')) LIKE '%factura%'
        OR lower(coalesce(a.filename, '')) LIKE '%011728%'
        OR lower(coalesce(a.filename, '')) LIKE '%174%'
      )
  )
)
"""

ATTACHMENT_HINT_FILENAMES: tuple[str, ...] = (
    "OC N º 26172.pdf",
    "Factura N°6.pdf",
    "A2602545 OrigenLab.pdf",
    "wise_transfer_confirmation",
    "CN011728",
)


@dataclass(frozen=True)
class EvidenceEmail:
    email_id: int
    date_iso: str | None
    subject: str | None
    sender: str | None
    folder: str | None
    body_text_snippet: str | None
    match_reason: str


@dataclass(frozen=True)
class EvidenceAttachment:
    attachment_id: int
    email_id: int
    filename: str | None
    doc_type: str | None
    extract_status: str | None
    text_preview_snippet: str | None


def connect_sqlite_readonly(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.expanduser().resolve()
    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _email_body_select_sql(conn: sqlite3.Connection) -> str:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(emails)")}
    if "body_text_clean" in cols:
        return "substr(e.body_text_clean, 1, 500) AS body_text_snippet"
    return "NULL AS body_text_snippet"


def _fetch_evidence_emails(conn: sqlite3.Connection) -> list[EvidenceEmail]:
    if not _table_exists(conn, "emails"):
        return []
    body_col = _email_body_select_sql(conn)
    rows = conn.execute(
        f"""
        SELECT e.id, e.date_iso, e.subject, e.sender, e.folder,
               {body_col}
        FROM emails e
        WHERE {EMAIL_WHERE_SQL}
        ORDER BY e.date_iso DESC
        LIMIT 200
        """
    ).fetchall()
    out: list[EvidenceEmail] = []
    for r in rows:
        subj = (r["subject"] or "").lower()
        sender = (r["sender"] or "").lower()
        reason_parts: list[str] = []
        if "serva" in subj or "serva" in sender:
            reason_parts.append("serva")
        if "ceaf" in subj or "ceaf" in sender:
            reason_parts.append("ceaf")
        if "26172" in subj:
            reason_parts.append("oc_26172")
        if "174" in subj and "26" in subj:
            reason_parts.append("po_174_26")
        if "wise" in subj or "bancochile" in subj or "int_emp" in subj:
            reason_parts.append("payment")
        if not reason_parts:
            reason_parts.append("attachment_or_body_match")
        out.append(
            EvidenceEmail(
                email_id=int(r["id"]),
                date_iso=r["date_iso"],
                subject=r["subject"],
                sender=r["sender"],
                folder=r["folder"] if "folder" in r.keys() else None,
                body_text_snippet=r["body_text_snippet"]
                if "body_text_snippet" in r.keys()
                else None,
                match_reason=",".join(reason_parts),
            )
        )
    return out


def _fetch_evidence_attachments(conn: sqlite3.Connection, email_ids: list[int]) -> list[EvidenceAttachment]:
    if not email_ids or not _table_exists(conn, "attachments"):
        return []
    placeholders = ",".join("?" for _ in email_ids)
    has_extracts = _table_exists(conn, "attachment_extracts")
    has_doc_master = _table_exists(conn, "document_master")
    extract_join = ""
    extract_cols = "NULL AS extract_status, NULL AS text_preview"
    if has_extracts:
        extract_join = "LEFT JOIN attachment_extracts x ON x.attachment_id = a.id"
        extract_cols = "x.extract_status, substr(x.text_preview, 1, 400) AS text_preview"
    doc_type_col = "NULL AS doc_type"
    if has_doc_master:
        doc_type_col = "d.doc_type"
        extract_join += " LEFT JOIN document_master d ON d.attachment_id = a.id"

    rows = conn.execute(
        f"""
        SELECT a.id AS attachment_id, a.email_id, a.filename,
               {doc_type_col},
               {extract_cols}
        FROM attachments a
        {extract_join}
        WHERE a.email_id IN ({placeholders})
        ORDER BY a.email_id DESC, a.id
        """,
        email_ids,
    ).fetchall()
    return [
        EvidenceAttachment(
            attachment_id=int(r["attachment_id"]),
            email_id=int(r["email_id"]),
            filename=r["filename"],
            doc_type=r["doc_type"] if "doc_type" in r.keys() else None,
            extract_status=r["extract_status"],
            text_preview_snippet=r["text_preview"],
        )
        for r in rows
    ]


def _email_relevance_score(e: EvidenceEmail) -> int:
    subj = (e.subject or "").lower()
    sender = (e.sender or "").lower()
    score = 0
    if "serva" in subj or "order@serva.de" in sender:
        score += 4
    if "ceaf" in subj or "ceaf.cl" in sender:
        score += 4
    if "26172" in subj:
        score += 5
    if "174" in subj and "26" in subj:
        score += 5
    if "310471" in subj or (e.body_text_snippet and "310471" in e.body_text_snippet):
        score += 3
    if "a2602545" in subj:
        score += 4
    if "wise" in subj or "bancochile" in subj or "factura" in subj:
        score += 3
    if "po" in subj and "174" in subj:
        score += 2
    return score


def _attachment_relevance_score(a: EvidenceAttachment) -> int:
    fn = (a.filename or "").lower()
    score = 0
    if any(h.lower() in fn for h in ATTACHMENT_HINT_FILENAMES):
        score += 6
    for token in ("26172", "174-26", "174", "a2602545", "wise", "factura", "011728", "serva", "ceaf"):
        if token in fn:
            score += 2
    if a.text_preview_snippet:
        prev = a.text_preview_snippet.lower()
        for token in ("310471", "26172", "174-26", "a2602545", "218", "363", "factura"):
            if token in prev:
                score += 1
    return score


def _rank_and_cap_emails(
    emails: list[EvidenceEmail],
) -> tuple[list[dict[str, object]], bool]:
    ranked = sorted(emails, key=_email_relevance_score, reverse=True)
    truncated = len(ranked) > MAX_PREVIEW_EMAILS
    out = [
        {
            "email_id": e.email_id,
            "date_iso": e.date_iso,
            "subject": e.subject,
            "sender": e.sender,
            "folder": e.folder,
            "match_reason": e.match_reason,
            "relevance_score": _email_relevance_score(e),
        }
        for e in ranked[:MAX_PREVIEW_EMAILS]
    ]
    return out, truncated


def _rank_and_cap_attachments(
    attachments: list[EvidenceAttachment],
) -> tuple[list[dict[str, object]], bool]:
    ranked = sorted(attachments, key=_attachment_relevance_score, reverse=True)
    positive = [a for a in ranked if _attachment_relevance_score(a) > 0]
    pool = positive if len(positive) >= 5 else ranked
    truncated = len(pool) > MAX_PREVIEW_ATTACHMENTS
    out = [
        {
            "attachment_id": a.attachment_id,
            "email_id": a.email_id,
            "filename": a.filename,
            "doc_type": a.doc_type,
            "extract_status": a.extract_status,
            "known_hint": any(
                h.lower() in (a.filename or "").lower() for h in ATTACHMENT_HINT_FILENAMES
            ),
            "relevance_score": _attachment_relevance_score(a),
        }
        for a in pool[:MAX_PREVIEW_ATTACHMENTS]
    ]
    return out, truncated


def _corpus_text(
    emails: list[EvidenceEmail],
    attachments: list[EvidenceAttachment],
    conn: sqlite3.Connection,
) -> str:
    chunks: list[str] = []
    for e in emails:
        chunks.extend([e.subject or "", e.sender or "", e.body_text_snippet or ""])
    for a in attachments:
        chunks.append(a.filename or "")
        if a.text_preview_snippet:
            chunks.append(a.text_preview_snippet)
    if _table_exists(conn, "commercial_purchase_events"):
        row = conn.execute(
            """
            SELECT commercial_summary, net_amount_clp, gross_amount_clp, currency
            FROM commercial_purchase_events
            WHERE oc_number = '26172'
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone()
        if row:
            chunks.append(str(row["commercial_summary"] or ""))
            if row["gross_amount_clp"] is not None:
                chunks.append(f"gross_amount_clp {row['gross_amount_clp']}")
    return "\n".join(chunks)


def _corpus_validation_hints(corpus: str) -> dict[str, dict[str, object] | None]:
    """Optional regex hits from archive — do not override operator-confirmed amounts."""
    return {
        "supplier_customer_code": extraction_to_json(parse_serva_customer_code(corpus)),
        "supplier_po_number": extraction_to_json(parse_supplier_po_number(corpus)),
        "client_po_number": extraction_to_json(parse_ceaf_oc_number(corpus)),
        "supplier_invoice_proforma": extraction_to_json(parse_supplier_proforma_number(corpus)),
        "supplier_amount_paid_eur_corpus": extraction_to_json(parse_supplier_payment_eur(corpus)),
        "client_invoice_number": extraction_to_json(parse_client_invoice_number(corpus)),
    }


def _gross_margin_block() -> dict[str, object]:
    return {
        "status": "needs_review",
        "basis": "client_sale_amount_net_clp_ex_vat",
        "reason": (
            "Margin uses net sale CLP 1,260,000 (ex-IVA), not the IVA-inclusive bank transfer. "
            "Still needs actual CLP cost of Wise payment (USD 268.47 at payment FX) and "
            "DHL/logistics/import costs in CLP."
        ),
        "client_sale_amount_net_clp": CLIENT_SALE_AMOUNT_NET_CLP,
        "client_payment_received_clp": CLIENT_PAYMENT_RECEIVED_CLP,
        "client_iva_amount_clp": 239_400,
        "note_cashflow_vs_margin": (
            "client_payment_received_clp includes 19% IVA; use net for gross margin unless "
            "computing cashflow explicitly."
        ),
        "supplier_amount_paid_eur": str(SUPPLIER_AMOUNT_PAID_EUR),
        "wise_total_paid_usd": "268.47",
        "missing_for_margin": [
            "wise_payment_cost_clp_at_fx",
            "dhl_or_external_freight_cost_clp",
            "import_duties_or_handling_clp_if_any",
        ],
    }


def build_serva_ceaf_deal_preview(conn: sqlite3.Connection) -> dict[str, Any]:
    """Assemble deal preview dict from SQLite (read-only connection)."""
    emails = _fetch_evidence_emails(conn)
    email_ids = [e.email_id for e in emails]
    attachments = _fetch_evidence_attachments(conn, email_ids)
    corpus = _corpus_text(emails, attachments, conn)

    fields = build_confirmed_fields()
    vat_breakdown = build_client_vat_breakdown()
    vat_breakdown["gross_from_net_formula_check"] = (
        chilean_iva_gross_from_net(CLIENT_SALE_AMOUNT_NET_CLP, CLIENT_IVA_RATE)
        == CLIENT_PAYMENT_RECEIVED_CLP
    )
    reconciliation = reconcile_supplier_payment_excluding_freight(
        invoice_total_eur=SUPPLIER_INVOICE_TOTAL_EUR,
        freight_quoted_eur=SUPPLIER_FREIGHT_QUOTED_EUR,
        amount_paid_eur=SUPPLIER_AMOUNT_PAID_EUR,
    )
    # Sanity: product + handling + freight = invoice total
    line_check = (
        SUPPLIER_PRODUCT_COST_EUR + SUPPLIER_HANDLING_COST_EUR + SUPPLIER_FREIGHT_QUOTED_EUR
        == SUPPLIER_INVOICE_TOTAL_EUR
    )

    missing: list[str] = []
    for key, meta in fields.items():
        if meta is None or meta.get("value") is None:
            missing.append(key)

    preview_emails, email_truncated = _rank_and_cap_emails(emails)
    preview_attachments, att_truncated = _rank_and_cap_attachments(attachments)

    preview: dict[str, Any] = {
        "deal_key": DEAL_KEY,
        "generated_at": now_iso(),
        "supplier": {
            "org": "SERVA Electrophoresis GmbH",
            "domain": "serva.de",
            "contact_email": "order@serva.de",
        },
        "client": {
            "org": "CEAF / Centro de Estudios Avanzados en Fruticultura",
            "domain": "ceaf.cl",
            "contact_emails": ["cgaray@ceaf.cl", "fgonzalez@ceaf.cl", "lhidalgo@ceaf.cl"],
        },
        "fields": fields,
        "client_vat_breakdown": vat_breakdown,
        "reconciliation": reconciliation,
        "proforma_line_check": {
            "product_plus_handling_plus_freight_equals_invoice": line_check,
            "product_eur": "148.00",
            "handling_eur": "70.00",
            "freight_eur": "145.00",
            "invoice_total_eur": "363.00",
        },
        "events": build_confirmed_events(),
        "gross_margin": _gross_margin_block(),
        "corpus_validation": _corpus_validation_hints(corpus),
        "evidence": {
            "email_count_total": len(emails),
            "attachment_count_total": len(attachments),
            "email_count_in_preview": len(preview_emails),
            "attachment_count_in_preview": len(preview_attachments),
            "truncated": email_truncated or att_truncated,
            "emails": preview_emails,
            "attachments": preview_attachments,
            "expected_attachment_hints": list(ATTACHMENT_HINT_FILENAMES),
        },
        "missing_fields": missing,
        "safety": {
            "sqlite_mode": "readonly",
            "gmail_mutations": False,
            "db_writes": False,
            "postgres_writes": False,
            "public_export_requires_redaction": True,
        },
    }
    preview["public_export"] = redact_preview_for_public(preview)
    return preview


def write_preview_outputs(
    preview: dict[str, Any],
    out_dir: Path,
) -> tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{preview['deal_key']}.json"
    public_path = out_dir / f"{preview['deal_key']}.public.json"
    csv_path = out_dir / f"{preview['deal_key']}.csv"
    json_path.write_text(json.dumps(preview, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    public = preview.get("public_export") or redact_preview_for_public(preview)
    public_path.write_text(json.dumps(public, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    row = {
        "deal_key": preview["deal_key"],
        "deal_status": _field_value(preview, "deal_status"),
        "client_po": _field_value(preview, "client_po_number"),
        "client_invoice": _field_value(preview, "client_invoice_number"),
        "client_payment_received_clp": _field_value(preview, "client_payment_received_clp"),
        "client_sale_gross_clp": _field_value(preview, "client_sale_amount_gross_clp"),
        "client_sale_net_clp": _field_value(preview, "client_sale_amount_net_clp"),
        "client_iva_clp": _field_value(preview, "client_iva_amount_clp"),
        "client_iva_rate": _field_value(preview, "client_iva_rate"),
        "supplier_po": _field_value(preview, "supplier_po_number"),
        "supplier_customer_code": _field_value(preview, "supplier_customer_code"),
        "supplier_proforma": _field_value(preview, "supplier_invoice_proforma"),
        "supplier_invoice_total_eur": _field_value(preview, "supplier_invoice_total_eur"),
        "supplier_product_cost_eur": _field_value(preview, "supplier_product_cost_eur"),
        "supplier_handling_cost_eur": _field_value(preview, "supplier_handling_cost_eur"),
        "supplier_freight_quoted_eur": _field_value(preview, "supplier_freight_quoted_eur"),
        "supplier_amount_paid_eur": _field_value(preview, "supplier_amount_paid_eur"),
        "wise_total_paid_usd": _field_value(preview, "wise_total_paid_usd"),
        "supplier_payment_method": _field_value(preview, "supplier_payment_method"),
        "supplier_payment_transfer_id": _field_value(preview, "supplier_payment_transfer_id"),
        "freight_status": _field_value(preview, "freight_status"),
        "reconciliation_status": _field_value(preview, "reconciliation_status"),
        "gross_margin_status": (preview.get("gross_margin") or {}).get("status", ""),
        "missing_fields": ";".join(preview.get("missing_fields") or []),
        "email_count": preview["evidence"]["email_count_total"],
        "attachment_count": preview["evidence"]["attachment_count_total"],
    }
    headers = list(row.keys())
    lines = [",".join(headers), ",".join(_csv_cell(row[h]) for h in headers)]
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, csv_path, public_path


def _field_value(preview: dict[str, Any], key: str) -> str:
    meta = (preview.get("fields") or {}).get(key)
    if not meta:
        return ""
    val = meta.get("value")
    return "" if val is None else str(val)


def _csv_cell(val: object) -> str:
    s = "" if val is None else str(val)
    if any(c in s for c in [",", '"', "\n"]):
        return '"' + s.replace('"', '""') + '"'
    return s
