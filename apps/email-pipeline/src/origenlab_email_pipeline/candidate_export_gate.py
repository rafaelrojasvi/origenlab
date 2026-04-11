"""Shared pre-export eligibility for cold outreach (lead path + contact_master path).

Single policy implementation: Streamlit and CLIs must not duplicate these rules.
Phase 1: no new tables; reuses suppression, Sent parse, outreach state, supplier_master, noise heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.marketing_contact_noise import (
    marketing_outreach_noise_email,
    marketing_outreach_noise_organization_guess,
)
from origenlab_email_pipeline.marketing_supplier_domains import is_supplier_email_domain

# Stable reason codes (CSV, logs, tests).
REASON_INVALID_EMAIL = "invalid_email"
REASON_INTERNAL_DOMAIN = "internal_domain"
REASON_SUPPRESSION = "suppression"
REASON_SENT_HISTORY = "sent_history"
REASON_OUTREACH_CONTACTED = "outreach_contacted"
REASON_OUTREACH_REPLIED = "outreach_replied"
REASON_OUTREACH_SNOOZED = "outreach_snoozed"
REASON_SUPPLIER_DOMAIN = "supplier_domain"
REASON_NOISE_EMAIL = "noise_email"
REASON_NOISE_ORGANIZATION = "noise_organization"

_OUTREACH_REASON = {
    "contacted": REASON_OUTREACH_CONTACTED,
    "replied": REASON_OUTREACH_REPLIED,
    "snoozed": REASON_OUTREACH_SNOOZED,
}


@dataclass(frozen=True)
class GateContext:
    """Inputs for eligibility. Build once per export run."""

    sent_recipient_norms: frozenset[str]
    suppressed_norms: frozenset[str]
    outreach_state_by_email: dict[str, str]
    supplier_domains: frozenset[str]
    blocked_domains: frozenset[str]
    skip_noise_filter: bool = False
    skip_supplier_domain_filter: bool = False


@dataclass(frozen=True)
class ExportGateResult:
    eligible: bool
    """If not eligible, a single-element tuple with the first triggered rule (evaluation order fixed)."""

    reasons: tuple[str, ...]


def normalize_export_email(contact_email: str) -> str | None:
    """Match ``norm_lead_email`` / contact_master export: first mailbox in string."""
    raw = (contact_email or "").strip()
    if not raw:
        return None
    found = emails_in(raw)
    if not found:
        return None
    return found[0]


def evaluate_export_eligibility(
    *,
    contact_email: str,
    institution_name: str | None,
    ctx: GateContext,
) -> ExportGateResult:
    em = normalize_export_email(contact_email)
    if not em:
        return ExportGateResult(eligible=False, reasons=(REASON_INVALID_EMAIL,))

    if "@" not in em:
        return ExportGateResult(eligible=False, reasons=(REASON_INVALID_EMAIL,))

    dom = em.rsplit("@", 1)[-1].lower()
    if dom in ctx.blocked_domains:
        return ExportGateResult(eligible=False, reasons=(REASON_INTERNAL_DOMAIN,))

    if em in ctx.suppressed_norms:
        return ExportGateResult(eligible=False, reasons=(REASON_SUPPRESSION,))

    if em in ctx.sent_recipient_norms:
        return ExportGateResult(eligible=False, reasons=(REASON_SENT_HISTORY,))

    st = (ctx.outreach_state_by_email or {}).get(em)
    if st:
        reason = _OUTREACH_REASON.get(st)
        if reason:
            return ExportGateResult(eligible=False, reasons=(reason,))

    if not ctx.skip_supplier_domain_filter and ctx.supplier_domains:
        if is_supplier_email_domain(em, ctx.supplier_domains):
            return ExportGateResult(eligible=False, reasons=(REASON_SUPPLIER_DOMAIN,))

    if not ctx.skip_noise_filter:
        if marketing_outreach_noise_email(em):
            return ExportGateResult(eligible=False, reasons=(REASON_NOISE_EMAIL,))
        if marketing_outreach_noise_organization_guess(institution_name or ""):
            return ExportGateResult(eligible=False, reasons=(REASON_NOISE_ORGANIZATION,))

    return ExportGateResult(eligible=True, reasons=())
