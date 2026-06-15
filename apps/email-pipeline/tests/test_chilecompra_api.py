"""Tests for Mercado Público licitaciones API client (mocked HTTP only)."""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import MagicMock
from urllib.error import HTTPError

import pytest

from origenlab_email_pipeline.chilecompra_api import (
    ChileCompraHttpError,
    ChileCompraJsonError,
    ChileCompraTicketMissingError,
    build_licitaciones_url,
    fetch_licitacion_by_codigo,
    fetch_licitaciones,
    normalize_licitacion_detail_items,
    normalize_licitacion_summary,
    normalize_licitaciones_response,
    redact_ticket,
    redact_ticket_in_url,
    ticket_from_env,
    validate_fecha,
)
from origenlab_email_pipeline.equipment_first_licitacion_queue import CSV_COLUMNS

_SECRET_TICKET = "00000000-0000-0000-0000-000000000099"


def _mock_response(payload: dict[str, Any] | str, *, status: int = 200) -> MagicMock:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    if isinstance(payload, str):
        body = payload.encode("utf-8")
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.status = status
    response.getcode.return_value = status
    response.read.return_value = body
    return response


def test_build_licitaciones_url_includes_ticket_but_log_helper_redacts() -> None:
    url = build_licitaciones_url(ticket=_SECRET_TICKET, fecha="14062026", estado="activas")
    assert f"ticket={_SECRET_TICKET}" in url
    assert "fecha=14062026" in url
    assert "estado=activas" in url
    safe = redact_ticket_in_url(url)
    assert _SECRET_TICKET not in safe
    assert "ticket=<redacted>" in safe


def test_ticket_from_env_missing_raises_clear_error() -> None:
    with pytest.raises(ChileCompraTicketMissingError, match="CHILECOMPRA_API_TICKET"):
        ticket_from_env({})


def test_ticket_from_env_reads_configured_value() -> None:
    assert ticket_from_env({"CHILECOMPRA_API_TICKET": _SECRET_TICKET}) == _SECRET_TICKET


def test_validate_fecha_requires_ddmmaaaa() -> None:
    assert validate_fecha("14062026") == "14062026"
    with pytest.raises(ValueError, match="ddmmaaaa"):
        validate_fecha("2026-06-14")


def test_normalize_summary_from_listado_payload() -> None:
    payload = {
        "Listado": [
            {
                "CodigoExterno": "1051-1-LP26",
                "Tipo": "LP",
                "Nombre": "Adquisición centrifuga laboratorio",
                "Descripcion": "Equipo para laboratorio clínico",
                "Comprador": {"NombreOrganismo": "Hospital Demo", "Region": "Región Metropolitana"},
                "FechaPublicacion": "01/06/2026 10:00:00",
                "FechaCierre": "15/06/2026 15:00:00",
            }
        ]
    }
    rows = normalize_licitaciones_response(payload)
    assert len(rows) == 1
    row = rows[0]
    assert row["codigo"] == "1051-1-LP26"
    assert row["tipo_licitacion"] == "LP"
    assert row["title"] == "Adquisición centrifuga laboratorio"
    assert row["descripcion"] == "Equipo para laboratorio clínico"
    assert row["buyer"] == "Hospital Demo"
    assert row["region"] == "Región Metropolitana"
    assert row["fecha_publicacion"] == "01/06/2026 10:00:00"
    assert row["close_date"] == "15/06/2026 15:00:00"
    assert set(row) == set(CSV_COLUMNS)


def test_missing_listado_returns_empty_list() -> None:
    assert normalize_licitaciones_response({}) == []
    assert normalize_licitaciones_response({"Listado": None}) == []


def test_normalize_detail_items_from_items_listado() -> None:
    licitacion = {
        "CodigoExterno": "2277-2-LR25",
        "Nombre": "Reactivos y equipos",
        "Descripcion": "Compra anual laboratorio",
        "OrganismoComprador": {"NombreOrganismo": "Universidad Demo", "Region": "Biobío"},
        "Items": {
            "Listado": [
                {
                    "Descripcion": "Centrifuga refrigerada 4000 rpm",
                    "CodigoProducto": "41105301",
                    "UnidadMedida": "Unidad",
                    "Cantidad": "2",
                    "NombreProducto": "Centrifuga",
                    "Categoria": "Equipos de laboratorio",
                },
                {
                    "Descripcion": "Balanza analítica 0.1 mg",
                    "CodigoProducto": "41111503",
                    "UnidadMedida": "Unidad",
                    "Cantidad": "1",
                    "NombreProducto": "Balanza",
                    "Nivel2": "Instrumentos",
                    "Nivel3": "Balanza",
                },
            ]
        },
    }
    rows = normalize_licitacion_detail_items(licitacion)
    assert len(rows) == 2
    assert rows[0]["codigo"] == "2277-2-LR25"
    assert rows[0]["buyer"] == "Universidad Demo"
    assert rows[0]["line_description"] == "Centrifuga refrigerada 4000 rpm"
    assert rows[0]["unspsc_code"] == "41105301"
    assert rows[0]["cantidad"] == "2"
    assert rows[0]["producto"] == "Centrifuga"
    assert rows[0]["nivel_1"] == "Equipos de laboratorio"
    assert rows[1]["line_description"] == "Balanza analítica 0.1 mg"
    assert rows[1]["nivel_2"] == "Instrumentos"
    assert rows[1]["nivel_3"] == "Balanza"


def test_normalize_detail_items_single_item_object() -> None:
    licitacion = {
        "CodigoExterno": "1000-1-LP26",
        "Nombre": "Sonicador",
        "Items": {
            "Descripcion": "Procesador ultrasónico",
            "CodigoProducto": "41105312",
            "Cantidad": "1",
            "UnidadMedida": "Unidad",
        },
    }
    rows = normalize_licitacion_detail_items(licitacion)
    assert len(rows) == 1
    assert rows[0]["line_description"] == "Procesador ultrasónico"
    assert rows[0]["unspsc_code"] == "41105312"


def test_normalize_detail_without_items_returns_summary_only() -> None:
    summary = normalize_licitacion_summary(
        {"CodigoExterno": "1000-2-LP26", "Nombre": "Solo encabezado"}
    )
    rows = normalize_licitacion_detail_items(
        {"CodigoExterno": "1000-2-LP26", "Nombre": "Solo encabezado"}
    )
    assert rows == [summary]
    assert rows[0]["line_description"] == ""


def test_fetch_licitaciones_uses_mocked_http() -> None:
    payload = {"Listado": [{"CodigoExterno": "1-1-LP26", "Nombre": "Demo"}]}
    mock_urlopen = MagicMock(return_value=_mock_response(payload))

    result = fetch_licitaciones(
        ticket=_SECRET_TICKET,
        estado="activas",
        urlopen_fn=mock_urlopen,
    )

    assert result == payload
    called_url = mock_urlopen.call_args[0][0].full_url
    assert "estado=activas" in called_url
    assert f"ticket={_SECRET_TICKET}" in called_url


def test_fetch_licitacion_by_codigo_uses_codigo_param() -> None:
    payload = {"Listado": [{"CodigoExterno": "1051-1-LP26", "Nombre": "Detalle"}]}
    mock_urlopen = MagicMock(return_value=_mock_response(payload))

    result = fetch_licitacion_by_codigo(
        "1051-1-LP26",
        ticket=_SECRET_TICKET,
        urlopen_fn=mock_urlopen,
    )

    assert result == payload
    called_url = mock_urlopen.call_args[0][0].full_url
    assert "codigo=1051-1-LP26" in called_url


def test_fetch_http_error_redacts_ticket_from_message() -> None:
    def _raise_http_error(*_args: object, **_kwargs: object) -> None:
        url = build_licitaciones_url(ticket=_SECRET_TICKET, estado="activas")
        raise HTTPError(url, 403, "Forbidden", hdrs=None, fp=io.BytesIO(b"denied"))

    with pytest.raises(ChileCompraHttpError) as exc:
        fetch_licitaciones(ticket=_SECRET_TICKET, urlopen_fn=_raise_http_error)

    message = str(exc.value)
    assert _SECRET_TICKET not in message
    assert "HTTP 403" in message
    assert "<redacted>" in message


def test_fetch_invalid_json_raises_clear_error_without_ticket() -> None:
    mock_urlopen = MagicMock(return_value=_mock_response("not-json"))

    with pytest.raises(ChileCompraJsonError) as exc:
        fetch_licitaciones(ticket=_SECRET_TICKET, urlopen_fn=mock_urlopen)

    assert _SECRET_TICKET not in str(exc.value)


def test_redact_ticket_removes_secret_from_free_form_text() -> None:
    text = f"failed for ticket {_SECRET_TICKET} on retry"
    redacted = redact_ticket(text, _SECRET_TICKET)
    assert _SECRET_TICKET not in redacted
    assert "<redacted>" in redacted
