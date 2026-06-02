"""Overlay exact-email outreach/suppression state onto lead_research prospect rows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from origenlab_email_pipeline.business_mart import domain_of

CLASS_MANUAL_OUTREACH_SENT = "manual_outreach_sent"
CLASS_BOUNCED_SUPPRESSED = "bounced_suppressed"
CLASS_SAME_DOMAIN_CONTACTED_REVIEW = "same_domain_contacted_review"
CLASS_RESEARCH_ONLY = "research_only_contact_needed"
STATUS_MANUAL_CONTACTED = "manual_outreach_contacted"
STATUS_BOUNCED_SUPPRESSED = "bounced_suppressed"
STATUS_SAME_DOMAIN_REVIEW = "same_domain_review"
SAME_DOMAIN_EMPTY_EMAIL_ACTION = (
    "Ya existe contacto por dominio; revisar historial antes de cualquier acción."
)

_BOUNCE_REASON_PREFIX = "bounce_"
_CONTACTED_STATES = frozenset({"contacted", "replied"})


@dataclass
class SuppressionHit:
    reason_code: str
    reason_text: str | None = None


@dataclass
class OutreachHit:
    state: str
    source: str | None = None


@dataclass
class OperationalEmailIndexes:
    suppressions: dict[str, SuppressionHit] = field(default_factory=dict)
    outreach: dict[str, OutreachHit] = field(default_factory=dict)
    domain_suppressions: dict[str, str] = field(default_factory=dict)
    domains_with_contacted: set[str] = field(default_factory=set)
    domains_with_bounce_suppression: set[str] = field(default_factory=set)


def prospect_domain_norm(prospect: dict[str, Any]) -> str | None:
    """Normalized domain from prospect row (domain column or email suffix)."""
    dom = str(prospect.get("domain") or "").strip().lower()
    if dom:
        return dom
    return domain_of(normalize_prospect_email(prospect.get("email")))


def finalize_domain_operational_indexes(idx: OperationalEmailIndexes) -> None:
    """Derive domain-level contacted/bounce sets from exact-email sidecars."""
    idx.domains_with_contacted.clear()
    idx.domains_with_bounce_suppression.clear()
    for em, ocs in idx.outreach.items():
        if ocs.state in _CONTACTED_STATES:
            dom = domain_of(em)
            if dom:
                idx.domains_with_contacted.add(dom)
    for em, sup in idx.suppressions.items():
        if is_bounce_suppression_reason(sup.reason_code):
            dom = domain_of(em)
            if dom:
                idx.domains_with_bounce_suppression.add(dom)


def normalize_prospect_email(email: str | None) -> str | None:
    if not email:
        return None
    s = str(email).strip().lower()
    return s or None


def is_bounce_suppression_reason(code: str | None) -> bool:
    if not code:
        return False
    c = code.strip().lower()
    return c.startswith(_BOUNCE_REASON_PREFIX) or c in {
        "reported_non_delivery",
        "manual_do_not_contact",
    }


def load_operational_indexes_from_sqlite(conn: sqlite3.Connection) -> OperationalEmailIndexes:
    idx = OperationalEmailIndexes()
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contact_email_suppression'"
    ).fetchone():
        for row in conn.execute(
            """
            SELECT email, suppression_reason_code, suppression_reason_text
            FROM contact_email_suppression
            """
        ):
            em = normalize_prospect_email(row[0])
            if em:
                idx.suppressions[em] = SuppressionHit(
                    reason_code=str(row[1] or ""),
                    reason_text=(str(row[2]).strip() if row[2] else None),
                )
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='outreach_contact_state'"
    ).fetchone():
        for row in conn.execute(
            """
            SELECT contact_email_norm, state, source
            FROM outreach_contact_state
            """
        ):
            em = normalize_prospect_email(row[0])
            if em:
                idx.outreach[em] = OutreachHit(
                    state=str(row[1] or ""),
                    source=(str(row[2]).strip() if row[2] else None),
                )
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contact_domain_suppression'"
    ).fetchone():
        for row in conn.execute(
            "SELECT domain_norm, suppression_reason_text FROM contact_domain_suppression"
        ):
            dom = str(row[0] or "").strip().lower()
            if dom:
                idx.domain_suppressions[dom] = str(row[1] or "domain_suppressed")
    finalize_domain_operational_indexes(idx)
    return idx


def load_operational_indexes_from_postgres(
    conn: Any,
    *,
    emails: list[str] | None = None,
) -> OperationalEmailIndexes:
    """Load outbound sidecar rows (Postgres mirror). ``emails`` limits query size when set."""
    from origenlab_email_pipeline.postgres_dashboard_api.db import fetch_all, table_exists

    idx = OperationalEmailIndexes()
    if table_exists(conn, schema="outbound", table="contact_email_suppression"):
        if emails:
            norms = sorted({e for e in (normalize_prospect_email(x) for x in emails) if e})
            if norms:
                rows = fetch_all(
                    conn,
                    """
                    SELECT email, suppression_reason_code, suppression_reason_text
                    FROM outbound.contact_email_suppression
                    WHERE LOWER(TRIM(email)) = ANY(%s)
                    """,
                    [norms],
                )
            else:
                rows = []
        else:
            rows = fetch_all(
                conn,
                """
                SELECT email, suppression_reason_code, suppression_reason_text
                FROM outbound.contact_email_suppression
                """,
            )
        for row in rows:
            em = normalize_prospect_email(row.get("email"))
            if em:
                idx.suppressions[em] = SuppressionHit(
                    reason_code=str(row.get("suppression_reason_code") or ""),
                    reason_text=(
                        str(row["suppression_reason_text"]).strip()
                        if row.get("suppression_reason_text")
                        else None
                    ),
                )

    if table_exists(conn, schema="outbound", table="outreach_contact_state"):
        if emails:
            norms = sorted({e for e in (normalize_prospect_email(x) for x in emails) if e})
            if norms:
                rows = fetch_all(
                    conn,
                    """
                    SELECT contact_email_norm, state, source
                    FROM outbound.outreach_contact_state
                    WHERE LOWER(TRIM(contact_email_norm)) = ANY(%s)
                    """,
                    [norms],
                )
            else:
                rows = []
        else:
            rows = fetch_all(
                conn,
                """
                SELECT contact_email_norm, state, source
                FROM outbound.outreach_contact_state
                """,
            )
        for row in rows:
            em = normalize_prospect_email(row.get("contact_email_norm"))
            if em:
                idx.outreach[em] = OutreachHit(
                    state=str(row.get("state") or ""),
                    source=(str(row["source"]).strip() if row.get("source") else None),
                )
    if table_exists(conn, schema="outbound", table="contact_domain_suppression"):
        rows = fetch_all(
            conn,
            """
            SELECT domain_norm, suppression_reason_text
            FROM outbound.contact_domain_suppression
            """,
        )
        for row in rows:
            dom = str(row.get("domain_norm") or "").strip().lower()
            if dom:
                idx.domain_suppressions[dom] = str(row.get("suppression_reason_text") or "")
    finalize_domain_operational_indexes(idx)
    return idx


def apply_operational_overlay_to_prospect(
    prospect: dict[str, Any],
    indexes: OperationalEmailIndexes,
) -> dict[str, Any]:
    """Return prospect dict with classification/status overridden from sidecars (suppression wins)."""
    em = normalize_prospect_email(prospect.get("email"))
    if not em:
        return _apply_empty_email_domain_overlay(prospect, indexes)

    sup = indexes.suppressions.get(em)
    if sup and is_bounce_suppression_reason(sup.reason_code):
        out = dict(prospect)
        out["classification"] = CLASS_BOUNCED_SUPPRESSED
        out["status"] = STATUS_BOUNCED_SUPPRESSED
        out["is_blocked"] = True
        out["campaign_bucket"] = "blocked"
        out["block_or_review_reason"] = sup.reason_code
        out["recommended_next_action"] = "No contactar: rebote / suprimido"
        flags = (out.get("risk_flags") or "").strip()
        tag = "exact_email_suppressed"
        out["risk_flags"] = f"{flags},{tag}".strip(",") if flags else tag
        return out

    ocs = indexes.outreach.get(em)
    if ocs and ocs.state in _CONTACTED_STATES:
        out = dict(prospect)
        out["classification"] = CLASS_MANUAL_OUTREACH_SENT
        out["status"] = STATUS_MANUAL_CONTACTED
        out["is_blocked"] = False
        out["recommended_next_action"] = "Esperar respuesta; no reenviar ahora"
        src = (ocs.source or "").strip()
        if src:
            out["block_or_review_reason"] = f"contactado:{src}"
        else:
            out["block_or_review_reason"] = "contactado_operacional"
        return out

    return prospect


def _apply_empty_email_domain_overlay(
    prospect: dict[str, Any],
    indexes: OperationalEmailIndexes,
) -> dict[str, Any]:
    """Display-only: Falta-email rows with same-domain evidence → revisar historial."""
    if str(prospect.get("classification") or "") != CLASS_RESEARCH_ONLY:
        return prospect

    domain = prospect_domain_norm(prospect)
    if not domain:
        return prospect

    if domain in indexes.domain_suppressions or domain in indexes.domains_with_bounce_suppression:
        out = dict(prospect)
        out["classification"] = CLASS_BOUNCED_SUPPRESSED
        out["status"] = STATUS_BOUNCED_SUPPRESSED
        out["is_blocked"] = True
        out["campaign_bucket"] = "blocked"
        reason = indexes.domain_suppressions.get(domain) or "domain_bounce_suppressed"
        out["block_or_review_reason"] = reason
        out["recommended_next_action"] = "No contactar: rebote / suprimido"
        return out

    has_gmail = int(prospect.get("gmail_sent_count") or 0) > 0 or bool(
        prospect.get("gmail_last_contacted_at")
    )
    if domain not in indexes.domains_with_contacted and not has_gmail:
        return prospect

    out = dict(prospect)
    out["classification"] = CLASS_SAME_DOMAIN_CONTACTED_REVIEW
    out["status"] = STATUS_SAME_DOMAIN_REVIEW
    out["is_blocked"] = False
    out["campaign_bucket"] = "same_domain"
    out["recommended_next_action"] = SAME_DOMAIN_EMPTY_EMAIL_ACTION
    out["block_or_review_reason"] = "contactado_mismo_dominio_sin_email_fila"
    flags = str(out.get("risk_flags") or "").strip()
    tag = "contactado_mismo_dominio_sin_email"
    out["risk_flags"] = f"{flags},{tag}".strip(",") if flags else tag
    return out


def overlay_block_reasons_for_prospects(
    prospects: list[dict[str, Any]],
    original: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace block reasons when operational overlay changes classification.

  Raw SQLite ``lead_research_block_reason`` rows for contacted/manual and
  same-domain review reasons are dropped; bounced prospects get a single
  ``Rebotado / suprimido`` row. Mirror verify must compare Postgres to these
  built counts, not raw SQLite totals.
  """
    overlay_keys = {
        p["prospect_key"]
        for p in prospects
        if p.get("classification")
        in (
            CLASS_BOUNCED_SUPPRESSED,
            CLASS_MANUAL_OUTREACH_SENT,
            CLASS_SAME_DOMAIN_CONTACTED_REVIEW,
        )
    }
    kept = [br for br in original if br.get("prospect_key") not in overlay_keys]
    for p in prospects:
        if p.get("classification") != CLASS_BOUNCED_SUPPRESSED:
            continue
        code = str(p.get("block_or_review_reason") or "bounced_suppressed")
        kept.append(
            {
                "prospect_key": p["prospect_key"],
                "reason_code": code,
                "reason_label": "Rebotado / suprimido",
            }
        )
    return kept


def overlay_recommendations_for_prospects(
    prospects: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key = {r["prospect_key"]: dict(r) for r in recommendations}
    out: list[dict[str, Any]] = []
    for p in prospects:
        rec = by_key.get(p["prospect_key"])
        if not rec:
            continue
        rec = dict(rec)
        if p.get("classification") == CLASS_BOUNCED_SUPPRESSED:
            rec["recommended_next_action"] = "No contactar: rebote / suprimido"
            rec["safety_note"] = "Correo suprimido por rebote o exclusión operacional."
        elif p.get("classification") == CLASS_MANUAL_OUTREACH_SENT:
            rec["recommended_next_action"] = "Esperar respuesta; no reenviar ahora"
            rec["safety_note"] = "Ya contactado en outreach manual reciente. No reenviar sin revisar."
        elif p.get("classification") == CLASS_SAME_DOMAIN_CONTACTED_REVIEW:
            rec["recommended_next_action"] = SAME_DOMAIN_EMPTY_EMAIL_ACTION
            rec["safety_note"] = (
                "No hay email en la fila, pero existe contacto previo con el mismo dominio."
            )
        out.append(rec)
    return out


def summarize_prospects_for_dashboard(prospects: list[dict[str, Any]]) -> dict[str, int]:
    """KPI counts after operational overlay."""
    total = len(prospects)
    blocked = sum(1 for p in prospects if p.get("is_blocked"))
    review = sum(1 for p in prospects if not p.get("is_blocked"))
    return {
        "total": total,
        "review_count": review,
        "blocked_count": blocked,
        "net_new_safe": sum(
            1 for p in prospects if p.get("classification") == "net_new_safe_review" and not p.get("is_blocked")
        ),
        "gmail_historico": sum(
            1
            for p in prospects
            if p.get("source_type") == "gmail_historico" and not p.get("is_blocked")
        ),
        "followup_antiguo": sum(
            1
            for p in prospects
            if p.get("source_type") == "followup_antiguo" and not p.get("is_blocked")
        ),
        "caso_activo": sum(1 for p in prospects if p.get("source_type") == "caso_activo"),
        "public_tender_review": sum(
            1
            for p in prospects
            if p.get("classification") == "public_tender_review" and not p.get("is_blocked")
        ),
        "same_domain_review": sum(
            1
            for p in prospects
            if p.get("classification") == "same_domain_contacted_review" and not p.get("is_blocked")
        ),
        "research_needed": sum(
            1
            for p in prospects
            if p.get("classification") == "research_only_contact_needed" and not p.get("is_blocked")
        ),
    }
