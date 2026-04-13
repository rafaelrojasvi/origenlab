"""Text and MIME helpers for client report generation (no CLI / HTML)."""

from __future__ import annotations

from email.header import decode_header


def decode_mime_header_value(s: str | None) -> str:
    """Decode MIME encoded-word (e.g. =?utf-8?B?...?=) in subject/header to readable str."""
    if not s or "=?" not in s:
        return (s or "").strip()
    try:
        parts = decode_header(s)
        out: list[str] = []
        for part, charset in parts:
            if isinstance(part, bytes):
                out.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(part or "")
        return "".join(out).strip()
    except Exception:
        return (s or "").strip()


def is_bounce_sender_for_report(sender: str) -> bool:
    """Heuristic: treat as bounce/NDR-style sender for domain report counters."""
    sl = (sender or "").lower()
    return (
        "mailer-daemon" in sl
        or "mail delivery subsystem" in sl
        or sl.startswith("postmaster@")
        or "postmaster@" in sl
    )
