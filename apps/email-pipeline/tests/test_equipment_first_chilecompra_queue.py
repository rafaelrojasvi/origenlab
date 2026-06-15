"""Tests for ChileCompra API → equipment-first queue integration (mocked HTTP)."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from origenlab_email_pipeline.chilecompra_api import ChileCompraTicketMissingError
from origenlab_email_pipeline.equipment_first_chilecompra_queue import (
    build_equipment_queue_from_chilecompra_api,
    summary_passes_keyword_prefilter,
    write_chilecompra_api_queue_outputs,
)
from origenlab_email_pipeline.equipment_first_licitacion_queue import (
    build_equipment_queue_rows_from_normalized_rows,
)

_SECRET_TICKET = "00000000-0000-0000-0000-000000000099"
_T0 = datetime(2026, 6, 14, 12, 0, 0)


def _summary_row(
    *,
    codigo: str,
    title: str,
    descripcion: str = "",
) -> dict[str, str]:
    return {
        "codigo": codigo,
        "tipo_licitacion": "LP",
        "title": title,
        "descripcion": descripcion,
        "buyer": "Hospital Demo",
        "region": "Región Metropolitana",
        "fecha_publicacion": "01/06/2026 10:00:00",
        "close_date": "20/06/2026 17:00:00",
        "line_description": "",
        "unspsc_code": "",
        "unidad": "",
        "cantidad": "",
        "producto": "",
        "nivel_1": "",
        "nivel_2": "",
        "nivel_3": "",
    }


def test_summary_keyword_prefilter_accepts_equipment_terms() -> None:
    row = _summary_row(codigo="1-1-LP26", title="Adquisición centrifuga laboratorio")
    assert summary_passes_keyword_prefilter(row) is True
    assert summary_passes_keyword_prefilter(
        _summary_row(codigo="2-2-LP26", title="Pavimentación calle principal")
    ) is False


def test_build_equipment_queue_from_normalized_rows_centrifuge() -> None:
    rows = [
        {
            **_summary_row(codigo="1057898-51-LP26", title="CENTRIFUGAS UMT"),
            "line_description": "Bombas centrífugas de laboratorio",
            "producto": "Centrifuga refrigerada",
            "nivel_1": "Equipamiento para laboratorios",
        }
    ]
    out = build_equipment_queue_rows_from_normalized_rows(rows, now=_T0)
    assert len(out) == 1
    assert out[0]["codigo_licitacion"] == "1057898-51-LP26"
    assert out[0]["equipment_category"] == "centrifuge"
    assert out[0]["next_action"] == "quote_now"


def test_build_equipment_queue_from_normalized_rows_balance() -> None:
    rows = [
        {
            **_summary_row(codigo="2000-1-LP26", title="Balanza analítica laboratorio"),
            "line_description": "Balanza analítica 0.1 mg para laboratorio clínico",
            "producto": "Balanza",
        }
    ]
    out = build_equipment_queue_rows_from_normalized_rows(rows, now=_T0)
    assert out[0]["equipment_category"] == "balance"


def test_build_equipment_queue_from_normalized_rows_sonicator() -> None:
    rows = [
        {
            **_summary_row(codigo="3000-1-LP26", title="Sonicador laboratorio"),
            "line_description": "Procesador ultrasónico para laboratorio",
            "producto": "Sonicador",
        }
    ]
    out = build_equipment_queue_rows_from_normalized_rows(rows, now=_T0)
    assert out[0]["equipment_category"] == "lab_ultrasonic_processor"


def test_build_equipment_queue_from_normalized_rows_excludes_consumables_only() -> None:
    rows = [
        {
            **_summary_row(codigo="1497-6-LE26", title="INSUMOS PARA ANALISIS"),
            "line_description": "Reactivos microbiológicos y medios de cultivo",
            "producto": "Reactivos",
        }
    ]
    assert build_equipment_queue_rows_from_normalized_rows(rows, now=_T0) == []


def test_build_equipment_queue_from_chilecompra_api_mocked(tmp_path: Path) -> None:
    summaries = {
        "Listado": [
            {
                "CodigoExterno": "1051-1-LP26",
                "Nombre": "Adquisición centrifuga laboratorio",
                "Descripcion": "Equipos para laboratorio clínico",
                "Comprador": {"NombreOrganismo": "Hospital Demo", "Region": "RM"},
                "FechaCierre": "20/06/2026 17:00:00",
            },
            {
                "CodigoExterno": "9000-1-LP26",
                "Nombre": "Pavimentación vial urbana",
                "Descripcion": "Obras viales",
            },
        ]
    }
    detail = {
        "Listado": [
            {
                "CodigoExterno": "1051-1-LP26",
                "Nombre": "Adquisición centrifuga laboratorio",
                "Comprador": {"NombreOrganismo": "Hospital Demo", "Region": "RM"},
                "FechaCierre": "20/06/2026 17:00:00",
                "Items": {
                    "Listado": [
                        {
                            "Descripcion": "Centrifuga refrigerada para laboratorio clínico",
                            "NombreProducto": "Centrifuga",
                            "Cantidad": "2",
                        }
                    ]
                },
            }
        ]
    }

    fetch_list = MagicMock(return_value=summaries)
    fetch_detail = MagicMock(return_value=detail)

    rows, manifest = build_equipment_queue_from_chilecompra_api(
        ticket=_SECRET_TICKET,
        max_details=100,
        now=_T0,
        fetch_licitaciones_fn=fetch_list,
        fetch_licitacion_by_codigo_fn=fetch_detail,
    )

    assert manifest["fetched_summaries"] == 2
    assert manifest["candidate_summaries"] == 1
    assert manifest["detail_requests"] == 1
    assert manifest["output_rows"] == 1
    fetch_list.assert_called_once()
    fetch_detail.assert_called_once_with("1051-1-LP26", ticket=_SECRET_TICKET)
    assert rows[0]["equipment_category"] == "centrifuge"
    assert "source:chilecompra_api" in rows[0]["reason"]


def test_build_equipment_queue_respects_max_details() -> None:
    summaries = {
        "Listado": [
            {
                "CodigoExterno": f"{index}-1-LP26",
                "Nombre": f"Adquisición centrifuga laboratorio {index}",
                "Descripcion": "Equipos laboratorio",
            }
            for index in range(5)
        ]
    }
    fetch_list = MagicMock(return_value=summaries)
    fetch_detail = MagicMock(
        return_value={
            "Listado": [
                {
                    "CodigoExterno": "x",
                    "Nombre": "Adquisición centrifuga laboratorio",
                    "Items": {
                        "Descripcion": "Centrifuga refrigerada laboratorio clínico",
                    },
                }
            ]
        }
    )

    _rows, manifest = build_equipment_queue_from_chilecompra_api(
        ticket=_SECRET_TICKET,
        max_details=2,
        now=_T0,
        fetch_licitaciones_fn=fetch_list,
        fetch_licitacion_by_codigo_fn=fetch_detail,
    )

    assert manifest["candidate_summaries"] == 5
    assert manifest["detail_requests"] == 2
    assert fetch_detail.call_count == 2


def test_write_chilecompra_api_queue_outputs_csv_fields(tmp_path: Path) -> None:
    rows = [
        {
            "codigo_licitacion": "1051-1-LP26",
            "buyer": "Hospital Demo",
            "region": "RM",
            "close_date": "20/06/2026 17:00:00",
            "title": "Centrifuga",
            "item_description": "Centrifuga refrigerada",
            "equipment_category": "centrifuge",
            "fit_score": "75",
            "reason": "source:chilecompra_api; equipment:centrifuge",
            "next_action": "quote_now",
        }
    ]
    out_csv = tmp_path / "equipment_first_operator_queue_chilecompra_api_20260614.csv"
    manifest = {
        "source": "chilecompra_api",
        "generated_at_utc": _T0.isoformat(),
        "fetched_summaries": 1,
        "candidate_summaries": 1,
        "detail_requests": 1,
        "normalized_item_rows": 1,
        "output_rows": 1,
        "by_next_action": {"quote_now": 1},
    }
    stats = write_chilecompra_api_queue_outputs(
        rows=rows,
        manifest=manifest,
        out_csv=out_csv,
    )

    assert out_csv.is_file()
    assert Path(stats["manifest_path"]).is_file()
    with out_csv.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == [
            "codigo_licitacion",
            "buyer",
            "region",
            "close_date",
            "title",
            "item_description",
            "equipment_category",
            "fit_score",
            "reason",
            "next_action",
        ]
        row = next(reader)
        assert row["codigo_licitacion"] == "1051-1-LP26"
        assert "source:chilecompra_api" in row["reason"]

    manifest_data = json.loads(Path(stats["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest_data["output_rows"] == 1
    assert manifest_data["by_next_action"]["quote_now"] == 1


def test_build_equipment_queue_missing_ticket_raises_clear_error() -> None:
    with pytest.raises(ChileCompraTicketMissingError, match="CHILECOMPRA_API_TICKET"):
        build_equipment_queue_from_chilecompra_api(
            fetch_licitaciones_fn=MagicMock(),
            fetch_licitacion_by_codigo_fn=MagicMock(),
        )
