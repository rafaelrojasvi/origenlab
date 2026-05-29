"""Stable warm-case grouping keys (read-only; API dedup + Postgres promotion)."""

from __future__ import annotations

import re

from origenlab_email_pipeline.warm_case_sender_rules import (
    email_domain,
    is_supplier_vendor_domain,
)

_RE_PREFIX = re.compile(r"^(?:(?:re|fw|fwd|rv|res)\s*:\s*)+", re.I)


def normalize_subject_group_token(subject: str) -> str:
    """Subject stem for supplier-thread grouping (no bodies)."""
    sub = (subject or "").strip().lower()
    while True:
        stripped = _RE_PREFIX.sub("", sub, count=1).strip()
        if stripped == sub:
            break
        sub = stripped
    sub = re.sub(r"\s+", " ", sub).strip()
    return sub[:160]


def thread_case_hint(subject: str, contact_email: str = "") -> str | None:
    sub = (subject or "").lower()
    email = (contact_email or "").strip().lower()
    domain = email_domain(email)

    if ("rv10.70" in sub or "3812200" in sub) and "rg energia" in sub:
        return "rg-energia-ika-rv10.70-3812200"

    if domain == "crtopmachine.com" or "crtop" in sub:
        if (
            "reactor" in sub
            or "olt-hp" in sub
            or "olt hp" in sub
            or "inquiry about our reactor" in sub
        ):
            return "crtop-reactor-olt-hp-5l"

    if (
        "unach" in sub
        or "universidad adventista" in sub
        or domain.endswith("unach.cl")
    ) and ("hielscher" in sub or "uip2000" in sub or "ultrason" in sub):
        return "unach-hielscher-uip2000-extraction"

    if "ongo" in sub or domain == "ongo.cl":
        if "up400st" in sub or "sonicador" in sub:
            return "ongo-hielscher-up400st-quote"

    return None


def warm_case_group_key(contact_email: str, subject: str) -> str:
    """One dashboard row per group key; duplicates expose grouped_email_count."""
    email = (contact_email or "").strip().lower()
    hint = thread_case_hint(subject, email)
    if hint:
        return f"thread:{hint}"

    domain = email_domain(email)
    if is_supplier_vendor_domain(domain):
        token = normalize_subject_group_token(subject)
        return f"supplier:{email}|{token}"

    return f"email:{email}|{domain}"
