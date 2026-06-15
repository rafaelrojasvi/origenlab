"""Golden regression cases for equipment-first ChileCompra tender matching.

These tests intentionally cover business-quality behavior rather than HTTP/API wiring:
which tender text should become an operator queue row, which should be ignored,
and which next_action/category should be preserved as rules evolve.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from origenlab_email_pipeline.equipment_first_licitacion_queue import (
    build_equipment_queue_rows_from_normalized_rows,
)

_NOW = datetime(2026, 6, 14, 12, 0, 0)


def _row(
    *,
    codigo: str,
    title: str,
    line_description: str,
    producto: str = "",
    descripcion: str = "",
    close_date: str = "20/06/2026 17:00:00",
) -> dict[str, str]:
    return {
        "codigo": codigo,
        "buyer": "Hospital Demo",
        "region": "Región Demo",
        "close_date": close_date,
        "title": title,
        "descripcion": descripcion,
        "line_description": line_description,
        "producto": producto,
        "nivel_1": "Equipamiento para laboratorios",
        "nivel_2": "Equipos e insumos para laboratorio",
        "nivel_3": "",
    }


@pytest.mark.parametrize(
    ("case_name", "row", "expected_category"),
    [
        (
            "centrifuge_purchase",
            _row(
                codigo="GOLD-001-LP26",
                title="ADQUISICIÓN DE CENTRÍFUGA DE LABORATORIO",
                line_description="Centrífuga refrigerada para laboratorio clínico",
                producto="Centrífuga",
            ),
            "centrifuge",
        ),
        (
            "analytical_balance_purchase",
            _row(
                codigo="GOLD-002-LP26",
                title="Compra de balanza analítica para laboratorio",
                line_description="Balanza analítica 0.1 mg para laboratorio clínico",
                producto="Balanza analítica",
            ),
            "balance",
        ),
        (
            "lab_sonicator_purchase",
            _row(
                codigo="GOLD-003-LP26",
                title="Adquisición de sonicador para laboratorio",
                line_description="Sonicador de muestras para laboratorio de investigación",
                producto="Sonicador",
            ),
            "sonicator",
        ),
        (
            "ultra_turrax_purchase",
            _row(
                codigo="GOLD-004-LP26",
                title="Adquisición de homogeneizador para laboratorio",
                line_description="Homogeneizador Ultra Turrax para muestras biológicas",
                producto="Homogeneizador",
            ),
            "homogenizer",
        ),
        (
            "lab_ultrasonic_processor_purchase",
            _row(
                codigo="GOLD-005-LP26",
                title="Compra procesador ultrasónico para laboratorio",
                line_description="Procesador ultrasónico para preparación de muestras",
                producto="Procesador ultrasónico",
            ),
            "lab_ultrasonic_processor",
        ),
    ],
)
def test_golden_equipment_purchase_cases_reach_operator_queue(
    case_name: str,
    row: dict[str, str],
    expected_category: str,
) -> None:
    rows = build_equipment_queue_rows_from_normalized_rows([row], now=_NOW)

    assert len(rows) == 1, case_name
    assert rows[0]["codigo_licitacion"] == row["codigo"]
    assert rows[0]["equipment_category"] == expected_category
    assert rows[0]["next_action"] in {"quote_now", "needs_supplier_quote"}


@pytest.mark.parametrize(
    ("case_name", "row"),
    [
        (
            "centrifuge_tubes_are_consumables_not_equipment",
            _row(
                codigo="GOLD-101-LP26",
                title="Adquisición de material de laboratorio",
                line_description="Tubos cónicos para centrífuga 50 ml",
                producto="Tubos para centrífuga",
            ),
        ),
        (
            "clinical_ultrasound_is_not_lab_ultrasonic_equipment",
            _row(
                codigo="GOLD-102-LP26",
                title="Servicio de exámenes de ecografía",
                line_description="Ecografía y ultrasonido cardiaco para pacientes",
                producto="Examen de ecografía",
            ),
        ),
        (
            "generic_balance_without_lab_context_is_too_broad",
            _row(
                codigo="GOLD-103-LP26",
                title="Compra de balanza digital",
                line_description="Balanza digital para control de peso general",
                producto="Balanza digital",
            ),
        ),
        (
            "maintenance_only_centrifuge_service_is_not_a_purchase",
            _row(
                codigo="GOLD-104-LP26",
                title="Servicio de mantenimiento de equipos de laboratorio",
                descripcion="Contratar mantenimiento preventivo y correctivo",
                line_description="Mantenimiento preventivo y correctivo de centrífuga de laboratorio",
                producto="Mantenimiento centrífuga",
            ),
        ),
    ],
)
def test_golden_non_equipment_or_service_cases_do_not_reach_operator_queue(
    case_name: str,
    row: dict[str, str],
) -> None:
    rows = build_equipment_queue_rows_from_normalized_rows([row], now=_NOW)

    assert rows == [], case_name
