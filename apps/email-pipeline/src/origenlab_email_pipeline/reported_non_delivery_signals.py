"""Heuristics: recipient text suggests they never got our outreach (inactive / mailbox issue).

Used against **inbound** ``emails`` rows (external ``sender``) on the contacto Gmail ingest.
Conservative patterns only — prefer false negatives over mass false positives.
"""

from __future__ import annotations

import re

# Strong phrasing only (avoids "no recibí respuesta", many third-person footers like "si no recibió…", etc.).
_NON_DELIVERY_STRONG: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"no\s+me\s+lleg[oáaó]\s+(el|la|tu|su|este|esta|unos?|unas?)\s+(correo|mail|e-?mail|mensaje)\b",
        re.I,
    ),
    re.compile(r"no\s+(me\s+)?lleg[oáaó]\s+tu\s+(correo|mail|e-?mail|mensaje)\b", re.I),
    re.compile(
        r"nunca\s+recib(i|í|imos)?\s+(tu|el|la|su|este|esta)\s+(correo|mail|e-?mail|mensaje)\b",
        re.I,
    ),
    re.compile(
        r"no\s+recib(i|í|imos)?\s+(tu|el|la|su|este|esta)\s+(correo|mail|e-?mail|mensaje)\b",
        re.I,
    ),
    re.compile(r"did\s+not\s+receive\s+(your|the)\s+(e-?mail|message|mail)\b", re.I),
    re.compile(r"never\s+received\s+(your|the)\s+(e-?mail|message|mail)\b", re.I),
    re.compile(r"never\s+got\s+your\s+(e-?mail|email|message)\b", re.I),
    re.compile(r"haven'?t\s+received\s+(your|the)\s+(e-?mail|message|mail)\b", re.I),
)


def text_suggests_reported_non_delivery(subject: str | None, body: str | None, *, max_body_chars: int = 12000) -> bool:
    subj = (subject or "").strip()
    body_s = (body or "").strip()
    if max_body_chars > 0 and len(body_s) > max_body_chars:
        body_s = body_s[:max_body_chars]
    blob = f"{subj}\n{body_s}".strip()
    if not blob:
        return False
    return any(p.search(blob) for p in _NON_DELIVERY_STRONG)
