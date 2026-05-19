"""Tests for equipment-first deep-search vetter."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from origenlab_email_pipeline.equipment_deepsearch_vetted_queue import (
    VETTED_CLASSIFICATIONS,
    build_vetted_queue,
    vet_deepsearch_rows,
)


def test_vet_skip_noise_consumables() -> None:
    rows = [
        {
            "codigo_licitacion": "1497-6-LE26",
            "title": "Reactivos microbiologia placas petri",
            "source_type": "public_tender",
        }
    ]
    vetted = vet_deepsearch_rows(
        rows,
        operator_by_code={},
        dnr_emails=set(),
        contacted_emails=set(),
        marketing_emails=set(),
        conn=None,
    )
    assert vetted[0].vetted_classification == "skip_noise"


def test_vet_duplicate_on_dnr() -> None:
    rows = [
        {
            "contact_email": "blocked@lab.cl",
            "title": "Centrifuga laboratorio clinico",
            "source_type": "private_lab",
        }
    ]
    vetted = vet_deepsearch_rows(
        rows,
        operator_by_code={},
        dnr_emails={"blocked@lab.cl"},
        contacted_emails=set(),
        marketing_emails=set(),
        conn=None,
    )
    assert vetted[0].vetted_classification == "duplicate_or_contacted"


def test_vet_aligns_operator_queue() -> None:
    rows = [{"codigo_licitacion": "1057898-51-LP26", "title": "Centrifuga UMT", "source_type": "public_tender"}]
    op = {
        "1057898-51-LP26": {
            "next_action": "quote_now",
            "safe_channel": "mercado_publico_bid",
            "contact_status": "no_verified_buyer_email",
            "equipment_category": "centrifuge",
            "operator_note": "test",
        }
    }
    vetted = vet_deepsearch_rows(
        rows,
        operator_by_code=op,
        dnr_emails=set(),
        contacted_emails=set(),
        marketing_emails=set(),
        conn=None,
    )
    assert vetted[0].vetted_classification == "mercado_publico_bid"


def test_build_vetted_queue_missing_input(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Deep-search input not found"):
        build_vetted_queue(
            input_path=tmp_path / "missing.csv",
            output_csv=tmp_path / "out.csv",
            output_md=tmp_path / "out.md",
            operator_queue_path=tmp_path / "op.csv",
            active_current=tmp_path,
            active_root=tmp_path,
            db_path=None,
            date_suffix="20260518",
        )


def test_build_vetted_queue_writes_output(tmp_path: Path) -> None:
    inp = tmp_path / "equipment_deep_research_opportunities_20260518.csv"
    inp.write_text(
        "codigo_licitacion,title,source_type\n"
        "1057898-51-LP26,Centrifuga laboratorio,public_tender\n",
        encoding="utf-8",
    )
    op = tmp_path / "equipment_first_operator_queue_20260518.csv"
    with op.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "codigo_licitacion",
                "next_action",
                "safe_channel",
                "contact_status",
                "equipment_category",
                "operator_note",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "codigo_licitacion": "1057898-51-LP26",
                "next_action": "quote_now",
                "safe_channel": "mercado_publico_bid",
                "contact_status": "no_verified_buyer_email",
                "equipment_category": "centrifuge",
                "operator_note": "n",
            }
        )

    out_csv = tmp_path / "equipment_deepsearch_vetted_queue_20260518.csv"
    out_md = tmp_path / "equipment_deepsearch_vetted_queue_20260518.md"
    stats = build_vetted_queue(
        input_path=inp,
        output_csv=out_csv,
        output_md=out_md,
        operator_queue_path=op,
        active_current=tmp_path,
        active_root=tmp_path,
        db_path=None,
        date_suffix="20260518",
    )
    assert stats["output_rows"] == 1
    assert out_csv.is_file()
    assert out_md.is_file()
    with out_csv.open(encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["vetted_classification"] in VETTED_CLASSIFICATIONS
