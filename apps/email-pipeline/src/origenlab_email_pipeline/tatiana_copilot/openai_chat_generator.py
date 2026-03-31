from __future__ import annotations

import json
import re
import unicodedata
from email.header import decode_header, make_header
from typing import Any

from origenlab_email_pipeline.config import Settings

from .generator import DraftGenerator, DraftResult
from .marketing_outreach import MARKETING_VARIANT_FOLLOWUP
from .origenlab_context import DRAFTING_PROFILE_ORIGENLAB, DRAFTING_PROFILE_TATIANA_HISTORICAL


class TatianaLLMConfigurationError(RuntimeError):
    """Raised when LLM-backed generation is requested but required configuration is missing."""


# Single canonical closing block (avoids duplicate / inconsistent signature lines in drafts).
_CANONICAL_SIGNATURE = (
    "Saludos cordiales,\n\n"
    "Tatiana Vivanco\n"
    "OrigenLab | Equipos para laboratorio\n"
    "Valdivia, Chile\n"
    "contacto@origenlab.cl | +56 9 6256 7816\n"
    "www.origenlab.cl"
)

_SPANISH_BOILERPLATE = frozenset(
    {
        "estimada",
        "estimado",
        "estimados",
        "gracias",
        "contactarnos",
        "saludar",
        "saludarle",
        "junto",
        "buenas",
        "tardes",
        "dias",
        "días",
        "por",
        "para",
        "favor",
        "cordiales",
        "saludos",
        "atenta",
        "atento",
        "quedo",
        "cualquier",
        "consulta",
        "adjunto",
        "adjunta",
        "le",
        "les",
        "con",
        "una",
        "las",
        "los",
        "del",
    }
)

# Subject line: avoid essay-like client subjects.
_MAX_ASUNTO_CHARS = 95

_PLACEHOLDER_MODEL_LINE = re.compile(
    r"^\s*[-•*]?\s*Modelo\s*[123]\s*(?:[.,])?\s*$",
    re.I | re.MULTILINE,
)

_COTIZACIÓN_REF = re.compile(r"N[°º]?\s*[\d][\d\-]{2,}", re.I)

# Comparative / hype patterns — allowed only if present in case text (not from retrieval).
_COMPARATIVE_MARKERS = re.compile(
    r"(?:"
    r"\d+\s*%|%\s*más|\b%\b|"
    r"m[aá]s\s+r[aá]pido|m[aá]s\s+eficiente|"
    r"mayor\s+precisi|mayor\s+sensibil|menor\s+tiempo|"
    r"doble\s+de\s+r[aá]pido|mucho\s+m[aá]s"
    r")",
    re.I,
)

_PLAZO_ENTREGA_PHRASE = re.compile(
    r"(?is)"
    r"(?:plazo\s+de\s+entrega|entrega\s+|plazo\s+(?:es\s+)?de\s+)"
    r"[^.\n]*?"
    r"\b(\d{1,2})\s*(?:a\s*(\d{1,2})\s*)?(d[ií]as?|semanas?)\b",
)

_HARD_INSTALL = re.compile(
    r"(?i)(?:incluye|inclu|con)\s+.{0,40}?(?:puesta\s+en\s+marcha|instalaci[oó]n(?:\s+|$|,))",
)
_LOOSE_INSTALL = re.compile(r"(?i)puesta\s+en\s+marcha|instalaci[oó]n\s+y\b")

_CIF_TERM = re.compile(r"\bCIF\b", re.I)

_MONTO_MÍNIMO = re.compile(
    r"(?i)monto\s+m[ií]nimo|m[ií]nimo\s+de\s+facturaci[oó]n|[\$]\s*[\d.]+",
)
_PLACEHOLDER_TOKEN_RE = re.compile(
    r"(\[[^\]\n]{1,80}\]|<[^>\n]{1,80}>|\{\{[^}\n]{1,80}\}\})",
    re.I,
)
_SUPPORT_REPLY_PHRASES_RE = re.compile(
    r"(?i)(gracias\s+por\s+contactarnos|le\s+confirmamos\s+recepci[oó]n|en\s+respuesta\s+a\s+su\s+solicitud)"
)


def _norm_match_text(s: str) -> str:
    t = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn")


def _case_contains(haystack_raw: str, needle_raw: str) -> bool:
    if not needle_raw.strip():
        return True
    return _norm_match_text(needle_raw) in _norm_match_text(haystack_raw)


def _iter_sentences(block: str) -> list[str]:
    """Split on Spanish sentence ends; keep short fragments as single units."""
    block = (block or "").strip()
    if not block:
        return []
    parts = re.split(r"(?<=[.!?])\s+", block)
    cleaned = [p.strip() for p in parts if p.strip()]
    return cleaned if cleaned else [block]


def _is_placeholder_model_line(line: str) -> bool:
    return bool(_PLACEHOLDER_MODEL_LINE.match(line.strip()))


def remove_placeholder_model_bullets(body: str) -> str:
    lines = body.splitlines()
    out: list[str] = []
    removed = False
    for line in lines:
        if _is_placeholder_model_line(line):
            removed = True
            continue
        out.append(line)
    text = "\n".join(out)
    if removed:
        text = re.sub(r"\n{3,}", "\n\n", text.strip())
        if not re.search(r"(?i)adjunto|cotizaci", text):
            text = text.rstrip() + "\n\nAdjunto las alternativas en la documentación enviada."
    return text


def _quote_refs_in(text: str) -> list[str]:
    return [m.group(0) for m in _COTIZACIÓN_REF.finditer(text)]


def _sentence_has_risky_comparative(sentence: str) -> bool:
    return bool(_COMPARATIVE_MARKERS.search(sentence))


def _is_stock_comparative_pitch_sentence(sentence: str) -> bool:
    """Halógeno vs infrarrojo speed/sensitivity line reused across outbounds (brochure-style)."""
    n = _norm_match_text(sentence)
    if "mas rapido" not in n or "infrarrojo" not in n:
        return False
    if "halogeno" in n:
        return True
    if "mayor sensibil" in n:
        return True
    return False


def _case_supports_comparative_pitch(case_text: str) -> bool:
    """Brochure comparatives need corroboration or an explicit buyer question — not prior seller copy."""
    raw = case_text or ""
    n = _norm_match_text(raw)
    if any(
        cue in n
        for cue in (
            "segun ficha",
            "ficha tecnic",
            "segun fabricante",
            "segun el fabricante",
            "datos del fabricante",
            "especificaciones del fabricante",
            "tabla comparativa",
            "comparativa de equipos",
            "informe comparativo",
        )
    ):
        return True
    if re.search(
        r"(?i)(?:cu[aá]l\s+es\s+m[aá]s\s+r[aá]pido|"
        r"diferencia(?:s)?\s+(?:entre\s+)?(?:el\s+)?(?:hal[oó]geno|infrarrojo|infrarroja)|"
        r"(?:hal[oó]geno|hal[oó]gena)\s+vs\.?\s*(?:el\s+)?infrarrojo|"
        r"infrarrojo\s+vs\.?\s*(?:el\s+)?hal[oó]geno|"
        r"m[aá]s\s+r[aá]pido\s+(?:que|vs)|"
        r"comparar\s+(?:hal[oó]geno|infrarrojo)|"
        r"que\s+ventaja\s+tiene\s+el\s+hal[oó]geno)",
        raw,
    ):
        return True
    return False


def _comparative_sentence_allowed(sentence: str, case_text: str) -> bool:
    if _is_stock_comparative_pitch_sentence(sentence) and _case_supports_comparative_pitch(
        case_text
    ):
        return True
    n = _norm_match_text(case_text)
    s_norm = _norm_match_text(sentence)
    if "%" in sentence and "%" not in case_text:
        return False
    phrases = (
        "mas rapido",
        "mas eficiente",
        "mayor precision",
        "mayor sensibil",
        "menor tiempo",
    )
    for ph in phrases:
        if ph in s_norm and ph not in n:
            return False
    return True


def _sentence_has_quote_ref(sentence: str) -> bool:
    return bool(_COTIZACIÓN_REF.search(sentence))


def _quote_sentence_allowed(sentence: str, case_text: str) -> bool:
    case_digits = re.sub(r"[^\d\-]", "", case_text)
    for ref in _quote_refs_in(sentence):
        digits = re.sub(r"[^\d\-]", "", ref)
        if len(digits) >= 4 and digits not in case_digits:
            return False
    return True


def _sentence_has_strong_install(sentence: str) -> bool:
    return bool(_HARD_INSTALL.search(sentence) or _LOOSE_INSTALL.search(sentence))


def _case_supports_install_commitment(case_text: str) -> bool:
    """True only when case text positively mentions install/commissioning — not 'sin instalación'."""
    raw = case_text or ""
    n = _norm_match_text(raw)
    if re.search(
        r"(?i)sin\s+(?:mencionar\s+)?(?:la\s+)?instalaci[oó]n",
        raw,
    ) or re.search(r"(?i)sin\s+puesta\s+en\s+marcha", raw):
        return False
    if re.search(r"(?i)sin\s+instalaci[oó]n\b", raw):
        return False
    if re.search(r"(?i)no\s+incluye\s+(?:la\s+)?instalaci[oó]n", raw):
        return False
    if "puesta en marcha" in n:
        return True
    if "instalacion" in n:
        return True
    return False


def _install_sentence_allowed(sentence: str, case_text: str) -> bool:
    if not _sentence_has_strong_install(sentence):
        return True
    return _case_supports_install_commitment(case_text)


def _sentence_has_cif(sentence: str) -> bool:
    return bool(_CIF_TERM.search(sentence))


def _sentence_has_plazo_numbers(sentence: str) -> bool:
    return bool(_PLAZO_ENTREGA_PHRASE.search(sentence))


def _plazo_sentence_allowed(sentence: str, case_text: str) -> bool:
    m = _PLAZO_ENTREGA_PHRASE.search(sentence)
    if not m:
        return True
    span = m.group(0)
    if _case_contains(case_text, span):
        return True
    n1, n2, unit = m.group(1), m.group(2), m.group(3)
    ct = _norm_match_text(case_text)
    if n1 not in ct:
        return False
    if n2 and n2 not in ct:
        return False
    if _norm_match_text(unit) not in ct:
        # unit word might be abbreviated in case
        return "dia" in ct or "seman" in ct
    return True


def _sentence_has_policy_money(sentence: str) -> bool:
    return bool(_MONTO_MÍNIMO.search(sentence))


def _policy_money_allowed(sentence: str, case_text: str) -> bool:
    if not _sentence_has_policy_money(sentence):
        return True
    if re.search(r"[\$]\s*[\d.]+", sentence):
        amt = re.search(r"[\$]\s*([\d.]+)", sentence)
        if amt and amt.group(1) not in case_text.replace(".", "").replace(",", ""):
            g = amt.group(1).replace(".", "")
            if g and g not in re.sub(r"\D", "", case_text):
                return False
    if re.search(r"(?i)m[ií]nimo\s+de\s+facturaci", sentence):
        return _norm_match_text("facturaci") in _norm_match_text(case_text) or _norm_match_text(
            "monto minimo"
        ) in _norm_match_text(case_text)
    return True


def _sentence_allowed(sentence: str, case_text: str) -> bool:
    if _is_placeholder_model_line(sentence):
        return False
    if _is_stock_comparative_pitch_sentence(sentence) and not _case_supports_comparative_pitch(
        case_text
    ):
        return False
    if _sentence_has_risky_comparative(sentence) and not _comparative_sentence_allowed(
        sentence, case_text
    ):
        return False
    if _sentence_has_quote_ref(sentence) and not _quote_sentence_allowed(
        sentence, case_text
    ):
        return False
    if not _install_sentence_allowed(sentence, case_text):
        return False
    if _sentence_has_cif(sentence) and "cif" not in _norm_match_text(case_text):
        return False
    if _sentence_has_plazo_numbers(sentence) and not _plazo_sentence_allowed(
        sentence, case_text
    ):
        return False
    if _sentence_has_policy_money(sentence) and not _policy_money_allowed(
        sentence, case_text
    ):
        return False
    return True


def filter_ungrounded_sentences(paragraph: str, case_text: str) -> str:
    """Remove sentences that introduce risky claims without case support."""
    if not paragraph.strip():
        return paragraph
    new_lines: list[str] = []
    for raw_line in paragraph.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            new_lines.append(raw_line)
            continue
        m = re.match(r"^(\s*[-•*]\s*)(.+)$", line)
        if m:
            prefix, content = m.group(1), m.group(2)
            if _is_placeholder_model_line(stripped):
                continue
            sents = _iter_sentences(content)
            kept = [s for s in sents if _sentence_allowed(s, case_text)]
            if not kept and sents:
                continue
            if not sents:
                if _sentence_allowed(content, case_text):
                    new_lines.append(line)
                continue
            new_lines.append(prefix + " ".join(kept))
            continue
        sents = _iter_sentences(stripped)
        kept = [s for s in sents if _sentence_allowed(s, case_text)]
        if kept:
            new_lines.append(" ".join(kept))
    return "\n".join(new_lines)


def sanitize_body_grounding(body: str, case_text: str) -> str:
    body = remove_placeholder_model_bullets(body)
    paras = re.split(r"\n\n+", body.strip())
    out_paras: list[str] = []
    for p in paras:
        if not p.strip():
            continue
        cleaned = filter_ungrounded_sentences(p, case_text)
        if cleaned.strip():
            out_paras.append(cleaned.strip())
    return "\n\n".join(out_paras)


def harden_asunto_line(draft: str, *, max_chars: int = _MAX_ASUNTO_CHARS) -> str:
    lines = draft.splitlines()
    if not lines or not re.match(r"^asunto:\s*", lines[0], re.I):
        return draft
    prefix = re.match(r"^(asunto:\s*)", lines[0], re.I).group(1)
    rest = lines[0][len(prefix) :].strip()
    if len(rest) > max_chars:
        cut = rest[: max_chars - 3].rsplit(" ", 1)[0]
        rest = (cut or rest[:max_chars]) + "..."
    lines[0] = prefix + rest
    return "\n".join(lines)


def grounding_sanitize_below_asunto(text_after_asunto: str, case_text: str) -> str:
    """Apply grounding cleaners only to the letter body (leave signature block untouched)."""
    low = text_after_asunto.lower()
    sig = "saludos cordiales"
    idx = low.find(sig)
    if idx >= 0:
        main, tail = text_after_asunto[:idx].rstrip(), text_after_asunto[idx:].lstrip()
        main2 = sanitize_body_grounding(main, case_text)
        if not main2.strip():
            main2 = "Gracias por contactarnos."
        return f"{main2}\n\n{tail}".strip()
    return sanitize_body_grounding(text_after_asunto, case_text)


def decode_mime_subject(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return value


def extract_recipient_name_hint(body_text: str) -> str | None:
    m = re.search(r"^Estimad[ao]\s+([^,\n:]+)", body_text.strip(), re.M | re.I)
    if not m:
        return None
    name = m.group(1).strip().rstrip(",")
    if not name or name.lower() in {"a", "(a)", "cliente", "clientes", "señor", "señora"}:
        return None
    return name


def cotización_pointer_is_email_only(body_text: str) -> bool:
    """
    Detects corrupted threads where 'cotización' points at a bare mailbox line (no product detail).
    Targets eval_009-style bodies.
    """
    b = body_text.strip()
    if re.search(
        r"adjunto\s+(?:la\s+)?cotización\s+por\s*\n\s*[a-z0-9._%+-]+@",
        b,
        re.I | re.MULTILINE,
    ):
        return True
    if re.search(
        r"adjunto\s+(?:la\s+)?cotización\s+por\s+[a-z0-9._%+-]+@",
        b,
        re.I,
    ):
        return True
    if re.search(
        r"cotización\s+por\s*\n\s*[a-z0-9._%+-]+@",
        b,
        re.I | re.MULTILINE,
    ):
        return True
    return False


def _strip_urls_and_emails(text: str) -> str:
    t = re.sub(r"https?://\S+", " ", text)
    t = re.sub(r"\S+@\S+", " ", t)
    return t


def substantive_token_count(body_text: str) -> int:
    t = _strip_urls_and_emails(body_text)
    words = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]{4,}", t)
    return sum(1 for w in words if w.lower() not in _SPANISH_BOILERPLATE)


def has_product_or_model_signals(body_text: str) -> bool:
    if re.search(r"\b(ST\d{3,5}|DS\d{4,5}|SG[-\s]?[Uu]ltra)\b", body_text):
        return True
    if re.search(r"\bmodelo\s+[A-Za-z0-9][A-Za-z0-9\-]{2,}\b", body_text, re.I):
        return True
    if re.search(
        r"\b(medidor|dens[ií]metro|refract[oó]metro|termobalanza|balanza)\b",
        body_text,
        re.I,
    ):
        return True
    if re.search(r"\b(Ohaus|Krüss|Kruss|Eagle\s+Eye)\b", body_text, re.I):
        return True
    return False


def should_abstain_low_information_case(body_text: str) -> bool:
    if cotización_pointer_is_email_only(body_text):
        return True
    if has_product_or_model_signals(body_text):
        return False
    if not re.search(
        r"\b(adjunto|adjunta|cotizaci[oó]n|cotización)\b", body_text, re.I
    ):
        return False
    return substantive_token_count(body_text) < 14


def _asunto_subject_part_generic(subject_part: str) -> bool:
    s = subject_part.strip()
    s_low = s.lower()
    while s_low.startswith("re:"):
        s = s[3:].strip()
        s_low = s.lower()
    if len(s) <= 3:
        return True
    if s_low in {"cotización", "consulta", "información", "respuesta", "presupuesto"}:
        return True
    words = re.findall(r"[\wáéíóúñ]+", s_low)
    if len(words) <= 2 and words and words[0] in {
        "cotización",
        "consulta",
        "información",
        "respuesta",
        "presupuesto",
    }:
        return True
    return False


def _subject_is_weak_brand(subject_part: str) -> bool:
    s = _norm_match_text(subject_part)
    if "labdelivery" in s and len(s.split()) <= 5:
        return True
    if re.match(r"^cotizacion\s+(macerador|frasco|equipo)s?\s*$", s):
        return True
    return False


def subject_context_from_case_body(body_text: str) -> str | None:
    m = re.search(r"\b(ST\d{3,5})\b", body_text, re.I)
    if m:
        return f"ref. {m.group(1).upper()}"
    m = re.search(r"medidor de pH[^.\n]{3,75}", body_text, re.I)
    if m:
        return m.group(0).strip().replace("\n", " ")
    m = re.search(r"modelo\s+([A-Z0-9][A-Z0-9\-]{2,22})\b", body_text)
    if m:
        return f"modelo {m.group(1)}"
    m = re.search(r"Dens[ií]metro[^.\n]{5,90}", body_text, re.I)
    if m:
        return m.group(0).strip().replace("\n", " ")
    m = re.search(r"Refract[oó]metro[^.\n]{5,90}", body_text, re.I)
    if m:
        return m.group(0).strip().replace("\n", " ")
    m = re.search(r"termobalanza[^.\n]{5,75}", body_text, re.I)
    if m:
        return m.group(0).strip().replace("\n", " ")
    m = re.search(
        r"\b(macerador|frascos?\s+de\s+laboratorio|agitador\s+orbital|centr[ií]fuga|"
        r"microcen|biocen|scout\s+stx\s*\d+|pioneer\s+pa\d+)\b[^.\n]{0,55}",
        body_text,
        re.I,
    )
    if m:
        return m.group(0).strip().replace("\n", " ")[:78]
    m = re.search(r"\b(Ohaus|Krüss|Kruss|Eagle\s+Eye)\b", body_text, re.I)
    if m:
        return m.group(0).strip()
    return None


def enrich_generic_asunto_line(draft: str, case_body: str) -> str:
    lines = draft.splitlines()
    if not lines:
        return draft
    first = lines[0]
    if not re.match(r"^asunto:\s*", first, re.I):
        return draft
    subject_part = re.sub(r"^asunto:\s*", "", first, count=1, flags=re.I).strip()
    if not _asunto_subject_part_generic(subject_part) and not _subject_is_weak_brand(
        subject_part
    ):
        return draft
    hint = subject_context_from_case_body(case_body)
    if not hint:
        return draft
    suffix = hint.replace("\n", " ").strip()
    if len(suffix) > 72:
        suffix = suffix[:69].rstrip() + "..."
    lines[0] = f"Asunto: Cotización – {suffix}"
    return "\n".join(lines)


def normalize_signature_block(text: str, *, canonical_signature: str | None = None) -> str:
    """Trim duplicate closings; replace tail with canonical Tatiana or OrigenLab signature."""
    marker = "Saludos cordiales"
    lower = text.lower()
    idx = lower.find(marker.lower())
    chosen = (canonical_signature or "").strip() or _CANONICAL_SIGNATURE
    if idx < 0:
        body = text.rstrip()
        if body:
            return f"{body}\n\n{chosen}"
        return chosen
    head = text[:idx].rstrip()
    return f"{head}\n\n{chosen}"


def maybe_bullet_split_product_line(line: str) -> str | None:
    if len(line) < 70:
        return None
    low = line.lower()
    if " y modelo " not in low and " y modelos " not in low:
        return None
    parts = re.split(r"\s+y\s+Modelo(?:s)?\s+", line, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None
    left, right = parts[0].strip(), parts[1].strip()
    if len(left) < 25 or len(right) < 8:
        return None
    return f"- {left}\n- Modelo {right}"


def postprocess_draft_lines_after_subject(draft: str) -> str:
    lines = draft.splitlines()
    if len(lines) <= 1:
        return draft
    first, rest = lines[0], lines[1:]
    out_rest: list[str] = []
    for line in rest:
        split = maybe_bullet_split_product_line(line)
        out_rest.append(split if split is not None else line)
    return first + "\n" + "\n".join(out_rest)


def dedupe_closing_phrase(text: str, phrase: str) -> str:
    if text.lower().count(phrase.lower()) <= 1:
        return text
    idx = text.lower().find(phrase.lower())
    if idx < 0:
        return text
    before = text[: idx + len(phrase)]
    after = text[idx + len(phrase) :]
    after_lower = after.lower()
    while True:
        pos = after_lower.find(phrase.lower())
        if pos < 0:
            break
        after = after[:pos] + after[pos + len(phrase) :]
        after_lower = after.lower()
    return before + after


def _canonical_outreach_product_paragraph() -> str:
    return (
        "Entre nuestras soluciones destacamos osmómetro crioscópico Knauer, reactivos y equipamiento "
        "para electroforesis Serva, y dispersores Ultra Turrax IKA, entre otras líneas para distintas "
        "necesidades de laboratorio."
    )


def _draft_mentions_canonical_outreach_examples(text: str) -> bool:
    n = _norm_match_text(text)
    return any(
        cue in n
        for cue in (
            "osmometro crioscopico",
            "electroforesis",
            "ultra turrax",
        )
    )


def _lead_specific_outreach_line(outreach_supplement: dict[str, object]) -> str | None:
    pf = str(outreach_supplement.get("product_focus") or "").strip()
    uc = str(outreach_supplement.get("use_case") or "").strip()
    if pf and uc:
        return f"De manera complementaria, también podemos orientarles sobre {pf} para {uc}."
    if pf:
        return f"De manera complementaria, también podemos orientarles sobre {pf}."
    if uc:
        return f"De manera complementaria, también podemos orientarles según su aplicación en {uc}."
    return None


def reinforce_marketing_outreach_structure(
    draft: str,
    *,
    outreach_supplement: dict[str, object] | None = None,
) -> str:
    """Normalize outreach body order: intro -> canonical examples -> lead line -> CTA/contact."""
    supp = outreach_supplement or {}
    text = (draft or "").strip()
    if not text:
        return text
    lines = text.splitlines()
    if not lines:
        return text
    first = lines[0]
    rest_lines = lines[1:]
    greeting = ""
    if rest_lines:
        first_rest = (rest_lines[0] or "").strip()
        if re.match(r"(?i)^estimad[oa]s?(?:/as)?\b|^estimados/as\b", first_rest):
            greeting = first_rest
            rest_lines = rest_lines[1:]
            while rest_lines and not rest_lines[0].strip():
                rest_lines = rest_lines[1:]
    body = "\n".join(rest_lines).strip()
    if not body:
        return text
    parts = [p.strip() for p in re.split(r"\n{2,}", body) if p.strip()]
    if not parts:
        return text
    canon_para = _canonical_outreach_product_paragraph()
    lead_line = _lead_specific_outreach_line(supp)
    intro_parts: list[str] = []
    cta_parts: list[str] = []
    contact_parts: list[str] = []
    other_parts: list[str] = []
    # Remove any model-written canonical/examples paragraph; we will reinsert it in a fixed position.
    for p in parts:
        low = _norm_match_text(p)
        if (
            "entre nuestras soluciones destacamos" in low
            or _draft_mentions_canonical_outreach_examples(p)
        ):
            continue
        if low.startswith("junto con saludar") or "quisiera presentarles origenlab" in low:
            intro_parts.append(p)
        elif low.startswith("si le interesa") or low.startswith("si les interesa"):
            cta_parts.append(p)
        elif low.startswith("pueden escribirnos"):
            contact_parts.append(p)
        elif lead_line and _norm_match_text(p) == _norm_match_text(lead_line):
            continue
        else:
            other_parts.append(p)
    ordered_parts: list[str] = []
    ordered_parts.extend(intro_parts[:1] or other_parts[:1])
    if intro_parts[:1]:
        other_parts = [p for p in other_parts if p not in intro_parts[:1]]
    ordered_parts.append(canon_para)
    if lead_line and _norm_match_text(lead_line) not in _norm_match_text(body):
        ordered_parts.append(lead_line)
    ordered_parts.extend(other_parts)
    ordered_parts.extend(cta_parts[:1])
    ordered_parts.extend(contact_parts[:1])
    rebuilt_parts: list[str] = []
    if greeting:
        rebuilt_parts.append(greeting)
    rebuilt_parts.extend([p for p in ordered_parts if p.strip()])
    rebuilt = "\n\n".join(rebuilt_parts).strip()
    return first + "\n" + rebuilt


def postprocess_openai_draft(
    raw: str,
    case_body: str,
    *,
    canonical_signature: str | None = None,
    drafting_profile: str = DRAFTING_PROFILE_TATIANA_HISTORICAL,
    outreach_supplement: dict[str, object] | None = None,
) -> str:
    t = raw.strip()
    t = postprocess_draft_lines_after_subject(t)
    lines = t.splitlines()
    if lines:
        first, rest = lines[0], lines[1:]
        body = "\n".join(rest)
        body = grounding_sanitize_below_asunto(body, case_body)
        t = first + ("\n" + body if body.strip() else "")
    t = enrich_generic_asunto_line(t, case_body)
    t = harden_asunto_line(t)
    if drafting_profile == DRAFTING_PROFILE_ORIGENLAB and outreach_supplement:
        t = reinforce_marketing_outreach_structure(
            t,
            outreach_supplement=outreach_supplement,
        )
    t = normalize_signature_block(t, canonical_signature=canonical_signature)
    t = dedupe_closing_phrase(
        t, "Quedo atenta a cualquier consulta, no dude en contactarme."
    )
    t = dedupe_closing_phrase(t, "Quedo atenta a cualquier consulta.")
    if drafting_profile == DRAFTING_PROFILE_ORIGENLAB:
        t = dedupe_closing_phrase(t, "Quedo atenta a sus comentarios o consultas.")
    return t


def validate_marketing_outreach_draft(
    draft: str,
    *,
    canonical_signature: str,
    variant_type: str | None = None,
) -> str | None:
    """Return validation failure code, or ``None`` when draft looks safe enough."""
    text = (draft or "").strip()
    if not text:
        return "marketing_outreach_empty"
    if _PLACEHOLDER_TOKEN_RE.search(text):
        return "marketing_outreach_placeholder_token"
    first = text.splitlines()[0].strip() if text.splitlines() else ""
    if variant_type != MARKETING_VARIANT_FOLLOWUP and re.match(r"(?i)^asunto:\s*re:\s*", first):
        return "marketing_outreach_reply_subject"
    if _SUPPORT_REPLY_PHRASES_RE.search(text):
        return "marketing_outreach_reply_language"
    if canonical_signature.strip() and canonical_signature.strip() not in text:
        return "marketing_outreach_signature_mismatch"
    if "Tatiana Vivanco" not in text:
        return "marketing_outreach_missing_sender_identity"
    return None


class OpenAIChatDraftGenerator(DraftGenerator):
    """
    OpenAI Chat Completions API (or compatible base_url).

    Safe defaults: abstains with notes on thin context, empty retrieval (optional), or API errors.
    """

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        min_body_chars: int = 40,
        abstain_on_empty_retrieval: bool = True,
        temperature: float = 0.35,
        max_tokens: int = 1800,
    ) -> None:
        self._client = client
        self._model = model
        self._min_body_chars = min_body_chars
        self._abstain_on_empty_retrieval = abstain_on_empty_retrieval
        self._temperature = temperature
        self._max_tokens = max_tokens

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAIChatDraftGenerator:
        key = settings.resolved_tatiana_openai_api_key()
        if not key:
            raise TatianaLLMConfigurationError(
                "OpenAI API key missing: set ORIGENLAB_TATIANA_OPENAI_API_KEY or OPENAI_API_KEY "
                "in the environment (or .env)."
            )
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": key, "timeout": settings.tatiana_openai_timeout_seconds}
        if settings.tatiana_openai_base_url:
            kwargs["base_url"] = settings.tatiana_openai_base_url.strip()
        client = OpenAI(**kwargs)
        return cls(
            client=client,
            model=settings.tatiana_openai_model.strip(),
            min_body_chars=settings.tatiana_llm_min_body_chars,
            abstain_on_empty_retrieval=settings.tatiana_llm_abstain_on_empty_retrieval,
        )

    def generate(self, prompt_blocks: dict[str, object]) -> DraftResult:
        case = dict(prompt_blocks.get("case") or {})
        body = str(case.get("body_text") or "").strip()
        if len(body) < self._min_body_chars:
            return DraftResult(
                text="",
                provider_name="openai_chat",
                abstained=True,
                notes="insufficient_context_body_too_short",
            )

        if should_abstain_low_information_case(body):
            return DraftResult(
                text="",
                provider_name="openai_chat",
                abstained=True,
                notes="low_information_case",
            )

        styles = list(prompt_blocks.get("style_examples") or [])
        precedents = list(prompt_blocks.get("retrieved_precedents") or [])
        if self._abstain_on_empty_retrieval and not styles and not precedents:
            return DraftResult(
                text="",
                provider_name="openai_chat",
                abstained=True,
                notes="insufficient_retrieval_evidence",
            )

        profile = str(prompt_blocks.get("drafting_profile") or DRAFTING_PROFILE_TATIANA_HISTORICAL)
        canonical_signature = (
            str(prompt_blocks.get("approved_signature_block") or "").strip() or None
        )
        if profile != DRAFTING_PROFILE_ORIGENLAB:
            canonical_signature = None
        outreach_supp = dict(prompt_blocks.get("marketing_outreach_supplement") or {})
        outreach_variant = str(outreach_supp.get("variant_type") or "").strip() or None
        if outreach_supp:
            canonical_signature = (
                str(outreach_supp.get("canonical_signature_block") or "").strip()
                or canonical_signature
            )

        subject_raw = str(case.get("subject") or "")
        subject_decoded = decode_mime_subject(subject_raw)
        recipient_hint = extract_recipient_name_hint(body)

        if profile == DRAFTING_PROFILE_ORIGENLAB:
            system = (
                "Eres asistente de redacción comercial B2B para OrigenLab (Chile). "
                "Devuelve SOLO el borrador listo para pegar: primera línea exactamente "
                "'Asunto: …' (concreto; evita asuntos genéricos vacíos). "
                "Luego el cuerpo en párrafos claros, sin markdown. "
                "Identidad y datos de contacto: solo los de company_facts y approved_signature_block del JSON; "
                "nunca uses marca, dominio, teléfono ni direcciones de ejemplos de estilo (p. ej. Labdelivery). "
                "style_examples y retrieved_precedents son SOLO tono y estructura — no fuente de hechos. "
                "Hechos comerciales: case.body_text, case_context_supplement (explicit_known_facts), "
                "o posicionamiento general en company_facts — no inventar plazos, precios ni garantías. "
                "Cumple commercial_policy al pie de la letra. "
                "Nunca dejes placeholders o plantillas sin resolver como [Tu Nombre], [Nombre], [Institución], "
                "<nombre>, <empresa> o {{campo}}. "
                "Si case_context_supplement.missing_information indica vacíos críticos y el cuerpo no alcanza "
                "para una respuesta segura, devuelve exactamente ABSTAIN en una sola línea. "
                "Cierra el cuerpo antes de la firma con una frase profesional breve; luego respeta exactamente "
                "approved_signature_block como bloque final de firma (post-proceso lo alineará)."
            )
        else:
            system = (
                "Eres asistente de redacción comercial en español (voz Tatiana / Labdelivery). "
                "Devuelve SOLO el borrador listo para pegar: primera línea exactamente "
                "'Asunto: …' (concreto y breve: producto/modelo tomado del caso; sin cadenas largas ni asuntos "
                "solo «Cotización», «Consulta» o el nombre de la empresa como única clave). "
                "Luego el cuerpo en párrafos claros, sin bloques markdown. "
                "Si el caso menciona varias opciones o equipos distintos en la misma frase, preséntalos "
                "como lista con viñetas (- …), con el nombre o modelo real de cada ítem; nunca uses "
                "placeholders del tipo «Modelo 1», «Modelo 2», «Modelo 3». "
                "Si case.recipient_name_hint existe en el JSON del usuario, saluda usando ese nombre de forma "
                "coherente con el saludo del caso (Estimada/Estimado + nombre). "
                "Hechos comerciales y técnicos solo si aparecen literalmente en case.body_text: números de "
                "cotización (p. ej. N°…), plazos de entrega, instalación/puesta en marcha, términos CIF/incoterms, "
                "montos mínimos o políticas, porcentajes o afirmaciones comparativas (p. ej. «más rápido», "
                "«mayor precisión»). Los ejemplos recuperados son solo guía de estilo, no fuente de hechos. "
                "No inventes precios ni promesas. "
                "Cierra con «Quedo atenta…» y «Saludos cordiales,» y firma; no dupliques un segundo bloque de firma. "
                "Si falta información esencial para cotizar, devuelve exactamente la palabra ABSTAIN en una sola línea."
            )
        case_for_model = dict(case)
        case_for_model["subject_decoded"] = subject_decoded
        if recipient_hint:
            case_for_model["recipient_name_hint"] = recipient_hint

        payload: dict[str, Any] = {
            "instruction": prompt_blocks.get("instruction"),
            "case": case_for_model,
            "style_examples": styles,
            "retrieved_precedents": precedents,
        }
        if profile == DRAFTING_PROFILE_ORIGENLAB:
            payload["company_facts"] = prompt_blocks.get("company_facts")
            payload["commercial_policy"] = prompt_blocks.get("commercial_policy")
            payload["case_context_supplement"] = prompt_blocks.get("case_context_supplement")
            payload["approved_signature_block"] = prompt_blocks.get("approved_signature_block")
            payload["style_reference_notice"] = prompt_blocks.get("style_reference_notice")
            payload["marketing_outreach_supplement"] = prompt_blocks.get("marketing_outreach_supplement")
        user = json.dumps(payload, ensure_ascii=False, indent=2)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except Exception as e:  # noqa: BLE001 — provider errors become safe abstentions
            return DraftResult(
                text="",
                provider_name="openai_chat",
                abstained=True,
                notes=f"openai_error:{type(e).__name__}",
            )

        choice = completion.choices[0].message
        raw = (getattr(choice, "content", None) or "").strip()
        if not raw:
            return DraftResult(
                text="",
                provider_name="openai_chat",
                abstained=True,
                notes="openai_empty_response",
            )
        if raw.upper() == "ABSTAIN" or raw.splitlines()[0].strip().upper() == "ABSTAIN":
            return DraftResult(
                text="",
                provider_name="openai_chat",
                abstained=True,
                notes="model_abstained",
            )
        processed = postprocess_openai_draft(
            raw,
            body,
            canonical_signature=canonical_signature,
            drafting_profile=profile,
            outreach_supplement=outreach_supp,
        )
        if profile == DRAFTING_PROFILE_ORIGENLAB and outreach_supp:
            failure = validate_marketing_outreach_draft(
                processed,
                canonical_signature=canonical_signature or "",
                variant_type=outreach_variant,
            )
            if failure:
                return DraftResult(
                    text="",
                    provider_name="openai_chat",
                    abstained=True,
                    notes=failure,
                )
        return DraftResult(
            text=processed,
            provider_name="openai_chat",
            abstained=False,
            notes="openai_chat_completion",
        )

