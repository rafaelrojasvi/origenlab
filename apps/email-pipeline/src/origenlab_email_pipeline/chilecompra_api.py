"""Read-only client for Mercado Público licitaciones JSON API."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from origenlab_email_pipeline.equipment_first_licitacion_queue import CSV_COLUMNS

LICITACIONES_API_BASE = (
    "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
)
TICKET_ENV_VAR = "CHILECOMPRA_API_TICKET"
DEFAULT_TIMEOUT_SECONDS = 30.0
FECHA_PATTERN = re.compile(r"^\d{8}$")
_TICKET_IN_URL_RE = re.compile(r"([?&]ticket=)[^&]*", re.IGNORECASE)

UrlopenFn = Callable[..., Any]


class ChileCompraApiError(Exception):
    """Base error for Mercado Público licitaciones API client."""


class ChileCompraTicketMissingError(ChileCompraApiError):
    """Raised when CHILECOMPRA_API_TICKET is not configured."""


class ChileCompraHttpError(ChileCompraApiError):
    """Raised when the API returns a non-success HTTP status."""


class ChileCompraJsonError(ChileCompraApiError):
    """Raised when the API response is not valid JSON or has an unexpected shape."""


def ticket_from_env(environ: dict[str, str] | None = None) -> str:
    """Return the API ticket from ``CHILECOMPRA_API_TICKET``."""
    env = environ if environ is not None else os.environ
    ticket = (env.get(TICKET_ENV_VAR) or "").strip()
    if not ticket:
        raise ChileCompraTicketMissingError(
            f"{TICKET_ENV_VAR} is not set. Request a Mercado Público API ticket and "
            "export it in the environment before calling the live API."
        )
    return ticket


def redact_ticket(text: str, ticket: str) -> str:
    """Remove a ticket value from free-form text (errors, logs)."""
    if not ticket:
        return text
    redacted = text.replace(ticket, "<redacted>")
    return _TICKET_IN_URL_RE.sub(r"\1<redacted>", redacted)


def redact_ticket_in_url(url: str) -> str:
    """Return a URL safe for logs/tests without exposing the ticket query param."""
    return _TICKET_IN_URL_RE.sub(r"\1<redacted>", url)


def validate_fecha(fecha: str) -> str:
    """Validate Mercado Público ``fecha`` query format ``ddmmaaaa``."""
    value = (fecha or "").strip()
    if not FECHA_PATTERN.fullmatch(value):
        raise ValueError("fecha must use ddmmaaaa format (8 digits, e.g. 14062026)")
    return value


def build_licitaciones_url(
    *,
    ticket: str,
    fecha: str | None = None,
    estado: str | None = None,
    codigo: str | None = None,
) -> str:
    """Build the licitaciones JSON endpoint URL."""
    if not (ticket or "").strip():
        raise ValueError("ticket is required")
    params: dict[str, str] = {"ticket": ticket.strip()}
    if fecha is not None:
        params["fecha"] = validate_fecha(fecha)
    if estado is not None and estado.strip():
        params["estado"] = estado.strip()
    if codigo is not None and codigo.strip():
        params["codigo"] = codigo.strip()
    query = urlencode(params)
    parsed = urlparse(LICITACIONES_API_BASE)
    return urlunparse(parsed._replace(query=query))


def _empty_row() -> dict[str, str]:
    return {column: "" for column in CSV_COLUMNS}


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _nested_name(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("NombreOrganismo", "Nombre", "RazonSocial", "NombreUnidad"):
            text = _as_str(value.get(key))
            if text:
                return text
    return _as_str(value)


def _buyer_name(licitacion: dict[str, Any]) -> str:
    for key in ("Comprador", "OrganismoComprador", "Organismo"):
        name = _nested_name(licitacion.get(key))
        if name:
            return name
    for key in ("NombreOrganismo", "NombreUnidad", "Comprador"):
        text = _as_str(licitacion.get(key))
        if text:
            return text
    return ""


def _region_name(licitacion: dict[str, Any]) -> str:
    for key in ("Region", "RegionUnidad", "NombreRegion"):
        text = _as_str(licitacion.get(key))
        if text:
            return text
    for container_key in ("Comprador", "OrganismoComprador", "Organismo"):
        container = licitacion.get(container_key)
        if isinstance(container, dict):
            text = _as_str(container.get("Region") or container.get("RegionUnidad"))
            if text:
                return text
    return ""


def _codigo_externo(licitacion: dict[str, Any]) -> str:
    for key in ("CodigoExterno", "Codigo", "codigo"):
        text = _as_str(licitacion.get(key))
        if text:
            return text
    return ""


def normalize_licitacion_summary(licitacion: dict[str, Any]) -> dict[str, str]:
    """Normalize a basic licitación payload to equipment-first CSV row shape."""
    row = _empty_row()
    row["codigo"] = _codigo_externo(licitacion)
    row["tipo_licitacion"] = _as_str(
        licitacion.get("TipoLicitacion") or licitacion.get("Tipo") or licitacion.get("CodigoTipo")
    )
    row["title"] = _as_str(licitacion.get("Nombre") or licitacion.get("Titulo"))
    row["descripcion"] = _as_str(licitacion.get("Descripcion"))
    row["buyer"] = _buyer_name(licitacion)
    row["region"] = _region_name(licitacion)
    row["fecha_publicacion"] = _as_str(
        licitacion.get("FechaPublicacion") or licitacion.get("FechaCreacion")
    )
    row["close_date"] = _as_str(
        licitacion.get("FechaCierre") or licitacion.get("FechaFinal") or licitacion.get("FechaCierre1")
    )
    return row


def _extract_listado(payload: dict[str, Any]) -> list[dict[str, Any]]:
    listado = payload.get("Listado")
    if listado is None:
        return []
    if isinstance(listado, list):
        return [item for item in listado if isinstance(item, dict)]
    if isinstance(listado, dict):
        nested = listado.get("Licitacion")
        if nested is None:
            return [listado]
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if isinstance(nested, dict):
            return [nested]
    return []


def _extract_items(licitacion: dict[str, Any]) -> list[dict[str, Any]]:
    items = licitacion.get("Items")
    if items is None:
        return []
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    if isinstance(items, dict):
        listado = items.get("Listado")
        if listado is None:
            if any(
                key in items
                for key in (
                    "Descripcion",
                    "NombreProducto",
                    "CodigoProducto",
                    "Categoria",
                    "Cantidad",
                )
            ):
                return [items]
            return []
        if isinstance(listado, list):
            return [item for item in listado if isinstance(item, dict)]
        if isinstance(listado, dict):
            return [listado]
    return []


def _normalize_item_fields(item: dict[str, Any]) -> dict[str, str]:
    return {
        "line_description": _as_str(
            item.get("Descripcion")
            or item.get("NombreProducto")
            or item.get("DescripcionProducto")
            or item.get("rbiDescription")
        ),
        "unspsc_code": _as_str(
            item.get("CodigoProducto")
            or item.get("CodigoCategoria")
            or item.get("CodigoUNSPSC")
            or item.get("unspsc_code")
        ),
        "unidad": _as_str(item.get("UnidadMedida") or item.get("Unidad") or item.get("Medida")),
        "cantidad": _as_str(item.get("Cantidad")),
        "producto": _as_str(
            item.get("Producto") or item.get("NombreProducto") or item.get("Generico")
        ),
        "nivel_1": _as_str(item.get("Nivel1") or item.get("nivel_1") or item.get("Categoria")),
        "nivel_2": _as_str(item.get("Nivel2") or item.get("nivel_2")),
        "nivel_3": _as_str(item.get("Nivel3") or item.get("nivel_3")),
    }


def normalize_licitacion_detail_items(licitacion: dict[str, Any]) -> list[dict[str, str]]:
    """Normalize a detailed licitación plus its line items to CSV-shaped rows."""
    summary = normalize_licitacion_summary(licitacion)
    items = _extract_items(licitacion)
    if not items:
        return [summary]
    rows: list[dict[str, str]] = []
    for item in items:
        row = dict(summary)
        row.update(_normalize_item_fields(item))
        rows.append(row)
    return rows


def normalize_licitaciones_response(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Normalize a list lookup response to summary rows."""
    return [normalize_licitacion_summary(item) for item in _extract_listado(payload)]


def _decode_json_response(raw: bytes, *, ticket: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ChileCompraJsonError("API response is not valid UTF-8") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        message = redact_ticket(str(exc), ticket)
        raise ChileCompraJsonError(f"API response is not valid JSON: {message}") from exc
    if not isinstance(payload, dict):
        raise ChileCompraJsonError("API response must be a JSON object")
    return payload


def _fetch_json(url: str, *, ticket: str, timeout: float, urlopen_fn: UrlopenFn | None) -> dict[str, Any]:
    opener = urlopen_fn or urlopen
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "origenlab-chilecompra-api/1.0"},
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            body = response.read()
    except HTTPError as exc:
        message = redact_ticket(f"HTTP {exc.code} fetching {redact_ticket_in_url(url)}", ticket)
        raise ChileCompraHttpError(message) from exc
    except URLError as exc:
        message = redact_ticket(f"Network error fetching {redact_ticket_in_url(url)}: {exc.reason}", ticket)
        raise ChileCompraHttpError(message) from exc

    if status is not None and int(status) >= 400:
        message = redact_ticket(
            f"HTTP {status} fetching {redact_ticket_in_url(url)}",
            ticket,
        )
        raise ChileCompraHttpError(message)

    return _decode_json_response(body, ticket=ticket)


def fetch_licitaciones(
    *,
    ticket: str | None = None,
    fecha: str | None = None,
    estado: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    urlopen_fn: UrlopenFn | None = None,
) -> dict[str, Any]:
    """Fetch licitaciones list JSON from Mercado Público."""
    resolved_ticket = ticket or ticket_from_env()
    url = build_licitaciones_url(ticket=resolved_ticket, fecha=fecha, estado=estado)
    return _fetch_json(url, ticket=resolved_ticket, timeout=timeout, urlopen_fn=urlopen_fn)


def fetch_licitacion_by_codigo(
    codigo: str,
    *,
    ticket: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    urlopen_fn: UrlopenFn | None = None,
) -> dict[str, Any]:
    """Fetch one licitación by ``codigo`` (detailed payload when available)."""
    resolved_ticket = ticket or ticket_from_env()
    url = build_licitaciones_url(ticket=resolved_ticket, codigo=codigo)
    return _fetch_json(url, ticket=resolved_ticket, timeout=timeout, urlopen_fn=urlopen_fn)
