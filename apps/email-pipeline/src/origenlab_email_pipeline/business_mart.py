"""Business mart derivations (Phase: client-facing business database).

Design goals:
- Keep raw archive tables untouched.
- Rebuildable materialized tables for client search and exploration.
- Conservative noise exclusion; document heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from collections import Counter, defaultdict
from typing import Iterable

from origenlab_email_pipeline.timeutil import now_iso

EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", re.I)


def emails_in(s: str) -> list[str]:
    return [e.lower() for e in EMAIL_RE.findall(s or "")]


def primary_sender_email(sender: str) -> str | None:
    es = emails_in(sender)
    return es[0] if es else None


def domain_of(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.split("@")[-1].lower()


def guess_org_name_from_domain(domain: str) -> str:
    d = (domain or "").lower().strip()
    if not d or d in ("(no address)",):
        return ""
    parts = d.split(".")
    if len(parts) >= 2:
        core = parts[-2]
    else:
        core = parts[0]
    core = re.sub(r"[^a-z0-9]+", " ", core).strip()
    return core.title()


def guess_org_type_from_domain(domain: str) -> str:
    d = (domain or "").lower()
    if any(x in d for x in (".edu", ".ac.", "universidad", "uchile", "puc", "utalca", "udec", "uach", "usach")):
        return "education"
    if any(x in d for x in (".gov", "gob.cl", ".mil")):
        return "government"
    if any(x in d for x in ("gmail.com", "hotmail.", "outlook.com", "yahoo.", "live.com")):
        return "consumer_email"
    return "business"


def is_noise_sender(sender: str, subject: str, body: str) -> bool:
    s = (sender or "").lower()
    subj = (subject or "").lower()
    blob = (subject or "").lower() + " " + (body or "").lower()
    return (
        "mailer-daemon" in s
        or "postmaster" in s
        or "delivery status" in subj
        or "undeliverable" in subj
        or "mail delivery failed" in subj
        or "returning message to sender" in blob
        or "notificación de estado de entrega" in blob
    )


_EQUIPMENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("microscopio", re.compile(r"\bmicroscop", re.I)),
    ("centrifuga", re.compile(r"\bcentrifug", re.I)),
    ("espectrofotometro", re.compile(r"espectrofotomet|spectrophotomet", re.I)),
    ("phmetro", re.compile(r"phmetro|\bph meter\b", re.I)),
    ("autoclave", re.compile(r"\bautoclave\b", re.I)),
    ("balanza", re.compile(r"\bbalanza\b|balance analit", re.I)),
    ("cromatografia_hplc", re.compile(r"cromatograf|\bhplc\b|gc-ms", re.I)),
    ("incubadora", re.compile(r"\bincubador\b|incubator", re.I)),
    ("titulador", re.compile(r"\btitulador\b|titrator", re.I)),
    ("liofilizador", re.compile(r"liofiliz|lyophil", re.I)),
    ("horno_mufla", re.compile(r"\bmufla\b|\bhorno\b", re.I)),
    ("pipetas", re.compile(r"\bpipet|\bpipeta", re.I)),
    ("osmometro", re.compile(r"osmometro|osm[oó]metr|osmo\s*met", re.I)),
    ("termobalanza", re.compile(r"termobalanza|termo\s*balanza|termogravimetr", re.I)),
    ("humedad_granos", re.compile(r"medidor de humedad|grain moisture", re.I)),
]


def equipment_tags_from_text(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for tag, pat in _EQUIPMENT_PATTERNS:
        if pat.search(text):
            out.append(tag)
    return out


def classify_email_intents(subject: str, text: str) -> dict[str, bool]:
    blob = (subject or "") + "\n" + (text or "")
    b = blob.lower()
    return {
        "is_quote_email": "cotiz" in b or "quotation" in b or "quote" in b or "presupuesto" in b,
        "is_invoice_email": "factura" in b or "invoice" in b,
        "is_purchase_email": "orden de compra" in b or "purchase order" in b or re.search(r"\boc\b", b) is not None or "pedido" in b,
    }


def clean_document_preview(raw: str, *, max_chars: int = 900) -> tuple[str, float]:
    """Produce a cleaner preview and a simple quality score (0–1).

    Goals:
    - collapse whitespace/newlines
    - reduce table-like junk (very long lines / repeated separators)
    - keep the first useful chunk
    """
    if not raw:
        return "", 0.0
    s = raw.replace("\x00", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s).strip()

    # Drop obvious CSV-like "sep=," marker and very repetitive separators.
    s = re.sub(r"(?im)^\s*sep\s*=\s*[,;|\t]\s*$", "", s).strip()
    s = re.sub(r"(?m)^[\-\=\_]{6,}\s*$", "", s).strip()

    # If lots of pipes/commas suggest a table dump, keep fewer lines.
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if not lines:
        return "", 0.0

    # Cap very long lines (xlsx/csv explosions).
    clipped = []
    for ln in lines[:60]:
        clipped.append(ln[:240])
    s2 = "\n".join(clipped).strip()

    # Final truncate
    s2 = s2[:max_chars].strip()

    # Quality score heuristic:
    # - prefer more letters than punctuation
    # - penalize extremely short previews
    letters = sum(ch.isalpha() for ch in s2)
    punct = sum((not ch.isalnum()) and (not ch.isspace()) for ch in s2)
    length = len(s2)
    if length == 0:
        return "", 0.0
    ratio = letters / max(1, letters + punct)
    len_score = min(1.0, length / 250.0)
    quality = max(0.0, min(1.0, 0.15 + 0.7 * ratio + 0.15 * len_score))
    return s2, quality


@dataclass
class DocAgg:
    business_doc_email_ids: set[int]
    doc_counts_by_email: dict[int, Counter]


def doc_aggregates(rows: Iterable[tuple]) -> DocAgg:
    """Input rows: (email_id, doc_type, has_quote, has_invoice, has_purchase, has_price_list)."""
    business_doc_email_ids: set[int] = set()
    doc_counts_by_email: dict[int, Counter] = defaultdict(Counter)
    for email_id, doc_type, hq, hi, hp, hpl in rows:
        if email_id is None:
            continue
        business_doc_email_ids.add(int(email_id))
        dt = (doc_type or "unknown").lower()
        # Treat "unknown" docs as business-doc only if any signal is set.
        if dt == "unknown" and not (hq or hi or hp or hpl):
            continue
        doc_counts_by_email[int(email_id)][dt] += 1
    return DocAgg(business_doc_email_ids, doc_counts_by_email)


def signal_row(
    *,
    signal_type: str,
    entity_kind: str,
    entity_key: str,
    email_id: int | None = None,
    attachment_id: int | None = None,
    score: float | None = None,
    details: dict | None = None,
) -> tuple:
    return (
        signal_type,
        entity_kind,
        entity_key,
        email_id,
        attachment_id,
        score,
        json.dumps(details or {}, ensure_ascii=False),
        now_iso(),
    )

