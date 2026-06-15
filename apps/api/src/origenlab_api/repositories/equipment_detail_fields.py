"""Optional ChileCompra / equipment detail fields surfaced from CSV or extra_json."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

EQUIPMENT_DETAIL_OPTIONAL_FIELDS: tuple[str, ...] = (
    "fecha_publicacion",
    "close_at",
    "validity_status",
    "chilecompra_status",
    "chilecompra_status_code",
    "api_checked_at_utc",
    "source",
    "mercado_publico_url",
    "title",
    "unspsc_code",
    "unidad",
    "cantidad",
    "producto",
    "nivel_1",
    "nivel_2",
    "nivel_3",
)

_ANEXO_FIELDS = ("nombre", "tipo", "descripcion", "tamano", "fecha_adjunto", "url")
_UNSAFE_ATTACHMENT_URL_RE = re.compile(
    r"ticket|api\.chilecompra|api\.mercadopublico\.cl",
    re.IGNORECASE,
)


def _extra_json_dict(source: dict[str, Any]) -> dict[str, Any]:
    extra = source.get("extra_json")
    if isinstance(extra, dict):
        return extra
    if isinstance(extra, str) and extra.strip():
        try:
            parsed = json.loads(extra)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _format_close_at(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _is_safe_public_attachment_url(url: str) -> bool:
    text = (url or "").strip()
    if not text:
        return False
    if not text.lower().startswith(("http://", "https://")):
        return False
    return _UNSAFE_ATTACHMENT_URL_RE.search(text) is None


def _normalize_anexo_item(item: dict[str, Any]) -> dict[str, str]:
    normalized = {
        field: str(item.get(field) or "").strip()
        for field in _ANEXO_FIELDS
    }
    if normalized["url"] and not _is_safe_public_attachment_url(normalized["url"]):
        normalized["url"] = ""
    return normalized


def _parse_anexos_json(source: dict[str, Any]) -> list[dict[str, str]]:
    raw: Any = source.get("anexos_json")
    if raw is None:
        raw = _extra_json_dict(source).get("anexos_json")
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        items = parsed if isinstance(parsed, list) else []
    else:
        return []

    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_anexo_item(item)
        if any(normalized.values()):
            out.append(normalized)
    return out


def merge_equipment_detail_fields(item: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Merge read-only detail fields from row columns and/or extra_json."""
    out = dict(item)
    extra = _extra_json_dict(source)
    for field in EQUIPMENT_DETAIL_OPTIONAL_FIELDS:
        if field == "close_at":
            continue
        value: Any = None
        for container in (source, extra):
            candidate = container.get(field)
            if candidate is not None and str(candidate).strip():
                value = candidate
                break
        if value is not None:
            out[field] = str(value).strip()
    close_at = source.get("close_at")
    if close_at is None:
        close_at = extra.get("close_at")
    formatted_close_at = _format_close_at(close_at)
    if formatted_close_at:
        out["close_at"] = formatted_close_at
    anexos = _parse_anexos_json(source)
    if not anexos:
        anexos = _parse_anexos_json(extra)
    if anexos:
        out["anexos"] = anexos
    return out
