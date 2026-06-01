"""Map NDR / operator notes to dashboard failure_type labels."""

from __future__ import annotations

from origenlab_email_pipeline.campaigns.manual_outreach_2026_06_01 import FailureType
from origenlab_email_pipeline.ndr_bounce_extraction import bounce_suppression_code_from_ndr_text

_DOMAIN_NOT_FOUND_HINTS = (
    "domain not found",
    "dominio no encontrado",
    "dns error",
    "nxdomain",
    "host not found",
    "no such host",
    "name or service not known",
    "mrlab.cl",
    "aramalab.cl",
    "cosmeticanacional.cl",
)

_GROUP_PERMISSION_HINTS = (
    "group",
    "google group",
    "permission",
    "not allowed to post",
    "no tiene permiso",
    "sin permiso",
    "publish",
    "publicar",
)

_MISCONFIGURED_HINTS = (
    "misconfigured",
    "mal configurado",
    "configuration error",
    "remote server",
    "servidor remoto",
)


def classify_failure_type(ndr_text: str | None, *, operator_hint: str = "") -> FailureType:
    blob = f"{ndr_text or ''} {operator_hint or ''}".lower()
    if any(h in blob for h in _GROUP_PERMISSION_HINTS):
        return "group_or_permission"
    if any(h in blob for h in _DOMAIN_NOT_FOUND_HINTS):
        return "domain_not_found"
    if any(h in blob for h in _MISCONFIGURED_HINTS):
        return "remote_server_misconfigured"
    code = bounce_suppression_code_from_ndr_text(blob)
    if code == "bounce_no_such_user":
        return "no_such_user"
    return "unknown"
