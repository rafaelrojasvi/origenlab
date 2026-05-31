"""Cyber campaign Phase 1.1 — geography, org dedupe, Phase 10D net-new (read-only)."""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import domain_of
from origenlab_email_pipeline.candidate_export_gate import normalize_export_email
from origenlab_email_pipeline.campaigns.cyber_campaign_gate import (
    classify_safety,
    product_angle,
)
from origenlab_email_pipeline.campaigns.cyber_campaign_templates import apply_templates_to_row
from origenlab_email_pipeline.campaigns.cyber_campaign_types import (
    SEGMENT_EXCLUDED,
    SEGMENT_NET_NEW,
    SEGMENT_NET_NEW_LEAD_RESEARCH,
    SEGMENT_PREVIOUS,
    SEGMENT_WARM,
    CyberCampaignRow,
)
from origenlab_email_pipeline.lead_research.lead_research_schema import lead_research_tables_exist
from origenlab_email_pipeline.leads.new_customer_research import CLASS_NET_NEW

GEO_CHILE_OK = "chile_ok"
GEO_MANUAL_REVIEW = "manual_review_foreign"
GEO_EXCLUDED = "excluded_foreign"

_REVIEW_CSV_NAME = "new_customer_targets_review.csv"

_CHILE_REGION_MARKERS: tuple[str, ...] = (
    "chile",
    "metropolitana",
    "valparaíso",
    "valparaiso",
    "biobío",
    "biobio",
    "araucanía",
    "araucania",
    "ohiggins",
    "maule",
    "antofagasta",
    "atacama",
    "coquimbo",
    "los ríos",
    "los rios",
    "los lagos",
    "aysén",
    "aysen",
    "magallanes",
    "tarapacá",
    "tarapaca",
    "arica",
    "ñuble",
    "nuble",
)

_LAB_BUYER_TYPES: tuple[str, ...] = (
    "laboratorio_privado",
    "laboratorio_alimentos",
    "laboratorio_acuicola",
    "laboratorio_agua",
    "laboratorio_clinico",
    "centro_ensayos",
    "laboratorio",
    "qc",
    "control_calidad",
)

_GENERIC_LOCALS: frozenset[str] = frozenset(
    {
        "info",
        "contacto",
        "contact",
        "ventas",
        "sales",
        "admin",
        "administracion",
        "recepcion",
        "servicios",
        "servicios2",
        "comunicaciones",
        "atencion",
        "atencionalcliente",
    }
)

# Active commercial threads — exclude from Cyber mass promo (operator digest May 2026).
_ACTIVE_WARM_BLOCK_DOMAINS: frozenset[str] = frozenset(
    {
        "bureauveritas.com",
        "hielscher.com",
        "uach.cl",
        "adventista.cl",
        "dhl.com",
        "mybill.dhl.com",
    }
)
_ACTIVE_WARM_ORG_MARKERS: tuple[str, ...] = (
    "cesmec",
    "unach",
    "adventista",
    "hielscher",
    "uip2000",
    "bureau veritas",
    "bureauveritas",
)
_ACTIVE_WARM_EMAIL_MARKERS: tuple[str, ...] = (
    "hielscher",
    "marcos@hielscher",
    "mybill",
    "dhl",
)

_FOREIGN_TLD_SUFFIXES: tuple[str, ...] = (
    ".gov.gh",
    ".gov.uk",
    ".gov.au",
    ".gov.br",
    ".go.id",
    ".gov.in",
)

CSV_FIELDS_EXTENDED: tuple[str, ...] = (
    "email",
    "organization",
    "contact_name",
    "segment",
    "reason_for_inclusion",
    "product_angle",
    "suggested_subject",
    "suggested_message",
    "safety_status",
    "exclusion_reason",
    "domain",
    "secondary_contact_emails",
    "geo_status",
    "selection_rationale",
)

GEO_MANUAL_FIELDS: tuple[str, ...] = (
    *CSV_FIELDS_EXTENDED,
    "geo_review_reason",
)


@dataclass
class QualityPassResult:
    warm: list[CyberCampaignRow]
    previous_buyers: list[CyberCampaignRow]
    net_new: list[CyberCampaignRow]
    net_new_lead_research: list[CyberCampaignRow]
    same_domain: list[CyberCampaignRow]
    excluded: list[CyberCampaignRow]
    manual_geo: list[CyberCampaignRow]
    top25_raw: list[CyberCampaignRow]
    top25_deduped: list[CyberCampaignRow]
    metrics: dict[str, Any]


def is_generic_mailbox(email: str) -> bool:
    local = (email or "").split("@", 1)[0].strip().lower()
    if not local:
        return True
    if local in _GENERIC_LOCALS:
        return True
    return any(local == g or local.startswith(f"{g}.") or local.startswith(f"{g}+") for g in _GENERIC_LOCALS)


def _has_chile_evidence(
    *,
    region: str,
    organization: str,
    buyer_type: str,
    sector: str,
) -> bool:
    blob = " ".join((region, organization, buyer_type, sector)).lower()
    if "chile" in blob:
        return True
    reg = (region or "").lower()
    return any(m in reg for m in _CHILE_REGION_MARKERS)


def is_active_warm_sales_thread(
    email: str,
    *,
    organization: str = "",
    domain: str = "",
) -> tuple[bool, str]:
    """True when contact belongs to an open warm/sales thread (not Cyber blast)."""
    em = (email or "").strip().lower()
    dom = (domain or domain_of(em) or "").strip().lower()
    org_l = (organization or "").lower()
    if dom in _ACTIVE_WARM_BLOCK_DOMAINS:
        return True, f"hilo comercial activo — dominio {dom}"
    if any(dom.endswith("." + d) or dom == d for d in _ACTIVE_WARM_BLOCK_DOMAINS):
        return True, f"hilo comercial activo — dominio {dom}"
    if any(m in org_l for m in _ACTIVE_WARM_ORG_MARKERS):
        return True, f"hilo comercial activo — organización ({organization})"
    if any(m in em for m in _ACTIVE_WARM_EMAIL_MARKERS):
        return True, "hilo comercial activo — contacto en seguimiento"
    return False, ""


def apply_active_warm_promo_exclusions(
    rows: list[CyberCampaignRow],
    meta_by_email: dict[str, dict[str, Any]],
) -> tuple[list[CyberCampaignRow], list[CyberCampaignRow]]:
    """Move active warm-thread contacts out of Cyber promo lists."""
    kept: list[CyberCampaignRow] = []
    manual: list[CyberCampaignRow] = []
    for r in rows:
        meta = meta_by_email.get(r.email, {})
        blocked, reason = is_active_warm_sales_thread(
            r.email,
            organization=r.organization,
            domain=str(meta.get("domain") or ""),
        )
        if blocked:
            meta["geo_review_reason"] = reason
            meta["geo_status"] = "active_warm_thread"
            meta_by_email[r.email] = meta
            manual.append(r)
        else:
            kept.append(r)
    return kept, manual


def classify_geography(
    email: str,
    *,
    domain: str = "",
    region: str = "",
    organization: str = "",
    buyer_type: str = "",
    sector: str = "",
) -> tuple[str, str]:
    """Conservative Chile filter for Cyber CL campaign."""
    em = (email or "").strip().lower()
    dom = (domain or domain_of(em) or "").strip().lower()
    if not dom:
        return GEO_MANUAL_REVIEW, "sin dominio"

    if dom.endswith(".cl"):
        return GEO_CHILE_OK, "dominio .cl"

    if _has_chile_evidence(
        region=region, organization=organization, buyer_type=buyer_type, sector=sector
    ):
        return GEO_CHILE_OK, "evidencia Chile (región/organización)"

    for suffix in _FOREIGN_TLD_SUFFIXES:
        if dom.endswith(suffix) or suffix.strip(".") in dom:
            return GEO_MANUAL_REVIEW, f"dominio gubernamental/extranjero ({dom})"

    if dom.endswith(".gh") or dom.endswith(".ng") or dom.endswith(".za"):
        return GEO_MANUAL_REVIEW, f"TLD país no Chile ({dom})"

    if ".gov." in dom and not dom.endswith(".cl"):
        return GEO_MANUAL_REVIEW, f"dominio gobierno no .cl ({dom})"

    if not dom.endswith(".cl"):
        return GEO_MANUAL_REVIEW, f"dominio no .cl sin evidencia Chile ({dom})"

    return GEO_CHILE_OK, ""


def enrich_priority_score(row: CyberCampaignRow, meta: dict[str, Any]) -> float:
    score = float(row.priority_score or 0.0)
    if row.segment == SEGMENT_WARM:
        score += 200.0
    elif row.segment == SEGMENT_PREVIOUS:
        score += 80.0
    elif row.segment in (SEGMENT_NET_NEW, SEGMENT_NET_NEW_LEAD_RESEARCH):
        score += 50.0
        score += float(meta.get("final_score") or 0) * 0.5

    buyer = str(meta.get("buyer_type") or "").lower()
    sector = str(meta.get("sector") or "").lower()
    if any(t in buyer for t in _LAB_BUYER_TYPES):
        score += 35.0
    if "alimento" in sector or "acuicola" in sector or "clinica" in sector:
        score += 20.0
    if "universidad" in sector or buyer == "centro_investigacion":
        score -= 12.0
    if (row.contact_name or "").strip():
        score += 18.0
    if is_generic_mailbox(row.email):
        score -= 28.0
    dom = str(meta.get("domain") or domain_of(row.email) or "")
    if dom.endswith(".cl"):
        score += 12.0
    if meta.get("source_tag") == "lead_research_phase10d":
        score += 8.0
    return score


def _row_meta(raw: dict[str, Any]) -> dict[str, Any]:
    return dict(raw.get("_meta") or {})


def _read_review_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _load_lead_research_from_sqlite(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    if not lead_research_tables_exist(conn):
        return []
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT organization_name, contact_name, email, domain,
               sector, region, buyer_type, product_angle, likely_need,
               final_score, classification, spanish_message_angle,
               recommended_next_action, confidence, status, is_blocked
        FROM lead_research_prospect
        WHERE is_active = 1
          AND is_blocked = 0
          AND classification = ?
          AND status = 'net_new_safe_review'
          AND length(trim(COALESCE(email, ''))) > 0
        ORDER BY final_score DESC, organization_name
        """,
        (CLASS_NET_NEW,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(_lead_research_row_to_candidate(dict(r), source_tag="lead_research_sqlite"))
    return out


def _lead_research_row_to_candidate(row: dict[str, Any], *, source_tag: str) -> dict[str, Any]:
    em = normalize_export_email(row.get("email") or "") or ""
    org = str(row.get("organization_name") or "").strip()
    angle = str(row.get("spanish_message_angle") or row.get("product_angle") or "").strip()
    product = str(row.get("product_angle") or row.get("likely_need") or angle).strip()
    final_score = float(row.get("final_score") or 0)
    return {
        "email": em,
        "organization": org,
        "contact_name": str(row.get("contact_name") or "").strip(),
        "segment": SEGMENT_NET_NEW,
        "reason_for_inclusion": (
            f"Phase 10D net_new_safe_review; score {final_score:.0f}; "
            f"fuente {source_tag}"
        ),
        "product_angle": product or product_angle(),
        "priority_score": final_score,
        "_meta": {
            "domain": str(row.get("domain") or domain_of(em) or "").strip().lower(),
            "region": str(row.get("region") or "").strip(),
            "buyer_type": str(row.get("buyer_type") or "").strip(),
            "sector": str(row.get("sector") or "").strip(),
            "final_score": final_score,
            "source_tag": "lead_research_phase10d",
            "classification": CLASS_NET_NEW,
        },
    }


def gather_lead_research_net_new(
    conn: sqlite3.Connection,
    *,
    review_csv: Path | None,
) -> list[dict[str, Any]]:
    """Phase 10D prospects: SQLite mirror first, CSV fallback, net_new_safe only."""
    by_email: dict[str, dict[str, Any]] = {}
    for raw in _load_lead_research_from_sqlite(conn):
        em = raw.get("email") or ""
        if em:
            by_email[em] = raw

    if review_csv and review_csv.is_file():
        for row in _read_review_csv(review_csv):
            if (row.get("classification") or "").strip() != CLASS_NET_NEW:
                continue
            parsed = _lead_research_row_to_candidate(row, source_tag="lead_research_csv")
            em = parsed.get("email") or ""
            if not em:
                continue
            prev = by_email.get(em)
            if prev is None or float(parsed.get("priority_score") or 0) > float(
                prev.get("priority_score") or 0
            ):
                by_email[em] = parsed
    return list(by_email.values())


def finalize_lead_research_candidates(
    candidates: list[dict[str, Any]],
    *,
    gate_ctx: Any,
    universe_ctx: Any,
    meta_by_email: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[CyberCampaignRow], list[CyberCampaignRow], list[CyberCampaignRow]]:
    """Gate + geo split for Phase 10D net-new only."""
    eligible: list[CyberCampaignRow] = []
    manual: list[CyberCampaignRow] = []
    excluded: list[CyberCampaignRow] = []

    for raw in candidates:
        em = raw.get("email") or ""
        if not em:
            continue
        meta = _row_meta(raw)
        org = str(raw.get("organization") or "")
        if meta_by_email is not None:
            meta_by_email.setdefault(em, {}).update(meta)
        safety, excl = classify_safety(em, org or None, gate_ctx=gate_ctx, universe_ctx=universe_ctx)
        geo, geo_reason = classify_geography(
            em,
            domain=str(meta.get("domain") or ""),
            region=str(meta.get("region") or ""),
            organization=org,
            buyer_type=str(meta.get("buyer_type") or ""),
            sector=str(meta.get("sector") or ""),
        )
        base = CyberCampaignRow(
            email=em,
            organization=org,
            contact_name=str(raw.get("contact_name") or ""),
            segment=SEGMENT_NET_NEW_LEAD_RESEARCH,
            reason_for_inclusion=str(raw.get("reason_for_inclusion") or ""),
            product_angle=str(raw.get("product_angle") or ""),
            suggested_subject="",
            suggested_message="",
            safety_status=safety,
            exclusion_reason=excl,
            priority_score=float(raw.get("priority_score") or 0.0),
        )
        if safety != "eligible":
            excluded.append(
                replace(base, segment=SEGMENT_EXCLUDED, safety_status="blocked")
            )
            continue
        if geo != GEO_CHILE_OK:
            meta["geo_status"] = geo
            meta["geo_review_reason"] = geo_reason
            manual.append(
                replace(
                    apply_templates_to_row(replace(base, segment=SEGMENT_NET_NEW)),
                    segment=SEGMENT_NET_NEW,
                    exclusion_reason=geo_reason,
                )
            )
            continue
        row = apply_templates_to_row(replace(base, segment=SEGMENT_NET_NEW))
        row = replace(row, priority_score=enrich_priority_score(row, meta))
        eligible.append(row)
    eligible.sort(key=lambda r: -r.priority_score)
    return eligible, manual, excluded


def dedupe_by_domain(
    rows: list[CyberCampaignRow],
    meta_by_email: dict[str, dict[str, Any]],
) -> tuple[list[CyberCampaignRow], dict[str, Any]]:
    """One primary contact per domain; alternates in secondary_contact_emails."""
    groups: dict[str, list[CyberCampaignRow]] = {}
    for r in rows:
        meta = meta_by_email.get(r.email, {})
        dom = str(meta.get("domain") or domain_of(r.email) or "").strip().lower()
        key = dom or f"email:{r.email}"
        groups.setdefault(key, []).append(r)

    deduped: list[CyberCampaignRow] = []
    alternates_total = 0
    for _key, group in groups.items():
        enriched = [
            (r, enrich_priority_score(r, meta_by_email.get(r.email, {}))) for r in group
        ]
        enriched.sort(key=lambda x: (-x[1], x[0].email))
        primary, score = enriched[0]
        alts = [e for e, _ in enriched[1:] if e.email != primary.email]
        alternates_total += len(alts)
        meta = meta_by_email.get(primary.email, {})
        rationale = _selection_rationale(primary, meta, score)
        secondaries = ";".join(a.email for a in alts[:5])
        deduped.append(replace(primary, priority_score=score))
        meta_by_email[primary.email] = {
            **meta,
            "domain": str(meta.get("domain") or domain_of(primary.email) or ""),
            "secondary_contact_emails": secondaries,
            "selection_rationale": rationale,
            "geo_status": meta.get("geo_status") or GEO_CHILE_OK,
        }

    deduped.sort(key=lambda r: -r.priority_score)
    stats = {
        "rows_before": len(rows),
        "rows_after": len(deduped),
        "domains_with_alternates": sum(
            1 for m in meta_by_email.values() if m.get("secondary_contact_emails")
        ),
        "alternate_contacts_collapsed": alternates_total,
    }
    return deduped, stats


def _selection_rationale(row: CyberCampaignRow, meta: dict[str, Any], score: float) -> str:
    parts = [f"score={score:.0f}", f"segment={row.segment}"]
    if meta.get("source_tag") == "lead_research_phase10d":
        parts.append("Phase10D")
    if (row.contact_name or "").strip():
        parts.append("contacto_nominado")
    if is_generic_mailbox(row.email):
        parts.append("buzón_genérico")
    buyer = str(meta.get("buyer_type") or "")
    if buyer:
        parts.append(f"buyer={buyer}")
    return "; ".join(parts)


def apply_geography_to_eligible(
    rows: list[CyberCampaignRow],
    meta_by_email: dict[str, dict[str, Any]],
) -> tuple[list[CyberCampaignRow], list[CyberCampaignRow]]:
    """Move non-Chile default rows to manual geo review."""
    kept: list[CyberCampaignRow] = []
    manual: list[CyberCampaignRow] = []
    for r in rows:
        meta = meta_by_email.get(r.email, {})
        geo, reason = classify_geography(
            r.email,
            domain=str(meta.get("domain") or ""),
            region=str(meta.get("region") or ""),
            organization=r.organization,
            buyer_type=str(meta.get("buyer_type") or ""),
            sector=str(meta.get("sector") or ""),
        )
        meta["geo_status"] = geo
        meta["geo_review_reason"] = reason
        if geo == GEO_CHILE_OK:
            kept.append(replace(r, priority_score=enrich_priority_score(r, meta)))
        else:
            meta_by_email[r.email] = meta
            manual.append(r)
    return kept, manual


def build_top25_deduped(
    warm: list[CyberCampaignRow],
    previous: list[CyberCampaignRow],
    net_new: list[CyberCampaignRow],
    meta_by_email: dict[str, dict[str, Any]],
    *,
    n: int = 25,
) -> tuple[list[CyberCampaignRow], list[CyberCampaignRow]]:
    pool = warm + previous + net_new
    pool.sort(
        key=lambda r: -enrich_priority_score(r, meta_by_email.get(r.email, {})),
    )
    top25_raw = pool[:n]
    top25_deduped, _ = dedupe_by_domain(pool, meta_by_email)
    seen_domains: set[str] = set()
    picked: list[CyberCampaignRow] = []
    for r in top25_deduped:
        meta = meta_by_email.get(r.email, {})
        dom = str(meta.get("domain") or domain_of(r.email) or "").lower()
        key = dom or r.email
        if key in seen_domains:
            continue
        seen_domains.add(key)
        picked.append(r)
        if len(picked) >= n:
            break
    return top25_raw, picked


def row_to_extended_csv(row: CyberCampaignRow, meta_by_email: dict[str, dict[str, Any]]) -> dict[str, str]:
    meta = meta_by_email.get(row.email, {})
    d = row.to_csv_dict()
    d["domain"] = str(meta.get("domain") or domain_of(row.email) or "")
    d["secondary_contact_emails"] = str(meta.get("secondary_contact_emails") or "")
    d["geo_status"] = str(meta.get("geo_status") or GEO_CHILE_OK)
    d["selection_rationale"] = str(meta.get("selection_rationale") or "")
    return d


def row_to_geo_manual_csv(row: CyberCampaignRow, meta_by_email: dict[str, dict[str, Any]]) -> dict[str, str]:
    d = row_to_extended_csv(row, meta_by_email)
    meta = meta_by_email.get(row.email, {})
    d["geo_review_reason"] = str(
        meta.get("geo_review_reason") or row.exclusion_reason or "revisión geografía"
    )
    return d


def apply_quality_pass(
    *,
    warm: list[CyberCampaignRow],
    previous: list[CyberCampaignRow],
    net_new: list[CyberCampaignRow],
    same_domain: list[CyberCampaignRow],
    excluded: list[CyberCampaignRow],
    lead_research_eligible: list[CyberCampaignRow],
    lead_research_manual: list[CyberCampaignRow],
    lead_research_excluded: list[CyberCampaignRow],
    meta_by_email: dict[str, dict[str, Any]],
) -> QualityPassResult:
    """Merge lead research net-new, geo-filter, org-dedupe, rebuild top25."""
    manual_geo: list[CyberCampaignRow] = list(lead_research_manual)

    warm_geo, warm_manual = apply_geography_to_eligible(warm, meta_by_email)
    prev_geo, prev_manual = apply_geography_to_eligible(previous, meta_by_email)
    net_geo, net_manual = apply_geography_to_eligible(net_new, meta_by_email)
    manual_geo.extend(warm_manual)
    manual_geo.extend(prev_manual)
    manual_geo.extend(net_manual)

    warm_geo, warm_active = apply_active_warm_promo_exclusions(warm_geo, meta_by_email)
    prev_geo, prev_active = apply_active_warm_promo_exclusions(prev_geo, meta_by_email)
    net_geo, net_active = apply_active_warm_promo_exclusions(net_geo, meta_by_email)
    manual_geo.extend(warm_active)
    manual_geo.extend(prev_active)
    manual_geo.extend(net_active)

    net_by_email: dict[str, CyberCampaignRow] = {}
    for r in net_geo + lead_research_eligible:
        prev = net_by_email.get(r.email)
        if prev is None or r.priority_score > prev.priority_score:
            net_by_email[r.email] = r
    net_merged = sorted(net_by_email.values(), key=lambda r: -r.priority_score)

    warm_deduped, warm_stats = dedupe_by_domain(warm_geo, meta_by_email)
    prev_deduped, prev_stats = dedupe_by_domain(prev_geo, meta_by_email)
    net_deduped, net_stats = dedupe_by_domain(net_merged, meta_by_email)
    lr_deduped, lr_stats = dedupe_by_domain(lead_research_eligible, meta_by_email)

    excluded_all = list(excluded) + lead_research_excluded

    top25_raw, top25_deduped = build_top25_deduped(
        warm_deduped, prev_deduped, net_deduped, meta_by_email
    )

    metrics = {
        "org_dedupe": {
            "warm": warm_stats,
            "previous": prev_stats,
            "net_new": net_stats,
            "lead_research": lr_stats,
        },
        "lead_research_net_new_recovered": len(lead_research_eligible),
        "lead_research_manual_geo": len(lead_research_manual),
        "lead_research_gate_excluded": len(lead_research_excluded),
        "manual_geo_total": len(manual_geo),
        "active_warm_thread_excluded": len(warm_active) + len(prev_active) + len(net_active),
        "top25_raw_count": len(top25_raw),
        "top25_deduped_count": len(top25_deduped),
    }
    return QualityPassResult(
        warm=warm_deduped,
        previous_buyers=prev_deduped,
        net_new=net_deduped,
        net_new_lead_research=lr_deduped,
        same_domain=same_domain,
        excluded=excluded_all,
        manual_geo=manual_geo,
        top25_raw=top25_raw,
        top25_deduped=top25_deduped,
        metrics=metrics,
    )
