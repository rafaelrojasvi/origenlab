"""Reusable CSV normalization/validation helpers for campaign workflows."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urlparse

from origenlab_email_pipeline.business_mart import emails_in

_WS_RE = re.compile(r"\s+")
_HEADER_WS_RE = re.compile(r"[\s\-]+")
_CONFIDENCE_ALLOWED = {"high", "medium", "low"}
_THIRD_PARTY_HINTS = (
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "wikipedia.org",
)
_OFFICIAL_REGISTRY_HINTS = (
    "superdesalud.gob.cl",
    "mercadopublico.cl",
    "chilecompra.cl",
)


def normalize_header_name(name: str) -> str:
    s = str(name or "").strip().lower()
    s = _HEADER_WS_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def normalize_row_dict(row: dict | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(row, dict):
        return out
    for k, v in row.items():
        if k is None:
            continue
        key = normalize_header_name(str(k))
        if not key:
            continue
        if isinstance(v, list):
            # DictReader extras under None or parser anomalies; ignore by default.
            continue
        out[key] = str(v or "").strip()
    return out


def sanitize_csv_text(value: object, *, max_len: int | None = None) -> str:
    s = str(value or "")
    if not s:
        return ""
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = "".join((" " if (ord(ch) < 32 or 127 <= ord(ch) <= 159) else ch) for ch in s)
    s = _WS_RE.sub(" ", s).strip()
    if max_len is not None and max_len > 0 and len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def extract_email_from_aliases(row: dict[str, str], aliases: tuple[str, ...] | list[str]) -> str:
    for a in aliases:
        em = validate_email_syntax(row.get(normalize_header_name(a), ""))
        if em:
            return em
    return ""


def has_required_columns(headers: list[str] | set[str] | tuple[str, ...], required: tuple[str, ...] | list[str]) -> tuple[bool, list[str]]:
    h = {normalize_header_name(x) for x in headers}
    missing = [normalize_header_name(r) for r in required if normalize_header_name(r) not in h]
    return (len(missing) == 0, missing)


def detect_trailing_prose_or_summary_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    warnings: list[str] = []
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    for i, line in enumerate(lines, start=1):
        s = line.strip()
        if not s:
            continue
        if s.startswith("```"):
            warnings.append(f"line {i}: markdown fence detected")
        if re.match(r"^[a-zA-Z_]+\s*=\s*.+$", s):
            warnings.append(f"line {i}: summary-like assignment detected")
        if s.startswith("#"):
            warnings.append(f"line {i}: comment/prose line detected")
    return warnings


def validate_email_syntax(email: str) -> str:
    s = str(email or "").strip().lower()
    if not s:
        return ""
    found = emails_in(s)
    if not found:
        return ""
    return found[0] if found[0] == s else ""


def normalize_confidence(value: str) -> str:
    return str(value or "").strip().lower()


def validate_confidence(value: str) -> bool:
    v = normalize_confidence(value)
    return v in _CONFIDENCE_ALLOWED or v == ""


def validate_source_url(value: str) -> bool:
    s = str(value or "").strip()
    if not s:
        return False
    try:
        u = urlparse(s)
    except ValueError:
        return False
    return u.scheme in {"http", "https"} and bool(u.netloc)


def source_host_matches_domain(source_url: str, domain: str) -> bool:
    if not validate_source_url(source_url):
        return False
    host = (urlparse(source_url).hostname or "").strip().lower()
    dom = str(domain or "").strip().lower()
    if not host or not dom:
        return False
    return host == dom or host.endswith("." + dom)


def source_looks_third_party(source_url: str) -> bool:
    if not validate_source_url(source_url):
        return False
    host = (urlparse(source_url).hostname or "").strip().lower()
    return any(h in host for h in _THIRD_PARTY_HINTS)


def source_is_official_registry_exception(source_url: str) -> bool:
    if not validate_source_url(source_url):
        return False
    host = (urlparse(source_url).hostname or "").strip().lower()
    return any(h in host for h in _OFFICIAL_REGISTRY_HINTS)


def read_csv_normalized(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = [normalize_header_name(h) for h in (reader.fieldnames or [])]
        rows = [normalize_row_dict(r) for r in reader]
    return headers, rows

