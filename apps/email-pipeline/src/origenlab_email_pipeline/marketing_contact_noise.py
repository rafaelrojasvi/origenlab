"""Heuristics to skip obvious non-prospect rows when building cold-outreach lists.

``contact_master`` reflects the email archive: it legitimately contains
transactional / platform / carrier addresses. Do not delete those rows from the
mart; filter them when exporting marketing batches.
"""

from __future__ import annotations

# Domains that are almost never a human commercial buyer for lab outreach.
_NOISE_DOMAINS: frozenset[str] = frozenset(
    {
        "mercadopublico.cl",
        "chilecompra.cl",
        "dhl.com",
        "wherex.com",
        "facebookmail.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "google.com",
        "microsoft.com",
        "mailchimp.com",
        "sendgrid.net",
        "mandrillapp.com",
        "mailgun.org",
        "amazonses.com",
        "postmarkapp.com",
        # Newsletter / marketing automation senders (when the From is on these domains).
        "substack.com",
        "substack.email",
        "beehiiv.com",
        "convertkit.com",
        "klaviyo.com",
        "e.klaviyo.com",
        "customeriomail.com",
        "hubspotemail.net",
        "rsgsv.net",
        "createsend.com",
        "campaign-archive.com",
        "list-manage.com",
    }
)

# If local-part looks like an automated mailbox, skip (unless you later narrow the list).
_NOISE_LOCAL_PREFIXES: tuple[str, ...] = (
    "noreply",
    "no-reply",
    "donotreply",
    "do_not_reply",
    "mailer-daemon",
    "postmaster",
    "bounce",
    "bounces",
    "notificacion",
    "notificaciones",
    "notification",
    "notifications",
    "avisos",
    "alerts",
    "invitations",
    "invite",
    "system",
    "newsletter",
    "unsub",
    "unsubscribe",
    "mailing",
    "digest",
    "promo",
    "promos",
    "campaign",
)


def marketing_outreach_noise_email(email: str) -> bool:
    """True if ``email`` should be excluded from cold marketing exports."""
    raw = (email or "").strip().lower()
    if not raw or "@" not in raw:
        return True
    local, _, domain = raw.partition("@")
    local = local.strip()
    domain = domain.strip().lower()
    if not local or not domain:
        return True
    if domain in _NOISE_DOMAINS:
        return True
    for d in _NOISE_DOMAINS:
        if domain.endswith("." + d) or domain == d:
            return True
    for p in _NOISE_LOCAL_PREFIXES:
        if local == p or local.startswith(p + ".") or local.startswith(p + "+"):
            return True
    return False


def marketing_outreach_noise_organization_guess(name: str | None) -> bool:
    """True if organization_name_guess clearly matches a known noise source."""
    n = (name or "").strip().lower()
    if not n:
        return False
    noise_names = (
        "mercadopublico",
        "mercado publico",
        "dhl",
        "wherex",
        "facebookmail",
        "twitter",
        "linkedin",
    )
    return any(x in n for x in noise_names)
