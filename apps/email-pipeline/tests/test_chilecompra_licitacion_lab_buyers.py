from __future__ import annotations

from origenlab_email_pipeline.chilecompra_licitacion_lab_buyers import (
    LicitacionLineRow,
    aggregate_buyers_from_line_rows,
    classify_buyer_organization,
    row_matches_lab_icp,
)


def test_classify_buyer_organization_hospital_signals() -> None:
    assert classify_buyer_organization("HOSPITAL BASE OSORNO") == "hospital"
    assert (
        classify_buyer_organization("COMPLEJO ASISTENCIAL DR. SOTERO DEL RIO")
        == "hospital"
    )
    assert classify_buyer_organization("SERVICIO DE SALUD COQUIMBO") == "servicio_salud"


def test_row_matches_lab_icp_positive() -> None:
    assert row_matches_lab_icp(
        organismo="HOSPITAL X",
        blob="SUMINISTRO DE REACTIVOS PARA LABORATORIO CLÍNICO",
    )


def test_row_matches_lab_icp_negative_no_keyword() -> None:
    assert not row_matches_lab_icp(
        organismo="I MUNICIPALIDAD DE X",
        blob="ADQUISICIÓN DE PAPEL BOND OFICIO",
    )


def test_aggregate_buyers_from_line_rows_dedupes_org_region() -> None:
    rows = [
        LicitacionLineRow(
            numero_adquisicion="1-1-LE26",
            nombre_adquisicion="CONVENIO REACTIVOS LAB",
            descripcion="",
            organismo="HOSPITAL Z",
            region="Región de Test",
            descripcion_producto="REACTIVOS HEMATOLOGÍA",
            generico="",
            nivel_1="",
            nivel_2="",
            nivel_3="",
        ),
        LicitacionLineRow(
            numero_adquisicion="1-2-LE26",
            nombre_adquisicion="OTRO ÍTEM",
            descripcion="",
            organismo="HOSPITAL Z",
            region="Región de Test",
            descripcion_producto="MICROSCOPIO",
            generico="",
            nivel_1="",
            nivel_2="",
            nivel_3="",
        ),
    ]
    agg = aggregate_buyers_from_line_rows(rows)
    assert len(agg) == 1
    assert agg[0]["organization_name"] == "HOSPITAL Z"
    assert agg[0]["matched_line_items"] == 2
    assert "1-1-LE26" in agg[0]["sample_adquisicion_ids"]
    assert "1-2-LE26" in agg[0]["sample_adquisicion_ids"]
