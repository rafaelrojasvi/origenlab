"""Tests for publishing ChileCompra API queue to canonical dashboard CSV."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from origenlab_email_pipeline.equipment_first_chilecompra_publish import (
    CHILECOMPRA_CONTACT_STATUS,
    CHILECOMPRA_REVIEW_NOTE,
    CHILECOMPRA_SAFE_CHANNEL,
    PUBLISHED_DASHBOARD_FIELDS,
    enrich_chilecompra_row_for_dashboard,
    publish_chilecompra_equipment_queue_for_dashboard,
    publish_chilecompra_equipment_rows,
    sort_chilecompra_dashboard_rows,
    update_active_manifest_canonical_queue,
    write_published_dashboard_csv,
)

_SECRET_TICKET = "00000000-0000-0000-0000-000000000099"


def _source_row(
    *,
    codigo: str,
    next_action: str,
    fit_score: str,
    close_date: str = "20/06/2026 17:00:00",
    title: str = "Adquisición centrifuga laboratorio",
) -> dict[str, str]:
    return {
        "codigo_licitacion": codigo,
        "buyer": "Hospital Demo",
        "region": "RM",
        "close_date": close_date,
        "title": title,
        "item_description": "Centrifuga refrigerada",
        "equipment_category": "centrifuge",
        "fit_score": fit_score,
        "reason": "source:chilecompra_api; equipment:centrifuge",
        "next_action": next_action,
    }


def test_enrich_adds_missing_dashboard_columns_without_buyer_email() -> None:
    enriched = enrich_chilecompra_row_for_dashboard(
        _source_row(codigo="1051-1-LP26", next_action="needs_supplier_quote", fit_score="80")
    )

    assert enriched["safe_channel"] == CHILECOMPRA_SAFE_CHANNEL
    assert enriched["contact_status"] == CHILECOMPRA_CONTACT_STATUS
    assert enriched["supplier_needed"] == "yes"
    assert enriched["contact_email"] == ""
    assert CHILECOMPRA_REVIEW_NOTE in enriched["operator_note"]
    assert enriched["gmail_prior_thread"] == "none"


def test_needs_supplier_quote_gets_supplier_needed_yes() -> None:
    enriched = enrich_chilecompra_row_for_dashboard(
        _source_row(codigo="1-1-LP26", next_action="needs_supplier_quote", fit_score="70")
    )
    assert enriched["supplier_needed"] == "yes"
    assert enriched["supplier_contact"] != ""


def test_account_intelligence_only_stays_review_only_and_sorts_lower() -> None:
    rows = sort_chilecompra_dashboard_rows(
        publish_chilecompra_equipment_rows(
            [
                _source_row(
                    codigo="LOW-1-LP26",
                    next_action="account_intelligence_only",
                    fit_score="80",
                ),
                _source_row(
                    codigo="HIGH-1-LP26",
                    next_action="quote_now",
                    fit_score="80",
                ),
            ]
        )
    )

    assert rows[0]["codigo_licitacion"] == "HIGH-1-LP26"
    assert rows[1]["codigo_licitacion"] == "LOW-1-LP26"
    low = next(row for row in rows if row["codigo_licitacion"] == "LOW-1-LP26")
    assert low["next_action"] == "account_intelligence_only"
    assert low["safe_channel"] == CHILECOMPRA_SAFE_CHANNEL
    assert low["contact_status"] == CHILECOMPRA_CONTACT_STATUS


def test_publish_writes_stable_dashboard_columns(tmp_path: Path) -> None:
    source_csv = tmp_path / "equipment_first_operator_queue_chilecompra_api_20260614.csv"
    out_csv = tmp_path / "equipment_first_operator_queue_20260614.csv"
    with source_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        writer.writerow(
            _source_row(codigo="1051-1-LP26", next_action="quote_now", fit_score="85")
        )

    result = publish_chilecompra_equipment_queue_for_dashboard(
        source_csv=source_csv,
        out_csv=out_csv,
    )

    assert result["output_rows"] == 1
    with out_csv.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == list(PUBLISHED_DASHBOARD_FIELDS)
        row = next(reader)
    assert row["codigo_licitacion"] == "1051-1-LP26"
    assert row["priority_rank"] == "1"
    assert row["contact_email"] == ""
    assert _SECRET_TICKET not in out_csv.read_text(encoding="utf-8")


def test_update_manifest_prepends_canonical_queue(tmp_path: Path) -> None:
    active = tmp_path / "active" / "current"
    active.mkdir(parents=True)
    manifest_path = active / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "campaign_mode": "equipment_first",
                "canonical_files": [
                    "equipment_first_operator_queue_chilecompra_api_20260614.csv",
                    "equipment_first_operator_queue_20260518.csv",
                ],
            }
        ),
        encoding="utf-8",
    )
    source_manifest = active / "equipment_first_operator_queue_chilecompra_api_20260614.manifest.json"
    source_manifest.write_text(
        json.dumps({"output_rows": 2, "detail_error_count": 0}),
        encoding="utf-8",
    )

    result = update_active_manifest_canonical_queue(
        active,
        queue_filename="equipment_first_operator_queue_20260614.csv",
        source_manifest=source_manifest,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["canonical_files"][0] == "equipment_first_operator_queue_20260614.csv"
    assert "equipment_first_operator_queue_chilecompra_api_20260614.csv" not in manifest["canonical_files"]
    assert result["chilecompra_api_publish"]["source_output_rows"] == 2
    assert _SECRET_TICKET not in manifest_path.read_text(encoding="utf-8")


def test_sort_uses_close_date_when_fit_and_action_tie() -> None:
    rows = sort_chilecompra_dashboard_rows(
        [
            enrich_chilecompra_row_for_dashboard(
                _source_row(
                    codigo="LATE-1-LP26",
                    next_action="quote_now",
                    fit_score="80",
                    close_date="30/06/2026 17:00:00",
                )
            ),
            enrich_chilecompra_row_for_dashboard(
                _source_row(
                    codigo="SOON-1-LP26",
                    next_action="quote_now",
                    fit_score="80",
                    close_date="10/06/2026 17:00:00",
                )
            ),
        ]
    )
    assert rows[0]["codigo_licitacion"] == "SOON-1-LP26"
