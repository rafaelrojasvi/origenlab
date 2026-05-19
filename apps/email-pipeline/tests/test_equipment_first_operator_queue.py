"""Tests for equipment-first operator queue builder."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from origenlab_email_pipeline.equipment_first_licitacion_queue import (
    STOP_CONSUMABLES_OUTREACH_CODES,
)
from origenlab_email_pipeline.equipment_first_operator_queue import (
    PRIORITY_RANK,
    build_operator_rows,
    classify_safe_channel,
)


def test_classify_safe_channel() -> None:
    assert (
        classify_safe_channel(
            next_action="quote_now",
            codigo="1057898-51-LP26",
            title="ADQUISICIÓN DE CENTRIFUGAS",
        )
        == "mercado_publico_bid"
    )
    assert (
        classify_safe_channel(
            next_action="needs_supplier_quote",
            codigo="1057501-252-LP26",
            title="MANTENCIÓN",
        )
        == "supplier_quote_request"
    )
    assert (
        classify_safe_channel(
            next_action="contact_after_close",
            codigo="5067-29-L126",
            title="Reactivos",
        )
        == "contact_after_close"
    )


def test_build_operator_rows_excludes_stop_codes(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE outreach_contact_state (contact_email_norm TEXT, state TEXT)"
    )
    conn.execute("CREATE TABLE emails (id INTEGER, date_iso TEXT, subject TEXT, body_text_clean TEXT, source_file TEXT)")
    conn.commit()
    conn.close()

    equipment = [
        {
            "codigo_licitacion": "1057898-51-LP26",
            "buyer": "SERVICIO DE SALUD NUBLE",
            "region": "Ñuble",
            "close_date": "04/06/2026 17:00:00",
            "title": "CENTRIFUGAS UMT",
            "item_description": "EQUIPOS UMT",
            "equipment_category": "centrifuge",
            "fit_score": "85",
            "reason": "equipment:centrifuge",
            "next_action": "quote_now",
        },
        {
            "codigo_licitacion": "1497-6-LE26",
            "buyer": "SSP",
            "region": "X",
            "close_date": "22/05/2026",
            "title": "INSUMOS",
            "item_description": "reactivos",
            "equipment_category": "homogenizer",
            "fit_score": "5",
            "reason": "skip",
            "next_action": "skip_consumables",
        },
    ]
    rows = build_operator_rows(equipment, db_path=db, crosscheck_rows=[])
    assert len(rows) == 1
    assert rows[0]["codigo_licitacion"] == "1057898-51-LP26"
    assert rows[0]["priority_rank"] == "1"
    assert rows[0]["contact_status"] == "no_verified_buyer_email"
    assert "1497-6-LE26" in STOP_CONSUMABLES_OUTREACH_CODES


def test_priority_rank_has_nine_canonical_codes() -> None:
    assert len(PRIORITY_RANK) == 9
