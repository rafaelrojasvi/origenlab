"""
Tatiana **candidate writing** cohort — operational definition and review scoring.

This module supports **manual review exports** only (no ML). The cohort is broader
than strict `--sample-mode voice` in explore scripts: it uses `tatiana_voice_cohort`
candidate rules (allowlist + LabDelivery-style domains + optional Tatiana/Vivanco
text signals), then applies export filters and transparent heuristics for ranking.

See `docs/dataset/TATIANA_REVIEW_COHORT.md` for the full inclusion/exclusion spec.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from origenlab_email_pipeline.business_filter_rules import INTERNAL_DOMAINS
from origenlab_email_pipeline.business_mart import classify_email_intents, emails_in, is_noise_sender
from origenlab_email_pipeline.email_business_filters import classify_email
from origenlab_email_pipeline.tatiana_voice_cohort import (
    sender_header_matches_allowlist,
    sender_domain_matches_voice_domains,
    subject_is_reply_or_forward,
    text_blob_mentions_tatiana_identity,
)

TATIANA_CANDIDATE_COHORT_VERSION = "1.2"

# Spoof / phishing hints when From is forged as company domain (aligns with ML explore hygiene).
_REVIEW_SPOOF_SUBJECT_HINTS: tuple[str, ...] = (
    "pedido en su espera",
    "pedido en nuestro deposito",
    "pedido en nuestro depósito",
    "deposito en su nombre",
    "depósito en su nombre",
    "existen facturas no pagos",
    "existen facturas o boletos no pagados",
    "boletas o facturas no pago",
    "cobranza extrajudicial",
    "cobranza judicial",
    "tarjeta de coordenadas ha expirado",
    "pending messages on our remote server",
    "***spam***",
    "[spam]",
)

_REVIEW_SPOOF_BODY_HINTS: tuple[str, ...] = (
    "si no está viendo",
    "si no esta viendo",
    "si no puede ver este mensaje",
    "pending messages on our remote server",
    "unread in our cloud",
    "este e-mail fue generado durante",
    "labdelivery.cl administrator support",
    "nota fiscal.zip",
)


def _norm(s: str) -> str:
    return (s or "").lower()


@dataclass(frozen=True)
class ReviewSignals:
    inclusion_reasons: tuple[str, ...]
    risk_flags: tuple[str, ...]
    intent_primary: str
    intent_quote: bool
    intent_invoice: bool
    intent_purchase: bool
    commercial_subtype: str
    identity_mention_in_header: bool
    identity_mention_in_body_only: bool
    likely_outbound_to_external: bool
    heavy_reply_tail: bool
    trivial_one_liner: bool
    quote_line_ratio_full: float
    score: float  # 0..100, ranking only


def _internal_domain_set(voice_domains: frozenset[str]) -> frozenset[str]:
    a = {x.lower().strip() for x in INTERNAL_DOMAINS}
    b = {x.lower() for x in voice_domains}
    return frozenset(a | b)


def likely_outbound_to_external(
    recipients: str | None,
    *,
    voice_domains: frozenset[str],
) -> bool:
    """True if any parsed recipient domain is outside INTERNAL ∪ voice domains."""
    internal = _internal_domain_set(voice_domains)
    for e in emails_in(recipients or ""):
        dom = e.split("@")[-1].lower() if "@" in e else ""
        if not dom:
            continue
        if any(dom == i or dom.endswith("." + i) for i in internal):
            continue
        return True
    return False


def _spoof_flags(subject: str, hybrid: str) -> list[str]:
    flags: list[str] = []
    sub_l = _norm(subject)
    body_l = _norm(hybrid)[:8000]
    for frag in _REVIEW_SPOOF_SUBJECT_HINTS:
        if frag.lower() in sub_l:
            flags.append(f"spoof_subject:{frag[:40]}")
    for frag in _REVIEW_SPOOF_BODY_HINTS:
        if frag.lower() in body_l:
            flags.append(f"spoof_body:{frag[:40]}")
    return flags


def subject_looks_reply_or_forward(subject: str | None) -> bool:
    """
    True if the subject line looks like a reply/forward, including common MIME-encoded forms.
    """
    if not subject:
        return False
    if subject_is_reply_or_forward(subject):
        return True
    low = subject.lower()
    if re.search(r"\brv\s*:", subject, re.I):
        return True
    for needle in ("?q?re:", "?q?fw:", "?q?fwd:", "?q?rv:", "?q?re_", "?q?fw_"):
        if needle in low:
            return True
    return False


def external_recipient_domain_count(recipients: str | None, *, voice_domains: frozenset[str]) -> int:
    """Count distinct recipient domains outside INTERNAL ∪ voice_domains."""
    internal = _internal_domain_set(voice_domains)
    seen: set[str] = set()
    for e in emails_in(recipients or ""):
        dom = e.split("@")[-1].lower() if "@" in e else ""
        if not dom:
            continue
        if any(dom == i or dom.endswith("." + i) for i in internal):
            continue
        seen.add(dom)
    return len(seen)


@dataclass(frozen=True)
class MarketingExportRankMeta:
    """Export-only ranking overlay for marketing / intro / prospecting review slices."""

    rank_delta: float
    export_tier: int
    subject_threaded: bool
    ops_noise_hits: int
    hybrid_contam_flags: int
    external_domain_count: int
    body_len: int
    notes: tuple[str, ...]


def compute_marketing_export_rank_meta(
    *,
    subject: str,
    hybrid_body: str,
    risk_flags: tuple[str, ...],
    commercial_subtype: str,
    intent_quote: bool,
    intent_invoice: bool,
    recipients: str | None,
    voice_domains: frozenset[str],
) -> MarketingExportRankMeta:
    """
    Heuristic delta + tie-break fields for marketing-first export ordering.

    Does not change `review_quality_score`; combined sort uses score + rank_delta, then tuple tie-breaks.
    """
    subj_n = _norm(subject)
    blob = subj_n + " " + _norm(hybrid_body)[:10000]
    threaded = subject_looks_reply_or_forward(subject)
    notes: list[str] = []
    delta = 0.0
    ops_hits = 0

    def _pen(amount: float, w: int, tag: str) -> None:
        nonlocal delta, ops_hits
        delta += amount
        ops_hits += w
        notes.append(tag)

    # --- Demotions: payment / admin / logistics / supplier coordination ---
    strong_pay = (
        "comprobante de transferencia",
        "transferencia de fondos",
        "monto transacción",
        "monto transaccion",
        "número de transacción",
        "numero de transaccion",
        "datos bancarios para transferencia",
        "solicitud cambio de factura",
        "le informamos que ha efectuado una transferencia",
    )
    sp_applied = 0
    for ph in strong_pay:
        if ph in blob:
            if intent_quote and ph in (
                "solicitud cambio de factura",
            ):
                continue
            _pen(-11.0, 3, f"mk_demote:{ph[:28]}")
            sp_applied += 1
            if sp_applied >= 2:
                break

    if "datos bancarios" in blob and ("transferencia" in blob or "cuenta corriente" in blob):
        if "comprobante de transferencia" not in blob or sp_applied == 0:
            _pen(-9.0, 2, "mk_demote:datos_bancarios_transfer")

    inv_c = (
        "aviso cobranza",
        "pago factura",
        "pago de factura",
        "coordenadas bancarias",
        "cobranza pago factura",
    )
    for ph in inv_c:
        if ph in blob:
            _pen(-8.0, 2, f"mk_demote:{ph[:24]}")
            break

    if "cobranza" in subj_n:
        _pen(-5.0, 1, "mk_demote:cobranza_subject")

    if intent_invoice and not intent_quote:
        _pen(-4.0, 1, "mk_demote:intent_invoice")

    log_p = (
        "retenida en aduana",
        "retenida en la aduana",
        "guía aérea es",
        "guia aerea es",
        "número de guía",
        "numero de guia",
        "dhl estados unidos",
        "solucionen con el courier",
        "tracking number",
    )
    logistics_tagged = False
    for ph in log_p:
        if ph in blob:
            _pen(-8.0, 2, f"mk_demote:{ph[:24]}")
            logistics_tagged = True
            break

    if not logistics_tagged and "aduana" in blob and ("reten" in blob or "despacho" in blob):
        _pen(-6.0, 2, "mk_demote:aduana_ops")

    if "proforma" in blob and "necesito modifiques" in blob:
        _pen(-9.0, 2, "mk_demote:proforma_destinatario")

    # Cap demotions
    if delta < -34.0:
        delta = -34.0

    # --- Boosts: outreach / intro / quote prose ---
    boost_cap = 0.0
    if not threaded:
        delta += 7.0
        boost_cap += 7.0
        notes.append("mk_boost:fresh_subject")

    if "gracias por contactarnos" in blob:
        delta += 4.0
        boost_cap += 4.0
        notes.append("mk_boost:gracias_contacto")

    if ("junto con saludar" in blob or "junto con saludarla" in blob) and (
        "cotiz" in blob or "adjunto" in blob
    ):
        delta += 5.0
        boost_cap += 5.0
        notes.append("mk_boost:junto_saludar_cot_o_adjunto")

    if not threaded and any(
        x in blob for x in ("representada", "representados", "importador", "distribuidor", "dealers")
    ):
        delta += 3.0
        boost_cap += 3.0
        notes.append("mk_boost:company_repr_language")

    if commercial_subtype in ("quote", "followup") and delta > -12.0:
        delta += 3.0
        notes.append("mk_boost:subtype_quote_followup")

    if delta > 18.0:
        delta = 18.0

    # Tier 0..5 for secondary ordering
    tier = 2
    if not threaded:
        tier += 2
    if "gracias por contactarnos" in blob:
        tier += 1
    if commercial_subtype in ("quote", "followup"):
        tier += 1
    if any(x in blob for x in ("representada", "importador", "distribuidor")):
        tier += 1
    if delta <= -18.0:
        tier = min(tier, 2)
    if sp_applied > 0 or "comprobante de transferencia" in blob:
        tier = min(tier, 2)
    tier = max(0, min(5, tier))

    h_flags = sum(1 for f in risk_flags if str(f).startswith("hybrid_"))
    ext_n = external_recipient_domain_count(recipients, voice_domains=voice_domains)
    blen = len((hybrid_body or "").strip())

    return MarketingExportRankMeta(
        rank_delta=round(delta, 2),
        export_tier=tier,
        subject_threaded=threaded,
        ops_noise_hits=ops_hits,
        hybrid_contam_flags=h_flags,
        external_domain_count=ext_n,
        body_len=blen,
        notes=tuple(dict.fromkeys(notes)),
    )


def cohort_export_dedup_key(body_for_review: str, subject: str, date_iso: str) -> str:
    """
    Stable key for exact duplicate suppression in review exports.

    Uses normalized `body_for_review` + whitespace-collapsed subject + date day (ISO prefix).
    """

    def _squash(s: str) -> str:
        return " ".join((s or "").lower().split())

    sub = _squash(subject)
    day = (date_iso or "").strip()[:10]
    bod = _squash(body_for_review)
    raw = f"{sub}|{day}|{bod}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def hybrid_thread_contamination(hybrid_body: str) -> tuple[tuple[str, ...], float]:
    """
    Detect forward / reply-chain noise in the chosen review body (hybrid).

    Returns (risk flag names, total score penalty). Penalties are applied once by the caller.
    """
    h = (hybrid_body or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in h.split("\n") if ln.strip()]
    if not lines:
        return (), 0.0

    n = len(lines)
    forwardish = 0
    quoted_only = 0
    for ln in lines:
        low = ln.lower()
        if ln.startswith(">") or ln.startswith("|"):
            forwardish += 1
            quoted_only += 1
            continue
        if re.match(r"^(de|from|para|to|cc|bcc|asunto|subject)\s*:\s*\S", low):
            forwardish += 1
        elif (
            low.startswith("enviado el:")
            or low.startswith("sent:")
            or low.startswith("date:")
            or low.startswith("fecha:")
        ):
            forwardish += 1

    ratio = forwardish / n
    flags: list[str] = []
    penalty = 0.0

    first = lines[0].lower()
    if first.startswith("de:") or first.startswith("from:"):
        flags.append("hybrid_opens_forward_header")
        penalty += 9.0

    if n >= 4 and ratio >= 0.28:
        flags.append("hybrid_forward_or_quote_heavy")
        penalty += min(17.0, 9.0 + (ratio - 0.28) * 45.0)
    elif n >= 4 and ratio >= 0.18:
        flags.append("hybrid_forward_or_quote_moderate")
        penalty += 5.0

    if n >= 5 and quoted_only / n >= 0.22:
        flags.append("hybrid_quoted_lines_dense")
        penalty += 7.0

    return tuple(flags), penalty


def non_spanish_commercial_downrank(hybrid_body: str) -> tuple[tuple[str, ...], float]:
    """
    Mild downrank for clearly English-forward commercial prose (Spanish cohort default).

    Conservative: requires multiple English markers and weak Spanish markers.
    """
    t = _norm(hybrid_body)[:12000]
    spanish_markers = (
        "estimado",
        "estimada",
        "junto con saludar",
        "cotizaci",
        "adjunto",
        "quedo atenta",
        "quedo atento",
        "saludos cordiales",
        "buenos días",
        "buenas tardes",
        "atenta a sus comentarios",
        "atento a sus comentarios",
        "gracias por",
    )
    english_markers = (
        "dear sirs",
        "dear sir",
        "good morning",
        "good afternoon",
        "kind regards",
        "best regards",
        "we are dealers",
        "quotation for",
        "purchase order",
        "my name is ",
        "i will appreciate",
    )
    sm = sum(1 for m in spanish_markers if m in t)
    em = sum(1 for m in english_markers if m in t)
    if em >= 2 and sm <= 1:
        return ("likely_non_spanish_commercial_body",), 8.0
    if em >= 1 and sm == 0 and " the " in t[:1200]:
        return ("likely_non_spanish_commercial_body",), 6.0
    return (), 0.0


def quote_heavy_full_body(full_body_clean: str, top_reply_clean: str) -> tuple[bool, float]:
    """
    Approximate quoted / forwarded tail in full body using '>' line ratio.
    Returns (heavy_tail, ratio_of_lines_starting_with_quote_mark).
    """
    full = (full_body_clean or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in full.split("\n") if ln.strip()]
    if len(lines) < 4:
        return False, 0.0
    quoted = sum(1 for ln in lines if ln.startswith(">"))
    ratio = quoted / len(lines)
    top_len = len((top_reply_clean or "").strip())
    full_len = len(full.strip())
    heavy = ratio >= 0.35 and full_len > top_len + 200
    return heavy, ratio


def build_review_signals(
    *,
    sender: str,
    recipients: str | None,
    subject: str,
    full_body_clean: str,
    top_reply_clean: str,
    hybrid_body: str,
    allowlist: frozenset[str],
    voice_domains: frozenset[str],
    trusted_mention_domains: frozenset[str],
    include_tatiana_text_signals: bool,
) -> ReviewSignals:
    reasons: list[str] = []
    by_addr = sender_header_matches_allowlist(sender, allowlist)
    by_dom = bool(voice_domains) and sender_domain_matches_voice_domains(sender, voice_domains)
    by_mention = False
    if include_tatiana_text_signals and sender_domain_matches_voice_domains(
        sender, trusted_mention_domains
    ):
        by_mention = text_blob_mentions_tatiana_identity(
            sender, full_body_clean, top_reply_clean
        )
    if by_addr:
        reasons.append("allowlisted_sender_address")
    if by_dom:
        reasons.append("voice_sender_domain")
    if by_mention:
        reasons.append("tatiana_or_vivanco_signal_trusted_domain")

    id_header = text_blob_mentions_tatiana_identity(sender, None, None)
    id_body_only = text_blob_mentions_tatiana_identity(
        None, full_body_clean, top_reply_clean
    ) and not id_header

    risks: list[str] = []
    hlen = len((hybrid_body or "").strip())
    subj = subject or ""

    if is_noise_sender(sender, subj, hybrid_body[:5000] if hybrid_body else ""):
        risks.append("noise_sender_heuristic")

    spoof = _spoof_flags(subj, hybrid_body)
    risks.extend(spoof)

    cls = classify_email(sender=sender, recipients=recipients, subject=subj, body=hybrid_body[:12000])
    primary = str(cls.get("primary_category", "unknown"))
    tags = cls.get("tags") or []
    if primary in ("bounce_ndr", "spam_suspect", "newsletter", "social_notification"):
        risks.append(f"classify_primary:{primary}")
    if "spam_suspect" in tags and "classify_primary:spam_suspect" not in risks:
        risks.append("tag_spam_suspect")

    heavy, qratio = quote_heavy_full_body(full_body_clean, top_reply_clean)
    if heavy:
        risks.append("heavy_quoted_thread_in_full_body")

    lines = [ln for ln in (hybrid_body or "").splitlines() if ln.strip()]
    trivial = len(lines) <= 1 and hlen < 90
    if trivial:
        risks.append("trivial_short_message")

    cont_flags, cont_pen = hybrid_thread_contamination(hybrid_body)
    risks.extend(cont_flags)
    lang_flags, lang_pen = non_spanish_commercial_downrank(hybrid_body)
    risks.extend(lang_flags)

    outbound = likely_outbound_to_external(recipients, voice_domains=voice_domains)

    intents = classify_email_intents(subj, hybrid_body)
    comm_sub = str(cls.get("commercial_subtype") or "")
    inv_intent = bool(intents.get("is_invoice_email"))

    # --- Score (0..100), transparent additive model, clamped ---
    score = 48.0
    if "allowlisted_sender_address" in reasons:
        score += 18.0
    if "voice_sender_domain" in reasons:
        score += 12.0
    if "tatiana_or_vivanco_signal_trusted_domain" in reasons:
        score += 14.0
    if outbound:
        score += 8.0

    if hlen < 80:
        score -= 22.0
    elif hlen < 120:
        score -= 10.0
    elif 120 <= hlen < 250:
        score += 6.0
    elif 250 <= hlen < 800:
        score += 12.0
    elif 800 <= hlen < 3500:
        score += 8.0
    else:
        score += 3.0

    if primary == "business_core":
        score += 8.0
        if outbound:
            score += 4.0
    elif primary == "internal":
        if outbound:
            score += 1.0
        else:
            score -= 11.0

    if comm_sub in ("quote", "followup"):
        score += 5.0
    elif comm_sub == "support" and outbound:
        score += 3.0

    if comm_sub in ("invoice", "order"):
        if outbound:
            score += 2.0
        else:
            score -= 6.0

    if inv_intent and not outbound:
        score -= 6.0

    if "noise_sender_heuristic" in risks:
        score -= 35.0
    spoof_hits = sum(1 for r in risks if r.startswith("spoof_"))
    if spoof_hits:
        score -= min(42.0, spoof_hits * 14.0)
    if any(r.startswith("classify_primary:") for r in risks):
        score -= 22.0
    for r in risks:
        if r == "heavy_quoted_thread_in_full_body":
            score -= 10.0
        elif r == "trivial_short_message":
            score -= 14.0
        elif r == "tag_spam_suspect":
            score -= 12.0

    if qratio > 0.25 and qratio < 0.35:
        score -= 4.0

    score -= cont_pen + lang_pen

    score = max(0.0, min(100.0, score))

    return ReviewSignals(
        inclusion_reasons=tuple(dict.fromkeys(reasons)),
        risk_flags=tuple(dict.fromkeys(risks)),
        intent_primary=primary,
        intent_quote=bool(intents.get("is_quote_email")),
        intent_invoice=bool(intents.get("is_invoice_email")),
        intent_purchase=bool(intents.get("is_purchase_email")),
        commercial_subtype=comm_sub,
        identity_mention_in_header=id_header,
        identity_mention_in_body_only=id_body_only,
        likely_outbound_to_external=outbound,
        heavy_reply_tail=heavy,
        trivial_one_liner=trivial,
        quote_line_ratio_full=round(qratio, 3),
        score=round(score, 1),
    )
