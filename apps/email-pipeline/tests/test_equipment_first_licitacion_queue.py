"""Tests for equipment-first Licitacion_Publicada queue builder."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from origenlab_email_pipeline.equipment_first_licitacion_queue import (
    STOP_CONSUMABLES_OUTREACH_CODES,
    build_equipment_queue_rows,
    classify_next_action,
    detect_equipment_categories,
    line_blob,
)


def test_detect_centrifuge_excludes_water_pump_context() -> None:
    blob = "Construcción sala de bombas, 2 centrifugas sumergible para pozo"
    assert detect_equipment_categories(blob) == []


def test_detect_centrifuge_in_lab_context() -> None:
    blob = "Centrifuga para laboratorio clinico refrigerada"
    cats = detect_equipment_categories(blob)
    assert any(c == "centrifuge" for c, _ in cats)


def test_ultrasonido_skipped_for_ecografo() -> None:
    blob = "MANTENCIÓN EQUIPOS DE ECOGRAFÍA ultrasonido cardiaco"
    assert not any(c == "lab_ultrasonic_processor" for c, _ in detect_equipment_categories(blob))


def test_tubos_microcentrifuga_excluded_without_equipment_purchase() -> None:
    assert detect_equipment_categories("INSUMOS DE LABORATORIO TUBOS DE MICROCENTRIFUGA") == []
    assert detect_equipment_categories("Tubos para centrifuga, transparente 50 ml") == []
    blob = (
        "ADQUISICIÓN DE MATERIAL DE LABORATORIO PARA PROYECTO | "
        "Tubos para centrifuga, transparente 50 ml"
    )
    assert detect_equipment_categories(blob) == []


def test_generic_balanza_digital_without_lab_context_excluded() -> None:
    assert detect_equipment_categories("BALANZA DIGITAL insumos no clinicos") == []


def test_stop_codes_classified_skip_consumables() -> None:
    for code in STOP_CONSUMABLES_OUTREACH_CODES:
        assert (
            classify_next_action(
                codigo=code,
                category="centrifuge",
                close_dt=datetime(2026, 6, 1),
                maintenance=False,
                arriendo=False,
                convenio_reactivos=False,
                now=datetime(2026, 5, 18),
            )
            == "skip_consumables"
        )


def test_build_queue_from_minimal_csv(tmp_path: Path) -> None:
    src = tmp_path / "Licitacion_Publicada.csv"
    with src.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Textbox69", "ReportTitle"])
        w.writerow(["header", "x"])
        w.writerow(
            [
                "Textbox36",
                "TipoLC",
                "Textbox37",
                "Textbox38",
                "Textbox39",
                "citName",
                "Textbox40",
                "FechaCierre1",
                "rbiDescription",
                "rbiGoodAndService",
                "Unidad_de_Medida",
                "Cantidad",
                "ProductoName",
                "Level1",
                "Level2",
                "Level3",
            ]
        )
        w.writerow(
            [
                "1057898-51-LP26",
                "LP",
                "ADQUISICIÓN DE CENTRIFUGAS UMT",
                "Hospital regional",
                "SERVICIO DE SALUD NUBLE",
                "Región del Ñuble",
                "15/05/2026 14:16:11",
                "04/06/2026 17:00:00",
                "FAMILIA N°1: EQUIPOS UMT 1",
                "41105103",
                "Global",
                "1",
                "Bombas centrífugas de laboratorio",
                "Equipamiento para laboratorios",
                "Equipos e insumos para laboratorio",
                "Bombas y conductos de laboratorio",
            ]
        )
        w.writerow(
            [
                "1497-6-LE26",
                "LE",
                "INSUMOS PARA ANALISIS",
                "SEREMI",
                "SUBSECRETARIA DE SALUD PUBLICA",
                "Región de Los Ríos",
                "01/05/2026 10:00:00",
                "22/05/2026 15:01:00",
                "Reactivos microbiológicos",
                "x",
                "Unidad",
                "1",
                "Medios de cultivo",
                "Lab",
                "Lab",
                "Lab",
            ]
        )

    rows = build_equipment_queue_rows(src, now=datetime(2026, 5, 18, 12, 0, 0))
    codes = {r["codigo_licitacion"] for r in rows}
    assert "1057898-51-LP26" in codes
    assert "1497-6-LE26" not in codes  # consumables only, no equipment line
    nuble = next(r for r in rows if r["codigo_licitacion"] == "1057898-51-LP26")
    assert nuble["equipment_category"] == "centrifuge"
    assert nuble["next_action"] == "quote_now"
