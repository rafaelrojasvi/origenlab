"""Heuristic, read-only helpers for QA of «commercial type» labeling on email rows.

These rules are **not** the production classifier; they approximate operator-relevant
buckets for audits. Confidence is explicit (``high_confidence`` … ``needs_manual_review``).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Iterable

from origenlab_email_pipeline.business_mart import (
    domain_of,
    emails_in,
    is_noise_sender,
    primary_sender_email,
)
from origenlab_email_pipeline.marketing_supplier_domains import is_supplier_email_domain

# --- Operational internal domains (QA / counterparty parsing only) ---------------
# Do **not** infer from frequent senders: that mislabels DHL, Mercado Público, etc. as internal.

_DEFAULT_INTERNAL_DOMAINS: frozenset[str] = frozenset({"origenlab.cl", "labdelivery.cl"})

# Env: comma-separated extra internal domains, e.g. "subsidiary.cl,partner.cl"
_ORIGENLAB_INTERNAL_DOMAINS_ENV = "ORIGENLAB_INTERNAL_DOMAINS"


def qa_operational_internal_domains() -> frozenset[str]:
    """Explicit internal domains for QA counterparty parsing (lowercase, no @).

    Defaults: ``origenlab.cl``, ``labdelivery.cl``. Optional merge from
    ``ORIGENLAB_INTERNAL_DOMAINS`` (comma-separated). Does not infer from DB.
    """
    out = set(_DEFAULT_INTERNAL_DOMAINS)
    raw = (os.environ.get(_ORIGENLAB_INTERNAL_DOMAINS_ENV) or "").strip()
    if raw:
        for part in raw.split(","):
            p = part.strip().lower().lstrip("@")
            if p and "." in p:
                out.add(p)
    return frozenset(out)


# --- Marketplace / procurement platforms & logistics / social notifications --------

_MARKETPLACE_PROCUREMENT_ROOTS: frozenset[str] = frozenset(
    {
        "mercadopublico.cl",
        "wherex.com",
    }
)

_LOGISTICS_OR_NOTIFICATION_ROOTS: frozenset[str] = frozenset(
    {
        "dhl.com",
        "facebookmail.com",
        "twitter.com",
    }
)


def _domain_matches_root(dom: str | None, roots: frozenset[str]) -> bool:
    if not dom:
        return False
    d = dom.lower().strip()
    for root in roots:
        if d == root or d.endswith("." + root):
            return True
    return False


def detect_marketplace_or_procurement_platform(
    sender: str | None,
    recipients: str | None,
) -> tuple[bool, str]:
    for e in emails_in(sender or "") + emails_in(recipients or ""):
        dom = domain_of(e)
        if _domain_matches_root(dom, _MARKETPLACE_PROCUREMENT_ROOTS):
            return True, f"platform_domain:{dom}"
    return False, ""


def detect_logistics_or_notification(
    sender: str | None,
    recipients: str | None,
) -> tuple[bool, str]:
    for e in emails_in(sender or "") + emails_in(recipients or ""):
        dom = domain_of(e)
        if _domain_matches_root(dom, _LOGISTICS_OR_NOTIFICATION_ROOTS):
            return True, f"logistics_or_notify_domain:{dom}"
    return False, ""


# --- Keyword / pattern groups (Spanish + English) ---------------------------------

_COTIZ_SENT = re.compile(
    r"\b(cotizaci[oó]n|cotizaciones|cotizacion\b|presupuesto|presupuestos|"
    r"propuesta(\s+comercial|\s+econ[oó]mica)?|oferta(\s+comercial)?|"
    r"quotation|quoted|our\s+quote|"
    r"adjuntamos\s+(la\s+)?cotiz|adjunto\s+(la\s+)?cotiz|"
    r"price\s+list\s+attached|lista\s+de\s+precios)\b",
    re.I,
)

# Strong RFQ / purchase-intent (Chile / Spanish + English)
_QUOTE_STRONG = re.compile(
    r"\b("
    r"orden\s+de\s+compra|\boc\s*[#:]|\boc\b\s*\d+|"
    r"solicitud\s+de\s+cotiz(?:aci[oó]n)?|"
    r"solicito\s+(una\s+)?cotiz(?:aci[oó]n)?|necesito\s+(una\s+)?cotiz(?:aci[oó]n)?|"
    r"pedir(?:nos|me)?\s+cotiz(?:aci[oó]n)?|\bcotizar\b|"
    r"request\s+for\s+quotation|\brfq\b|please\s+quote|send\s+us\s+a\s+quote"
    r")\b",
    re.I,
)

_QUOTE_MEDIUM = re.compile(
    r"\b("
    r"ficha\s+t[eé]cnica|ficha\s+tecnica|"
    r"plazo\s+de\s+entrega|disponibilidad|"
    r"precio|precios|valor|valores|tarifa|tarifas|"
    r"despacho|despachos|"
    r"necesito\s+informaci[oó]n|solicito\s+informaci[oó]n|"
    r"favor\s+enviar|quisiera\s+consultar|requerimos|consulta\s+por|"
    r"compra\b|comprar\b"
    r")\b",
    re.I,
)

_QUOTE_WEAK = re.compile(
    r"\b("
    r"equipo|equipos|insumo|insumos|reactivo|reactivos|"
    r"osm[oó]metro|osmometro|centr[ií]fuga|centrifuga|"
    r"bioreactor|fotobiorreactor|ultraturrax|ultra[-\s]?turrax|"
    r"electroforesis"
    r")\b",
    re.I,
)

# Legacy umbrella + extra Spanish commercial phrasing
_QUOTE_REQUEST = re.compile(
    r"\b(solicitud\s+de\s+cotiz|pedir\s+cotiz|solicito\s+cotiz|"
    r"necesito\s+cotiz|ficha\s+t[eé]cnica|despacho|plazo\s+de\s+entrega|"
    r"disponibilidad|precio|tarifa|"
    r"request\s+for\s+quot|rfq|please\s+quote|send\s+us\s+a\s+quote)\b",
    re.I,
)

_UNIVERSITY = re.compile(
    r"\b(universidad\s+de|uc\.cl|uchile|puc\.|utalca|udec|uach|usach|"
    r"instituto\s+de\s+investigaci[oó]n|centro\s+de\s+investigaci[oó]n|"
    r"laboratorio\s+universitario|"
    r"\bMIT\b|Stanford|Harvard|Oxford|Max\s+Planck)\b",
    re.I,
)

_UNIVERSITY_DOMAIN_SUFFIXES = (
    ".edu",
    ".ac.uk",
    ".ac.za",
    "uchile.cl",
    "puc.cl",
    "uc.cl",
    "utalca.cl",
    "udec.cl",
    "usach.cl",
)

_HOSPITAL_OR_BUYER = re.compile(
    r"\b(hospital|cl[ií]nica|municipalidad|gobierno|servicio\s+de\s+salud|"
    r"ministerio|laboratorio\s+cl[ií]nico|centro\s+m[eé]dico)\b",
    re.I,
)

_PURCHASE_STRONG = re.compile(
    r"\b("
    r"orden\s+de\s+compra|orden\s+de\s+pedido|"
    r"\boc\s*[#:\-]|\boc\b\s*\d+|"
    r"purchase\s+order|\bpo\s*[#:\-]|\bpo\b\s*\d+"
    r")\b",
    re.I,
)

_PURCHASE_MEDIUM = re.compile(
    r"\b("
    r"cotizaci[oó]n\s+aceptada|aceptamos\s+la\s+cotizaci[oó]n|"
    r"proceder\s+con\s+la\s+compra|accepted\s+quotation|"
    r"adjudicad[oa]|adjudicaci[oó]n"
    r")\b",
    re.I,
)

_PURCHASE_WEAK = re.compile(
    r"\b(compra|comprado|factura|pago|despacho|invoice|payment)\b",
    re.I,
)

_NDR_SUBJECT = re.compile(
    r"(undeliverable|delivery\s+status|failure\s+notice|mail\s+delivery\s+failed|"
    r"returned\s+mail|message\s+not\s+delivered|rechazado|no\s+entregad|"
    r"mailbox\s+not\s+found|user\s+unknown|550\s|552\s|554\s)",
    re.I,
)


def is_sent_folder_heuristic(folder: str | None) -> bool:
    f = (folder or "").lower()
    return "enviados" in f or "sent" in f


def is_inbox_folder_heuristic(folder: str | None) -> bool:
    f = (folder or "").strip().lower()
    return "inbox" in f or f == "inbox"


def _blob(subject: str | None, *parts: str | None) -> str:
    return " ".join(
        str(x or "")
        for x in (
            subject,
            parts[0] if len(parts) > 0 else "",
            parts[1] if len(parts) > 1 else "",
            parts[2] if len(parts) > 2 else "",
        )
    )


def external_contact_emails(
    sender: str | None,
    recipients: str | None,
    *,
    internal_domains_lower: frozenset[str],
) -> set[str]:
    """Parse addresses from sender/recipients and drop internal operator domains."""
    out: set[str] = set()
    for e in emails_in(sender or "") + emails_in(recipients or ""):
        dom = domain_of(e)
        if dom and dom not in internal_domains_lower and not dom.endswith(".origenlab.cl"):
            out.add(e.lower().strip())
    return out


def detect_university_signals(blob: str, sender: str | None, recipients: str | None) -> tuple[bool, str]:
    if _UNIVERSITY.search(blob):
        return True, "keyword_university_or_research"
    for e in emails_in(sender or "") + emails_in(recipients or ""):
        dom = domain_of(e) or ""
        for suf in _UNIVERSITY_DOMAIN_SUFFIXES:
            if dom == suf.strip(".") or dom.endswith("." + suf.strip(".")) or dom.endswith(suf):
                return True, f"domain_tail:{suf}"
    return False, ""


def detect_supplier_signals(
    sender: str | None,
    recipients: str | None,
    supplier_domains: frozenset[str],
) -> tuple[bool, str]:
    for e in emails_in(sender or "") + emails_in(recipients or ""):
        if is_supplier_email_domain(e, supplier_domains):
            return True, f"supplier_domain:{domain_of(e)}"
    return False, ""


def detect_bad_email_or_bounce(sender: str | None, subject: str | None, blob: str) -> tuple[bool, str, str]:
    """Returns (hit, confidence, evidence_code)."""
    if is_noise_sender(sender or "", subject or "", blob):
        return True, "high_confidence", "is_noise_sender"
    if _NDR_SUBJECT.search(subject or "") or _NDR_SUBJECT.search(blob[:2000]):
        return True, "high_confidence", "ndr_subject_or_snippet"
    s = (sender or "").lower()
    if "mailer-daemon" in s or "postmaster" in s or "mail delivery subsystem" in s:
        return True, "high_confidence", "bounce_sender"
    return False, "", ""


def detect_cotizacion_sent(
    is_sent: bool,
    blob: str,
    doc_types_csv: str | None = None,
) -> tuple[bool, str, str]:
    if not is_sent:
        return False, "", ""
    dt = (doc_types_csv or "").lower()
    doc_quote = bool(dt) and ("quote" in dt or "presupuesto" in dt or "cotiz" in dt)
    head = blob[:400] if blob else ""
    subjectish_strong = bool(
        re.search(r"\b(cotizaci[oó]n|cotizacion|presupuesto|propuesta|oferta)\b", head, re.I)
    )

    if _COTIZ_SENT.search(blob):
        extra_ev = "cotiz_quote_keywords_in_blob"
        if doc_quote:
            return True, "high_confidence", "sent_keywords_and_document_master_quote"
        if subjectish_strong and len(re.findall(r"\b(cotiz|presupuest|oferta|propuesta|precio)\b", blob[:2500], re.I)) >= 2:
            return True, "high_confidence", "sent_multiple_commercial_terms"
        if subjectish_strong:
            return True, "high_confidence", "sent_strong_commercial_header"
        return True, "medium_confidence", extra_ev

    if doc_quote:
        return True, "medium_confidence", "document_master_quote_in_sent"

    return False, "", ""


def detect_quote_request_inbound(is_inbox: bool, blob: str) -> tuple[bool, str, str]:
    if not is_inbox:
        return False, "", ""
    strong = bool(_QUOTE_STRONG.search(blob))
    medium_hit = bool(_QUOTE_MEDIUM.search(blob))
    weak_hit = bool(_QUOTE_WEAK.search(blob))
    legacy = bool(_QUOTE_REQUEST.search(blob))

    if strong:
        if medium_hit or legacy or weak_hit:
            return True, "high_confidence", "quote_strong_with_supporting_commercial_terms"
        return True, "high_confidence", "quote_strong_rfq_or_oc"

    if medium_hit or legacy:
        if weak_hit:
            return True, "high_confidence", "quote_medium_plus_equipment_or_supplies_context"
        return True, "medium_confidence", "quote_request_commercial_terms"

    if weak_hit:
        return True, "weak_signal", "quote_weak_equipment_or_supplies_only"

    if _COTIZ_SENT.search(blob) and "?" in (blob[:800]):
        return True, "weak_signal", "cotiz_language_with_question_mark"

    return False, "", ""


def detect_client_or_buyer(blob: str) -> tuple[bool, str]:
    if _HOSPITAL_OR_BUYER.search(blob):
        return True, "weak_signal_buyer_keywords"
    return False, ""


def _external_company_domain_present(
    sender: str | None,
    recipients: str | None,
    *,
    internal_domains_lower: frozenset[str],
) -> bool:
    for e in external_contact_emails(sender, recipients, internal_domains_lower=internal_domains_lower):
        dom = domain_of(e)
        if dom and dom not in internal_domains_lower:
            return True
    return False


def detect_purchase_or_order_signal(
    *,
    is_inbox: bool,
    blob: str,
    sender: str | None,
    recipients: str | None,
    internal_domains_lower: frozenset[str],
) -> tuple[bool, str, str]:
    """Heuristic purchase / order signal (not proof of sale)."""
    strong = bool(_PURCHASE_STRONG.search(blob))
    medium = bool(_PURCHASE_MEDIUM.search(blob))
    weak = bool(_PURCHASE_WEAK.search(blob))
    external = _external_company_domain_present(
        sender, recipients, internal_domains_lower=internal_domains_lower
    )

    if strong and (is_inbox or external):
        return True, "high_confidence", "purchase_strong_terms_inbound_or_company"
    if medium:
        return True, "medium_confidence", "purchase_acceptance_or_award_language"
    if weak and is_inbox and external:
        return True, "weak_signal", "purchase_weak_terms_inbound"
    if weak and medium:
        return True, "medium_confidence", "purchase_weak_with_acceptance_language"
    return False, "", ""


def _tags_by_category(tags: list[tuple[str, str, list[str]]]) -> dict[str, tuple[str, str, list[str]]]:
    return {t[0]: t for t in tags}


def _pick_primary_category(tags: list[tuple[str, str, list[str]]]) -> str:
    """Resolve overlapping tags with triage-oriented precedence (heuristic, not CRM truth)."""
    if not tags:
        return "unclassified"
    by = _tags_by_category(tags)
    names = set(by)

    if "bad_email_or_bounce" in names:
        return "bad_email_or_bounce"
    if "marketplace_or_procurement_platform" in names:
        return "marketplace_or_procurement_platform"
    if "logistics_or_notification" in names:
        return "logistics_or_notification"

    pur = by.get("purchase_or_order_signal")
    if pur and pur[1] == "high_confidence":
        return "purchase_or_order_signal"

    cs = by.get("cotizacion_sent")
    qr = by.get("quote_request_inbound")
    if cs and cs[1] == "high_confidence":
        return "cotizacion_sent"
    # Sent cotización (medium) still wins over supplier CC when there is no high inbound RFQ.
    if (
        cs
        and cs[1] == "medium_confidence"
        and "supplier_or_vendor" in names
        and not (qr and qr[1] == "high_confidence")
    ):
        return "cotizacion_sent"

    if qr and qr[1] == "high_confidence" and "supplier_or_vendor" in names:
        return "quote_request_inbound"

    if "supplier_or_vendor" in names:
        if not qr or qr[1] != "high_confidence":
            return "supplier_or_vendor"

    if qr and "university_or_research" in names:
        if qr[1] in ("high_confidence", "medium_confidence"):
            return "quote_request_inbound"
        return "university_or_research"

    if qr:
        return "quote_request_inbound"

    if cs:
        return "cotizacion_sent"

    if "university_or_research" in names:
        return "university_or_research"

    if "supplier_or_vendor" in names:
        return "supplier_or_vendor"

    if "client_or_buyer" in names:
        return "client_or_buyer"

    if "needs_follow_up" in names:
        return "needs_follow_up"

    return tags[0][0]


def recommended_action_for_classification(primary: str, confidence: str) -> str:
    """Suggested triage action (UI / CSV); not automated workflow."""
    _ = confidence
    if primary == "unclassified":
        return "revisar_manual"
    if primary == "bad_email_or_bounce":
        return "marcar_rebote"
    if primary in ("marketplace_or_procurement_platform", "logistics_or_notification"):
        return "ignorar_notificacion"
    if primary == "cotizacion_sent":
        return "revisar_cotizacion"
    if primary == "quote_request_inbound":
        return "responder_solicitud"
    if primary == "needs_follow_up":
        return "revisar_seguimiento"
    if primary == "supplier_or_vendor":
        return "revisar_proveedor"
    if primary == "university_or_research":
        return "revisar_manual"
    if primary == "client_or_buyer":
        return "responder_solicitud"
    if primary == "no_response_after_sent":
        return "revisar_historico"
    if primary == "purchase_or_order_signal":
        return "revisar_cliente_activo"
    return "revisar_manual"


def spanish_heuristic_bucket_label(primary: str) -> str:
    """Human-facing label; makes clear this is heuristic, not CRM truth."""
    return {
        "cotizacion_sent": "Posible cotización enviada",
        "quote_request_inbound": "Posible solicitud",
        "needs_follow_up": "Requiere revisión",
        "supplier_or_vendor": "Proveedor / marca",
        "bad_email_or_bounce": "Rebote probable",
        "marketplace_or_procurement_platform": "Plataforma / licitación",
        "logistics_or_notification": "Logística / aviso",
        "university_or_research": "Universidad / investigación",
        "client_or_buyer": "Posible cliente / comprador",
        "unclassified": "Sin clasificar heurística",
        "no_response_after_sent": "Sin respuesta (heurística)",
        "purchase_or_order_signal": "Posible compra / orden",
    }.get(primary, "Requiere revisión")


@dataclass
class RowClassification:
    """Single-row QA classification (may attach multiple tags)."""

    primary: str
    categories: list[str]
    confidence: str
    evidence: list[str] = field(default_factory=list)
    ambiguous: bool = False
    likely_missed: bool = False
    notes: str = ""
    recommended_action: str = "revisar_manual"


def classify_email_row(
    *,
    folder: str | None,
    subject: str | None,
    sender: str | None,
    recipients: str | None,
    body: str | None,
    full_body_clean: str | None,
    top_reply_clean: str | None,
    doc_types_csv: str | None,
    supplier_domains: frozenset[str],
    internal_domains_lower: frozenset[str],
) -> RowClassification:
    """Apply heuristic buckets; ``doc_types_csv`` is optional ``GROUP_CONCAT`` from ``document_master``."""
    blob = _blob(subject, body, full_body_clean, top_reply_clean)
    is_sent = is_sent_folder_heuristic(folder)
    is_inbox = is_inbox_folder_heuristic(folder)

    tags: list[tuple[str, str, list[str]]] = []  # (category, confidence, evidence_parts)

    hit, conf, ev = detect_bad_email_or_bounce(sender, subject, blob)
    if hit:
        tags.append(("bad_email_or_bounce", conf, [ev]))

    mp_hit, mp_ev = detect_marketplace_or_procurement_platform(sender, recipients)
    if mp_hit:
        tags.append(("marketplace_or_procurement_platform", "high_confidence", [mp_ev]))

    log_hit, log_ev = detect_logistics_or_notification(sender, recipients)
    if log_hit:
        tags.append(("logistics_or_notification", "high_confidence", [log_ev]))

    uni_hit, uni_ev = detect_university_signals(blob, sender, recipients)
    if uni_hit:
        tags.append(("university_or_research", "medium_confidence", [uni_ev]))

    sup_hit, sup_ev = detect_supplier_signals(sender, recipients, supplier_domains)
    if sup_hit:
        tags.append(("supplier_or_vendor", "medium_confidence", [sup_ev]))

    cs_hit, cs_conf, cs_ev = detect_cotizacion_sent(is_sent, blob, doc_types_csv)
    if cs_hit:
        tags.append(("cotizacion_sent", cs_conf, [cs_ev]))

    qr_hit, qr_conf, qr_ev = detect_quote_request_inbound(is_inbox, blob)
    if qr_hit:
        tags.append(("quote_request_inbound", qr_conf, [qr_ev]))

    pur_hit, pur_conf, pur_ev = detect_purchase_or_order_signal(
        is_inbox=is_inbox,
        blob=blob,
        sender=sender,
        recipients=recipients,
        internal_domains_lower=internal_domains_lower,
    )
    if pur_hit:
        tags.append(("purchase_or_order_signal", pur_conf, [pur_ev]))

    client_hit, client_ev = detect_client_or_buyer(blob)
    if client_hit and not sup_hit:
        tags.append(("client_or_buyer", "weak_signal", [client_ev]))

    commercialish = bool(
        _COTIZ_SENT.search(blob)
        or _QUOTE_STRONG.search(blob)
        or _QUOTE_MEDIUM.search(blob)
        or _QUOTE_WEAK.search(blob)
        or _QUOTE_REQUEST.search(blob)
        or (doc_types_csv and "quote" in doc_types_csv.lower())
    )
    if commercialish and not tags:
        tags.append(("needs_follow_up", "weak_signal", ["residual_commercial_language"]))

    if not tags:
        return RowClassification(
            primary="unclassified",
            categories=["unclassified"],
            confidence="needs_manual_review",
            evidence=[],
            ambiguous=False,
            likely_missed=False,
            notes="No heuristic hit; not necessarily non-commercial.",
            recommended_action=recommended_action_for_classification("unclassified", "needs_manual_review"),
        )

    primary = _pick_primary_category(tags)
    categories = [t[0] for t in tags]
    confs = [t[1] for t in tags if t[0] == primary]
    confidence = confs[0] if confs else "weak_signal"
    evidence = [x for t in tags for x in t[2]]
    ambiguous = len(tags) > 1 and primary not in (
        "bad_email_or_bounce",
        "marketplace_or_procurement_platform",
        "logistics_or_notification",
    )
    has_quote_request = any(t[0] == "quote_request_inbound" for t in tags)
    likely_missed = (
        is_inbox
        and commercialish
        and not has_quote_request
        and primary
        not in (
            "marketplace_or_procurement_platform",
            "logistics_or_notification",
            "bad_email_or_bounce",
        )
    )
    rec_action = recommended_action_for_classification(primary, confidence)

    return RowClassification(
        primary=primary,
        categories=categories,
        confidence=confidence,
        evidence=evidence,
        ambiguous=ambiguous,
        likely_missed=likely_missed,
        notes="",
        recommended_action=rec_action,
    )


def inbound_exists_after_sent(
    conn,
    *,
    sent_id: int,
    sent_date_iso: str | None,
    counterparty_emails_lower: Iterable[str],
    counterparty_domains_lower: Iterable[str],
    canonical_predicate_on_e: str,
) -> bool:
    """True if a later **inbound** canonical row references a counterparty (heuristic overlap)."""
    if not sent_date_iso or not str(sent_date_iso).strip():
        return False
    emails_l = {e for e in counterparty_emails_lower if e}
    doms = {d.lower().strip() for d in counterparty_domains_lower if d}
    if not emails_l and not doms:
        return False
    conds: list[str] = []
    params: list[object] = []
    for e in emails_l:
        conds.append("(lower(coalesce(e.sender,'')) LIKE ? OR lower(coalesce(e.recipients,'')) LIKE ?)")
        like = f"%{e}%"
        params.extend([like, like])
    for d in doms:
        conds.append("(lower(coalesce(e.sender,'')) LIKE ? OR lower(coalesce(e.recipients,'')) LIKE ?)")
        like = f"%@{d}%"
        params.extend([like, like])
    overlap_sql = "(" + " OR ".join(conds) + ")"
    sql = f"""
        SELECT 1 FROM emails e
        WHERE ({canonical_predicate_on_e})
          AND e.id != ?
          AND (lower(coalesce(e.folder,'')) LIKE '%inbox%' OR lower(trim(coalesce(e.folder,''))) = 'inbox')
          AND e.date_iso IS NOT NULL AND trim(e.date_iso) != ''
          AND e.date_iso > ?
          AND {overlap_sql}
        LIMIT 1
    """
    params_final: list[object] = [sent_id, str(sent_date_iso).strip()] + params
    try:
        row = conn.execute(sql, tuple(params_final)).fetchone()
    except Exception:
        return False
    return bool(row)


def canonical_where_for_alias(alias: str) -> str:
    """Delegate to contacto predicate with table alias (trusted SQL fragment)."""
    from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source

    return sql_predicate_contacto_gmail_source(table_alias=alias, coalesce_null=False)


def mark_no_response_candidates(
    conn,
    *,
    canonical_where_sql: str,
    days: int,
    limit: int,
    internal_domains_lower: frozenset[str],
) -> list[dict]:
    """Return sent-like rows that look like quote/cotización **and** have no later inbound reply."""
    import sqlite3 as _s

    w = canonical_where_sql
    lim = max(1, min(int(limit), 5000))
    d = max(1, min(int(days), 3660))
    try:
        cur = conn.execute(
            f"""
            SELECT id, date_iso, folder, sender, recipients, subject,
                   COALESCE(body,'') AS body, COALESCE(full_body_clean,'') AS fbc,
                   COALESCE(top_reply_clean,'') AS trc
            FROM emails
            WHERE {w}
              AND date(date_iso) >= date('now', ?)
              AND (
                lower(coalesce(folder,'')) LIKE '%enviados%'
                OR lower(coalesce(folder,'')) LIKE '%sent%'
              )
            ORDER BY date_iso DESC
            LIMIT ?
            """,
            (f"-{d} days", lim * 3),
        )
        rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    except _s.Error:
        return []

    out: list[dict] = []
    cw_e = canonical_where_for_alias("e")
    for r in rows:
        blob = _blob(r.get("subject"), r.get("body"), r.get("fbc"), r.get("trc"))
        if not _COTIZ_SENT.search(blob):
            continue
        ext = external_contact_emails(r.get("sender"), r.get("recipients"), internal_domains_lower=internal_domains_lower)
        doms = {domain_of(x) for x in ext}
        doms.discard(None)
        if not ext and not doms:
            continue
        if inbound_exists_after_sent(
            conn,
            sent_id=int(r["id"]),
            sent_date_iso=r.get("date_iso"),
            counterparty_emails_lower=ext,
            counterparty_domains_lower={d for d in doms if d},
            canonical_predicate_on_e=cw_e,
        ):
            continue
        r["predicted_label"] = "no_response_after_sent"
        r["confidence"] = "weak_signal"
        r["evidence"] = "sent_cotiz_keywords_no_later_inbound_overlap"
        out.append(r)
        if len(out) >= lim:
            break
    return out


__all__ = [
    "RowClassification",
    "classify_email_row",
    "canonical_where_for_alias",
    "mark_no_response_candidates",
    "inbound_exists_after_sent",
    "external_contact_emails",
    "is_sent_folder_heuristic",
    "is_inbox_folder_heuristic",
    "detect_bad_email_or_bounce",
    "detect_cotizacion_sent",
    "detect_quote_request_inbound",
    "detect_university_signals",
    "qa_operational_internal_domains",
    "detect_marketplace_or_procurement_platform",
    "detect_logistics_or_notification",
    "recommended_action_for_classification",
    "spanish_heuristic_bucket_label",
]
