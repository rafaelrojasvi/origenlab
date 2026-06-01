"""Quality pass for Presentación OrigenLab — batch curation, dedupe, classification.

Read-only: no Gmail sends, no outreach-state writes.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import domain_of
from origenlab_email_pipeline.candidate_export_gate import normalize_export_email
from origenlab_email_pipeline.campaigns.presentacion_origenlab_quality_types import (
    BATCH_CSV_FIELDS,
    CLASS_FOLLOWUP_OLD,
    CLASS_HOLD_PERSONALIZED,
    CLASS_PRESENTATION,
    CLASS_EXCLUDED,
    DO_NOT_SEND_FIELDS,
    HOLD_PERSONALIZED_FIELDS,
    SAME_DOMAIN_CURATED_FIELDS,
    DoNotSendRow,
    HoldPersonalizedRow,
    PresentacionBatchRow,
)
from origenlab_email_pipeline.campaigns.presentacion_origenlab_templates import (
    render_batch_messages_markdown,
    template_followup_old_es,
    template_hold_personalized_es,
    template_presentacion_batch1_es,
)
from origenlab_email_pipeline.campaigns.presentacion_origenlab_types import (
    PresentacionReviewRow,
)

_BATCH1_LIMIT = 25
_BATCH2_LIMIT = 25

_QUOTE_RE = re.compile(r"cotiz|quote|osm[oó]met|solicitud de cotiz|re:\s", re.I)
_RE_SUBJECT_RE = re.compile(r"^re:\s", re.I)
_PRESENTATION_RE = re.compile(r"presentaci|origenlab|equipos para laboratorio|equipos e insumos", re.I)
_UNIVERSITY_BULK_DOMAINS: frozenset[str] = frozenset(
    {
        "uchile.cl",
        "udec.cl",
        "uach.cl",
        "usach.cl",
        "uc.cl",
        "puc.cl",
        "uv.cl",
        "utalca.cl",
        "ubiobio.cl",
        "userena.cl",
        "ufro.cl",
        "usm.cl",
        "ucn.cl",
        "pucv.cl",
        "unach.cl",
        "uta.cl",
        "uoh.cl",
        "umag.cl",
        "unap.cl",
        "umayor.cl",
        "uautonoma.cl",
    }
)
_LOW_QUALITY_LOCAL_RE = re.compile(
    r"^(comunicaciones|informaciones|circularizacion|transparencia|secredir|"
    r"comunicacion|noreply|no-reply|admin|postmaster|mailer)",
    re.I,
)
_LAB_LOCAL_HINTS: tuple[str, ...] = (
    "laboratorio",
    "lab",
    "calidad",
    "qc",
    "bacteriologia",
    "equipolaboratorio",
    "ambiental",
    "analisis",
    "microbiolog",
)
_PRIVATE_SECTOR_HINTS: tuple[str, ...] = (
    "lab",
    "laboratorio",
    "analisis",
    "qc",
    "aliment",
    "agua",
    "industr",
    "farma",
    "cosmet",
    "ambient",
    "acuic",
    "minera",
    "bio",
)

# Casos activos personalizados (C) — no campaña genérica.
HOLD_PERSONALIZED_REGISTRY: tuple[dict[str, str], ...] = (
    {
        "email": "juan-pablo.garcia@bureauveritas.com",
        "case_label": "CESMEC / Juan Pablo",
        "organization": "CESMEC / Bureau Veritas",
        "contact_name": "Juan Pablo García",
        "personalized_action": (
            "Según acuerdo del hilo CESMEC, adjuntar o reenviar catálogo / fichas "
            "solicitadas y confirmar próximo paso comercial."
        ),
    },
    {
        "email": "susanaalfaro@unach.cl",
        "case_label": "UNACH / Susana / Hielscher",
        "organization": "UNACH",
        "contact_name": "Susana Alfaro",
        "personalized_action": (
            "Esperar cotización del proveedor Hielscher antes de escalar propuesta "
            "al cliente; no enviar presentación genérica."
        ),
    },
    {
        "email": "marcos.a@hielscher.com",
        "case_label": "Hielscher / Marcos",
        "organization": "Hielscher Ultrasonics",
        "contact_name": "Marcos Acevedo",
        "personalized_action": (
            "Solicitar cotización formal al proveedor para el requerimiento UNACH / "
            "escalamiento ultrasónico."
        ),
    },
    {
        "email": "hola@ongo.cl",
        "case_label": "ONGO",
        "organization": "ONGO",
        "contact_name": "",
        "personalized_action": (
            "Seguimiento cotización Sonicador UP400St — confirmar specs, plazo y "
            "próximo paso con el cliente."
        ),
    },
    {
        "email": "ariel@crtopmachine.com",
        "case_label": "CRTOP",
        "organization": "CRTOP",
        "contact_name": "Ariel",
        "personalized_action": (
            "Seguimiento reactor / flete / margen con proveedor CRTOP; no mezclar "
            "con campaña de presentación."
        ),
    },
    {
        "email": "miguel.martinez@virbac.cl",
        "case_label": "Virbac",
        "organization": "Virbac",
        "contact_name": "Miguel Martínez",
        "personalized_action": (
            "Seguimiento cotización vigente — retomar hilo comercial específico, "
            "no presentación genérica."
        ),
    },
    {
        "email": "laboratorio@nanotecchile.com",
        "case_label": "Nanotec",
        "organization": "Nanotec Chile",
        "contact_name": "",
        "personalized_action": (
            "Seguimiento cotización elemento de dispersión IKA — confirmar specs "
            "y plazo."
        ),
    },
    {
        "email": "tbeldarrain@udec.cl",
        "case_label": "UdeC sonicadores",
        "organization": "Universidad de Concepción",
        "contact_name": "Tatiana Beldarraín",
        "personalized_action": (
            "Seguimiento cotización sonicadores — retomar hilo técnico/comercial "
            "con UdeC."
        ),
    },
    {
        "email": "fgonzalez@ceaf.cl",
        "case_label": "CEAF",
        "organization": "CEAF",
        "contact_name": "Francisca González",
        "personalized_action": "Coordinación pago/logística CEAF — no campaña comercial.",
    },
    {
        "email": "order@serva.de",
        "case_label": "SERVA",
        "organization": "SERVA",
        "contact_name": "",
        "personalized_action": "Pedido/logística proveedor SERVA — admin, no outbound.",
    },
)

OUTPUT_BATCH1 = "presentacion_batch1_send_now_25.csv"
OUTPUT_BATCH2 = "presentacion_batch2_followup_old_25.csv"
OUTPUT_HOLD = "presentacion_hold_active_personalized.csv"
OUTPUT_SAME_DOMAIN = "presentacion_same_domain_review_curated.csv"
OUTPUT_DO_NOT_SEND = "presentacion_do_not_send_reasons.csv"
OUTPUT_BATCH1_MSG = "presentacion_batch1_messages.md"
OUTPUT_FOLLOWUP_MSG = "presentacion_followup_messages.md"


@dataclass
class PresentacionQualityResult:
    batch1: list[PresentacionBatchRow] = field(default_factory=list)
    batch2: list[PresentacionBatchRow] = field(default_factory=list)
    hold_personalized: list[HoldPersonalizedRow] = field(default_factory=list)
    same_domain_curated: list[dict[str, str]] = field(default_factory=list)
    do_not_send: list[DoNotSendRow] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    batch1_markdown: str = ""
    followup_markdown: str = ""


def _norm_org_key(organization: str, domain: str) -> str:
    org = re.sub(r"[^a-z0-9]+", "", (organization or "").lower())
    dom = (domain or "").strip().lower()
    if org and len(org) >= 4:
        return org
    return dom


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _row_from_review(raw: dict[str, str]) -> PresentacionReviewRow:
    return PresentacionReviewRow(
        email=raw.get("email") or "",
        organization=raw.get("organization") or "",
        contact_name=raw.get("contact_name") or "",
        bucket=raw.get("bucket") or "",
        reason_for_inclusion=raw.get("reason_for_inclusion") or "",
        product_angle=raw.get("product_angle") or "",
        history_note=raw.get("history_note") or "",
        suggested_subject=raw.get("suggested_subject") or "",
        suggested_message=raw.get("suggested_message") or "",
        recommended_action=raw.get("recommended_action") or "",
        priority_score=float(raw.get("priority_score") or 0),
        exclusion_flags=raw.get("exclusion_flags") or "",
    )


def _sector_guess(domain: str, organization: str, email: str) -> str:
    blob = f"{domain} {organization} {email}".lower()
    if any(h in blob for h in ("aliment", "food", "leche", "agro")):
        return "alimentos_qc"
    if any(h in blob for h in ("agua", "esval", "aguas", "sanitaria")):
        return "agua_utilities"
    if any(h in blob for h in ("hospital", "salud", "clinico", "redsalud")):
        return "salud_hospital"
    if domain in _UNIVERSITY_BULK_DOMAINS or "univ" in blob or ".edu" in domain:
        return "universidad"
    if any(h in blob for h in _PRIVATE_SECTOR_HINTS):
        return "lab_privado_industria"
    if domain.endswith(".gov.cl"):
        return "publico"
    return "otro"


def _is_low_quality_contact(email: str, organization: str) -> tuple[bool, str]:
    em = (email or "").lower()
    local = em.split("@")[0] if "@" in em else em
    org_l = (organization or "").lower()
    if _LOW_QUALITY_LOCAL_RE.search(local):
        return True, "correo_admin_comunicaciones"
    if "redsalud" in em and not any(h in local for h in _LAB_LOCAL_HINTS):
        return True, "redsalud_no_laboratorio"
    if "gestion." in em or local.startswith(("sec", "dirc", "admin", "inform")):
        if not any(h in local for h in _LAB_LOCAL_HINTS):
            return True, "universidad_admin_generico"
    if any(x in org_l for x in ("gmail", "hotmail")):
        return True, "correo_personal"
    if domain_of(em) in _UNIVERSITY_BULK_DOMAINS and not any(
        h in local for h in _LAB_LOCAL_HINTS
    ):
        return True, "universidad_contacto_generico"
    return False, ""


def _has_quote_history(subject: str, history: str) -> bool:
    blob = f"{subject} {history}"
    return bool(_QUOTE_RE.search(blob))


def _is_followup_candidate(subject: str, history: str, sent_count: int) -> bool:
    blob = f"{subject} {history}"
    if _has_quote_history(subject, history):
        return True
    if _RE_SUBJECT_RE.search(subject or ""):
        return True
    if sent_count >= 3 and re.search(r"origenlab|centríf|centrif|equipos", blob, re.I):
        return True
    return False


def _presentation_fit_score(
    *,
    domain: str,
    organization: str,
    email: str,
    subject: str,
    history: str,
    base_score: float,
) -> float:
    score = base_score
    sector = _sector_guess(domain, organization, email)
    if sector == "lab_privado_industria":
        score += 25
    elif sector in ("alimentos_qc", "agua_utilities"):
        score += 20
    elif sector == "salud_hospital":
        score += 5
    elif sector == "universidad":
        score -= 15
    elif sector == "publico":
        score -= 10
    if _has_quote_history(subject, history):
        score -= 40
    if _PRESENTATION_RE.search(subject or ""):
        score += 10
    low, _ = _is_low_quality_contact(email, organization)
    if low:
        score -= 50
    if domain in _UNIVERSITY_BULK_DOMAINS:
        score -= 20
    if "redsalud" in domain:
        score -= 25
    return score


def _followup_fit_score(
    *,
    domain: str,
    organization: str,
    email: str,
    subject: str,
    history: str,
    base_score: float,
) -> float:
    score = base_score
    if _has_quote_history(subject, history):
        score += 35
    if "osm" in f"{subject} {history}".lower():
        score += 15
    if "centríf" in f"{subject} {history}".lower() or "centrif" in f"{subject} {history}".lower():
        score += 10
    low, _ = _is_low_quality_contact(email, organization)
    if low:
        score -= 40
    if domain in _UNIVERSITY_BULK_DOMAINS and not _has_quote_history(subject, history):
        score -= 15
    return score


def _topic_hint(subject: str, history: str) -> str:
    blob = f"{subject} {history}"
    if re.search(r"osm[oó]met", blob, re.I):
        return "cotización de osmómetro"
    if re.search(r"centríf|centrif", blob, re.I):
        return "centrífugas de laboratorio"
    if re.search(r"sonicador|ultrason", blob, re.I):
        return "sonicadores / ultrasonido"
    if re.search(r"reactor", blob, re.I):
        return "reactores de laboratorio"
    if _QUOTE_RE.search(blob):
        return "cotización previa"
    return "equipamiento de laboratorio"


def _build_hold_personalized(
    registry: tuple[dict[str, str], ...],
    universe_by_email: dict[str, dict[str, str]],
) -> list[HoldPersonalizedRow]:
    out: list[HoldPersonalizedRow] = []
    for spec in registry:
        em = normalize_export_email(spec["email"]) or spec["email"]
        dom = domain_of(em) or ""
        uni = universe_by_email.get(em, {})
        history = uni.get("latest_subject_safe") or spec.get("history_note") or ""
        subj, body = template_hold_personalized_es(
            contact_name=spec.get("contact_name") or uni.get("display_name") or "",
            case_label=spec["case_label"],
            personalized_action=spec["personalized_action"],
            history_note=history,
        )
        out.append(
            HoldPersonalizedRow(
                email=em,
                domain=dom,
                organization=spec.get("organization") or uni.get("organization_name") or "",
                contact_name=spec.get("contact_name") or uni.get("display_name") or "",
                case_label=spec["case_label"],
                personalized_action=spec["personalized_action"],
                history_note=history,
                suggested_subject=subj,
                suggested_message=body,
                recommended_action="hold_personalized_no_generic_campaign",
            )
        )
    return out


def _dedupe_by_domain(
    candidates: list[PresentacionBatchRow],
    *,
    limit: int,
    do_not_send: list[DoNotSendRow],
    reason_code: str,
) -> list[PresentacionBatchRow]:
    """Pick best per dedupe_key; demote rest to do_not_send."""
    by_key: dict[str, PresentacionBatchRow] = {}
    for row in sorted(candidates, key=lambda r: (-r.priority_score, r.email)):
        key = row.dedupe_key or row.domain
        if key not in by_key:
            by_key[key] = row
        else:
            primary = by_key[key]
            do_not_send.append(
                DoNotSendRow(
                    email=row.email,
                    domain=row.domain,
                    organization=row.organization,
                    reason_code="domain_duplicate_secondary",
                    reason_detail=f"Contacto secundario; primario={primary.email}",
                    primary_chosen_email=primary.email,
                    classification_attempted=row.classification,
                )
            )
    ranked = sorted(by_key.values(), key=lambda r: (-r.priority_score, r.email))
    selected: list[PresentacionBatchRow] = []
    for row in ranked:
        if len(selected) >= limit:
            do_not_send.append(
                DoNotSendRow(
                    email=row.email,
                    domain=row.domain,
                    organization=row.organization,
                    reason_code=reason_code,
                    reason_detail=f"Fuera del top {limit} tras dedupe por dominio",
                    primary_chosen_email="",
                    classification_attempted=row.classification,
                )
            )
            continue
        selected.append(row)
    return selected


def run_presentacion_quality_pass(out_dir: Path) -> PresentacionQualityResult:
    out_dir = out_dir.resolve()
    send_now_raw = _load_csv_rows(out_dir / "presentacion_origenlab_send_now_review.csv")
    same_domain_raw = _load_csv_rows(out_dir / "presentacion_origenlab_same_domain_review.csv")
    universe = _load_csv_rows(out_dir / "contacted_universe_contacts.csv")
    universe_by_email = {
        (r.get("normalized_email") or "").lower(): r for r in universe if r.get("normalized_email")
    }

    hold_emails = frozenset(
        normalize_export_email(s["email"]) or s["email"].lower()
        for s in HOLD_PERSONALIZED_REGISTRY
    )

    do_not_send: list[DoNotSendRow] = []
    presentation_pool: list[PresentacionBatchRow] = []
    followup_pool: list[PresentacionBatchRow] = []

    for raw in send_now_raw:
        row = _row_from_review(raw)
        em = normalize_export_email(row.email) or ""
        if not em:
            continue
        dom = domain_of(em) or ""
        dedupe_key = _norm_org_key(row.organization, dom)
        uni = universe_by_email.get(em, {})
        subject = uni.get("latest_subject_safe") or row.history_note
        history = row.history_note
        sent_count = int(uni.get("sent_count") or 0)
        if sent_count == 0:
            m = re.search(r"envíos=(\d+)", history)
            if m:
                sent_count = int(m.group(1))

        if em in hold_emails:
            do_not_send.append(
                DoNotSendRow(
                    email=em,
                    domain=dom,
                    organization=row.organization,
                    reason_code="hold_active_personalized",
                    reason_detail="Caso activo con mensaje personalizado — ver hold CSV",
                    primary_chosen_email="",
                    classification_attempted=CLASS_HOLD_PERSONALIZED,
                )
            )
            continue

        low, low_reason = _is_low_quality_contact(em, row.organization)
        if low:
            do_not_send.append(
                DoNotSendRow(
                    email=em,
                    domain=dom,
                    organization=row.organization,
                    reason_code=low_reason,
                    reason_detail="Contacto de baja calidad para outbound comercial",
                    primary_chosen_email="",
                    classification_attempted=CLASS_EXCLUDED,
                )
            )
            continue

        sector = _sector_guess(dom, row.organization, em)
        is_followup = _is_followup_candidate(subject, history, sent_count)

        if is_followup:
            score = _followup_fit_score(
                domain=dom,
                organization=row.organization,
                email=em,
                subject=subject,
                history=history,
                base_score=row.priority_score,
            )
            topic = _topic_hint(subject, history)
            subj, body = template_followup_old_es(
                contact_name=row.contact_name,
                organization=row.organization,
                topic_hint=topic,
            )
            followup_pool.append(
                PresentacionBatchRow(
                    email=em,
                    domain=dom,
                    organization=row.organization,
                    contact_name=row.contact_name,
                    classification=CLASS_FOLLOWUP_OLD,
                    sector_guess=sector,
                    reason_for_inclusion=f"Follow-up comercial antiguo — {topic}",
                    history_note=history,
                    product_angle=row.product_angle,
                    suggested_subject=subj,
                    suggested_message=body,
                    recommended_action="operator_review_before_send",
                    priority_score=score,
                    dedupe_key=dedupe_key,
                )
            )
        else:
            score = _presentation_fit_score(
                domain=dom,
                organization=row.organization,
                email=em,
                subject=subject,
                history=history,
                base_score=row.priority_score,
            )
            if score < 30:
                do_not_send.append(
                    DoNotSendRow(
                        email=em,
                        domain=dom,
                        organization=row.organization,
                        reason_code="low_presentation_fit",
                        reason_detail=f"Score presentación {score:.0f} — universidad/público o baja calidad",
                        primary_chosen_email="",
                        classification_attempted=CLASS_PRESENTATION,
                    )
                )
                continue
            subj, body = template_presentacion_batch1_es(contact_name=row.contact_name)
            presentation_pool.append(
                PresentacionBatchRow(
                    email=em,
                    domain=dom,
                    organization=row.organization,
                    contact_name=row.contact_name,
                    classification=CLASS_PRESENTATION,
                    sector_guess=sector,
                    reason_for_inclusion="Presentación empresa — contacto antiguo sin cotización activa",
                    history_note=history,
                    product_angle=row.product_angle,
                    suggested_subject=subj,
                    suggested_message=body,
                    recommended_action="operator_review_before_send",
                    priority_score=score,
                    dedupe_key=dedupe_key,
                )
            )

    batch1 = _dedupe_by_domain(
        presentation_pool,
        limit=_BATCH1_LIMIT,
        do_not_send=do_not_send,
        reason_code="below_batch1_cutoff",
    )
    batch1_emails = {r.email for r in batch1}
    batch1_keys = {r.dedupe_key for r in batch1}
    followup_emails = {r.email for r in followup_pool}

    # Completar batch 2 con contactos comerciales previos no incluidos en batch 1.
    for raw in send_now_raw:
        row = _row_from_review(raw)
        em = normalize_export_email(row.email) or ""
        if not em or em in hold_emails or em in batch1_emails or em in followup_emails:
            continue
        dom = domain_of(em) or ""
        if not dom.endswith(".cl"):
            continue
        dedupe_key = _norm_org_key(row.organization, dom)
        if dedupe_key in batch1_keys:
            continue
        uni = universe_by_email.get(em, {})
        subject = uni.get("latest_subject_safe") or row.history_note
        history = row.history_note
        sent_count = int(uni.get("sent_count") or 0)
        if sent_count == 0:
            m = re.search(r"envíos=(\d+)", history)
            if m:
                sent_count = int(m.group(1))
        if sent_count < 1:
            continue
        low, _ = _is_low_quality_contact(em, row.organization)
        if low:
            continue
        sector = _sector_guess(dom, row.organization, em)
        score = _followup_fit_score(
            domain=dom,
            organization=row.organization,
            email=em,
            subject=subject,
            history=history,
            base_score=row.priority_score + 10,
        )
        topic = _topic_hint(subject, history)
        subj, body = template_followup_old_es(
            contact_name=row.contact_name,
            organization=row.organization,
            topic_hint=topic,
        )
        followup_pool.append(
            PresentacionBatchRow(
                email=em,
                domain=dom,
                organization=row.organization,
                contact_name=row.contact_name,
                classification=CLASS_FOLLOWUP_OLD,
                sector_guess=sector,
                reason_for_inclusion="Follow-up — contacto comercial previo sin respuesta",
                history_note=history,
                product_angle=row.product_angle,
                suggested_subject=subj,
                suggested_message=body,
                recommended_action="operator_review_before_send",
                priority_score=score,
                dedupe_key=dedupe_key,
            )
        )
        followup_emails.add(em)

    batch2 = _dedupe_by_domain(
        followup_pool,
        limit=_BATCH2_LIMIT,
        do_not_send=do_not_send,
        reason_code="below_batch2_cutoff",
    )

    selected_emails = {r.email for r in batch1} | {r.email for r in batch2}
    do_not_send = [r for r in do_not_send if r.email not in selected_emails]

    hold_personalized = _build_hold_personalized(HOLD_PERSONALIZED_REGISTRY, universe_by_email)

    same_domain_curated: list[dict[str, str]] = []
    for raw in same_domain_raw:
        em = raw.get("email") or ""
        dom = raw.get("domain") or domain_of(em) or ""
        same_domain_curated.append(
            {
                "email": em,
                "domain": dom,
                "organization": raw.get("organization") or "",
                "contact_name": raw.get("contact_name") or "",
                "review_note": (
                    "Prospecto Phase 10D — mismo dominio ya contactado. "
                    "Revisar historial manualmente; no auto-send."
                ),
                "product_angle": raw.get("product_angle") or "",
                "recommended_action": "review_history_only_no_auto_send",
                "priority_score": raw.get("priority_score") or "",
            }
        )

    dup_domains_removed = sum(
        1 for r in do_not_send if r.reason_code == "domain_duplicate_secondary"
    )
    reason_counts: dict[str, int] = {}
    for r in do_not_send:
        reason_counts[r.reason_code] = reason_counts.get(r.reason_code, 0) + 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_quality_pass",
        "input_send_now_count": len(send_now_raw),
        "batch1_count": len(batch1),
        "batch2_count": len(batch2),
        "hold_personalized_count": len(hold_personalized),
        "same_domain_curated_count": len(same_domain_curated),
        "do_not_send_count": len(do_not_send),
        "domains_duplicate_secondaries_removed": dup_domains_removed,
        "exclusion_reason_counts": reason_counts,
        "top_batch1": [{"email": r.email, "org": r.organization, "score": r.priority_score} for r in batch1[:10]],
        "top_batch2": [{"email": r.email, "org": r.organization, "score": r.priority_score} for r in batch2[:10]],
    }

    batch1_md = render_batch_messages_markdown(
        batch1,
        title="Presentación OrigenLab — Batch 1 (top 25)",
        intro="Presentación empresa genérica. Mención Cyber suave hasta 7 de junio.",
    )
    followup_md = render_batch_messages_markdown(
        batch2,
        title="Presentación OrigenLab — Batch 2 follow-up (top 25)",
        intro="Follow-up comercial antiguo — retomar cotización o contacto previo.",
    )

    return PresentacionQualityResult(
        batch1=batch1,
        batch2=batch2,
        hold_personalized=hold_personalized,
        same_domain_curated=same_domain_curated,
        do_not_send=do_not_send,
        summary=summary,
        batch1_markdown=batch1_md,
        followup_markdown=followup_md,
    )


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fields))
        w.writeheader()
        for row in rows:
            if isinstance(row, dict):
                w.writerow({k: row.get(k, "") for k in fields})
            else:
                w.writerow(row.to_csv_dict())


def write_presentacion_quality_outputs(
    result: PresentacionQualityResult, out_dir: Path
) -> dict[str, Path]:
    out_dir = out_dir.resolve()
    paths = {
        "batch1": out_dir / OUTPUT_BATCH1,
        "batch2": out_dir / OUTPUT_BATCH2,
        "hold": out_dir / OUTPUT_HOLD,
        "same_domain": out_dir / OUTPUT_SAME_DOMAIN,
        "do_not_send": out_dir / OUTPUT_DO_NOT_SEND,
        "batch1_msg": out_dir / OUTPUT_BATCH1_MSG,
        "followup_msg": out_dir / OUTPUT_FOLLOWUP_MSG,
        "summary_json": out_dir / "presentacion_quality_summary.json",
    }
    _write_csv(paths["batch1"], BATCH_CSV_FIELDS, result.batch1)
    _write_csv(paths["batch2"], BATCH_CSV_FIELDS, result.batch2)
    _write_csv(paths["hold"], HOLD_PERSONALIZED_FIELDS, result.hold_personalized)
    _write_csv(paths["same_domain"], SAME_DOMAIN_CURATED_FIELDS, result.same_domain_curated)
    _write_csv(paths["do_not_send"], DO_NOT_SEND_FIELDS, result.do_not_send)
    paths["batch1_msg"].write_text(result.batch1_markdown, encoding="utf-8")
    paths["followup_msg"].write_text(result.followup_markdown, encoding="utf-8")
    paths["summary_json"].write_text(
        json.dumps(result.summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paths
