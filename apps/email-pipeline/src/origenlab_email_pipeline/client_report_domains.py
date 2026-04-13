"""Domain helpers for client report aggregates.

Uses canonical :func:`origenlab_email_pipeline.business_mart.emails_in` so report
generation does not duplicate mailbox regex logic.
"""

from __future__ import annotations

from origenlab_email_pipeline.business_mart import emails_in


def primary_domain(sender: str) -> str:
    addrs = emails_in(sender or "")
    if not addrs:
        return "(no address)"
    return addrs[0].split("@")[-1].lower()


def recip_domains(recipients: str) -> list[str]:
    out: list[str] = []
    for a in emails_in(recipients or ""):
        out.append(a.split("@")[-1].lower())
    return out
