"""Extract failed recipient addresses from NDR / DSN mail and map to suppression codes."""

from __future__ import annotations

import re
from typing import Literal

from origenlab_email_pipeline.email_business_filters import EMAIL_RE

SuppressionBounceCode = Literal["bounce_no_such_user", "bounce_access_denied", "bounce_other"]

_FINAL_RCPT_RE = re.compile(
    r"Final-Recipient:\s*(?:RFC822|rfc822)\s*;\s*([^\s;<>]+)",
    re.I,
)
_ORIG_RCPT_RE = re.compile(
    r"Original-Recipient:\s*(?:RFC822|rfc822)\s*;\s*([^\s;<>]+)",
    re.I,
)
_X_FAILED_RE = re.compile(r"X-Failed-Recipients:\s*([^\n]+)", re.I)

# Lines that often introduce the bounced address in provider templates
_RECIPIENT_LINE_HINTS = (
    "could not be delivered",
    "couldn't be delivered",
    "unable to deliver",
    "delivery to the following recipient",
    "entrega fall",
    "no se pudo entregar",
    "no se entregó",
    "no se entrego",
    "no se ha podido entregar",
    "mensaje no pudo ser entregado",
    "wasn't delivered",
    "was not delivered",
    "se bloqueó tu mensaje",
    "se bloqueo tu mensaje",
    "usuario desconocido",
    "unknown user",
    "user unknown",
    "mailbox not found",
    "address not found",
    "no existe la casilla",
    "550 ",
    "551 ",
    "552 ",
    "553 ",
    "554 ",
    "5.1.1",
    "5.4.1",
)

_NO_SUCH_USER_HINTS = (
    "user unknown",
    "unknown user",
    "550 5.1.1",
    "551 5.1.1",
    "status: 5.1.1",
    "5.1.1",
    "mailbox unavailable",
    "mailbox not found",
    "no such user",
    "recipient address rejected",
    "does not exist",
    "doesn't exist",
    "address not found",
    "invalid recipient",
    "usuario inexistente",
    "usuario desconocido",
    "destinatario desconocido",
    "no existe la casilla",
    "casilla inexistente",
    "no existe",
    "direccion inexistente",
    "no hay ningun buzon",
    "no hay ningún buzón",
)

_ACCESS_DENIED_HINTS = (
    "access denied",
    "rejected your message to",
    "message blocked",
    "policy violation",
    "relay access denied",
    "not allowed to relay",
    "550 5.7.1",
    "554 5.7.1",
    "571",
    "spam",
    "message rejected",
)

_SYSTEM_OR_INTERNAL_SUBSTRINGS = (
    "mailer-daemon",
    "postmaster@",
    "mail-daemon",
    "noreply",
    "no-reply",
    "double-bounce",
)

_SYSTEM_EMAIL_PREFIXES = ("mailer-daemon@", "postmaster@", "double-bounce@")

# Stop parsing before quoted / forwarded original (avoid BCC lists in campaign body).
_QUOTED_ORIGINAL_BOUNDARY_RE = re.compile(
    r"(?im)"
    r"(?:^-{3,}\s*original message\b"
    r"|^-{3,}\s*mensaje original\b"
    r"|^={3,}\s*forwarded message\b"
    r"|^\s*original message\s*$"
    r"|^\s*mensaje reenviado\s*$)",
)

# Gmail web/UI DSN templates: one capture group = failed mailbox (DSN narrative only).
_GMAIL_FAILURE_TEMPLATE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"tu mensaje no se entreg[oó]\s+a\s+<?([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})>?",
        re.I,
    ),
    re.compile(
        r"your message (?:wasn't|was not|couldn't|could not be) delivered to\s+"
        r"<?([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})>?",
        re.I,
    ),
    re.compile(
        r"se bloque[oó]\s+tu mensaje para\s+<?([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})>?",
        re.I,
    ),
    re.compile(
        r"your message (?:was )?blocked (?:for|to)\s+<?([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})>?",
        re.I,
    ),
)


def _dsn_narrative_portion(text: str) -> str:
    """Return NDR narrative only; exclude quoted original message bodies."""
    m = _QUOTED_ORIGINAL_BOUNDARY_RE.search(text)
    if m:
        return text[: m.start()]
    return text


def _extract_gmail_template_recipients(dsn_text: str) -> list[str]:
    ordered: list[str] = []
    for pat in _GMAIL_FAILURE_TEMPLATE_RES:
        for m in pat.finditer(dsn_text):
            e = _norm_email(m.group(1))
            if e and _is_plausible_failed_rcpt(e):
                ordered.append(e)
    return ordered


def _norm_email(addr: str) -> str | None:
    s = (addr or "").strip().strip("<>").strip().lower()
    if not s or "@" not in s:
        return None
    found = EMAIL_RE.findall(s)
    if not found:
        return None
    e = found[0].lower()
    low = e.lower()
    if any(low.startswith(p) for p in _SYSTEM_EMAIL_PREFIXES):
        return None
    if any(x in low for x in _SYSTEM_OR_INTERNAL_SUBSTRINGS):
        return None
    return e


def _is_plausible_failed_rcpt(email: str) -> bool:
    low = email.lower()
    if low.endswith("origenlab.cl") or low.endswith("labdelivery.cl"):
        return False
    # Google encodes some internal bounce paths as @mail.gmail.com (not a real mailbox).
    if low.endswith("@mail.gmail.com"):
        return False
    return True


def bounce_suppression_code_from_ndr_text(text: str | None) -> SuppressionBounceCode:
    """Classify NDR body into bounce_* suppression reason (heuristic)."""
    blob = (text or "").lower()
    if any(h in blob for h in _NO_SUCH_USER_HINTS):
        return "bounce_no_such_user"
    if any(h in blob for h in _ACCESS_DENIED_HINTS):
        return "bounce_access_denied"
    return "bounce_other"


def extract_failed_recipients_from_ndr(text: str | None) -> list[str]:
    """Return likely failed RCPT addresses (lowercased), best-effort from DSN + templates."""
    if not text:
        return []
    raw = text if len(text) <= 500_000 else text[:500_000]
    dsn = _dsn_narrative_portion(raw)
    ordered: list[str] = []

    for m in _FINAL_RCPT_RE.finditer(dsn):
        e = _norm_email(m.group(1))
        if e and _is_plausible_failed_rcpt(e):
            ordered.append(e)

    for m in _X_FAILED_RE.finditer(dsn):
        for part in re.split(r"[\s,;]+", m.group(1)):
            e = _norm_email(part)
            if e and _is_plausible_failed_rcpt(e):
                ordered.append(e)

    for m in _ORIG_RCPT_RE.finditer(dsn):
        e = _norm_email(m.group(1))
        if e and _is_plausible_failed_rcpt(e):
            ordered.append(e)

    # Gmail UI templates only when standard DSN headers did not name the failed RCPT.
    if not ordered:
        ordered.extend(_extract_gmail_template_recipients(dsn))

    if not ordered:
        for line in dsn.splitlines():
            low_line = line.lower()
            if not any(h in low_line for h in _RECIPIENT_LINE_HINTS):
                continue
            for addr in EMAIL_RE.findall(line):
                e = _norm_email(addr)
                if e and _is_plausible_failed_rcpt(e):
                    ordered.append(e)
                    break

    seen: set[str] = set()
    out: list[str] = []
    for e in ordered:
        if e in seen:
            continue
        seen.add(e)
        out.append(e)
    return out
