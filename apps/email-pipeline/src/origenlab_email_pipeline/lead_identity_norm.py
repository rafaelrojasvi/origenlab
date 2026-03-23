"""Normalized identity fields for lead_master (matching against mart and accounts).

Uses existing helpers: primary_sender_email / domain_of from business_mart;
normalize_domain / normalize_org_name from org_normalize.
"""

from __future__ import annotations

from origenlab_email_pipeline.business_mart import domain_of, primary_sender_email
from origenlab_email_pipeline.org_normalize import normalize_domain, normalize_org_name


def normalize_lead_email(raw: str | None) -> str:
    """Single best-effort contact email, lowercased, for equality matching to contact_master.email."""
    if not raw or not str(raw).strip():
        return ""
    s = str(raw).strip()
    pe = primary_sender_email(s)
    if pe:
        return pe.strip().lower()
    # Fallback: first token that looks like an email
    from origenlab_email_pipeline.business_mart import emails_in

    found = emails_in(s)
    return (found[0] if found else "").strip().lower()


def compute_lead_norm_fields(
    email: str | None,
    domain: str | None,
    org_name: str | None,
) -> dict[str, str | None]:
    """Return email_norm, domain_norm, org_name_norm for storage on lead_master."""
    email_norm = normalize_lead_email(email) or None
    domain_norm = normalize_domain(domain or "") or None
    if not domain_norm and email_norm and "@" in email_norm:
        domain_norm = domain_of(email_norm) or None
    org_name_norm = normalize_org_name(org_name or "") or None
    return {
        "email_norm": email_norm,
        "domain_norm": domain_norm,
        "org_name_norm": org_name_norm,
    }
