"""Tests for Presentación → lead_research prospect merge (read-only ingest)."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.campaigns.presentacion_origenlab_campaign import (
    load_cyberday_sent_emails,
)
from origenlab_email_pipeline.lead_research.lead_research_schema import (
    ensure_lead_research_origin_columns,
    ensure_lead_research_tables,
)
from origenlab_email_pipeline.lead_research.presentacion_prospectos_merge import (
    CLASS_ACTIVE_HOLD,
    CLASS_OLD_FOLLOWUP,
    CLASS_OLD_GMAIL,
    SOURCE_CASO_ACTIVO,
    SOURCE_FOLLOWUP,
    SOURCE_GMAIL,
    merge_presentacion_into_lead_research,
)


def _write_batch1(path: Path, email: str = "ana@hist.cl") -> None:
    path.write_text(
        "organization,email,domain,history_note,priority_score,product_angle\n"
        f"Hist Co,{email},hist.cl,envíos=4; Último asunto: Consulta equipos,80,equipos\n",
        encoding="utf-8",
    )


def _write_batch2(path: Path) -> None:
    path.write_text(
        "organization,email,domain,history_note,priority_score\n"
        "Follow Co,old@follow.cl,follow.cl,envíos=6,75\n",
        encoding="utf-8",
    )


def _write_hold(path: Path) -> None:
    path.write_text(
        "organization,email,domain,case_label,recommended_action\n"
        "Hold Co,pedro@hold.cl,hold.cl,CESMEC,hold_personalized\n",
        encoding="utf-8",
    )


def _write_cyber_log(path: Path, email: str) -> None:
    path.write_text(
        f'{{"sent": [{{"email": "{email}"}}]}}',
        encoding="utf-8",
    )


def _write_exclusion_stubs(dir_path: Path) -> None:
    for name in (
        "contacted_exact_emails_for_exclusion.csv",
        "contacted_domains_for_exclusion.csv",
        "bounced_emails_for_exclusion.csv",
        "suppressed_contacts_for_exclusion.csv",
    ):
        (dir_path / name).write_text("email\n", encoding="utf-8")
    (dir_path / "bounced_emails_for_exclusion.csv").write_text(
        "email\nbounce@blocked.cl\n",
        encoding="utf-8",
    )


@pytest.fixture
def merge_dir(tmp_path: Path) -> Path:
    _write_batch1(tmp_path / "presentacion_batch1_final_send_25.csv")
    _write_batch2(tmp_path / "presentacion_batch2_followup_old_25.csv")
    _write_hold(tmp_path / "presentacion_hold_active_personalized.csv")
    _write_cyber_log(tmp_path / "cyber_production_send_log.json", "cyber@blocked.cl")
    _write_exclusion_stubs(tmp_path)
    return tmp_path


def test_merge_inserts_gmail_followup_hold(tmp_path: Path, merge_dir: Path) -> None:
    conn = sqlite3.connect(":memory:")
    ensure_lead_research_tables(conn)
    ensure_lead_research_origin_columns(conn)
    result = merge_presentacion_into_lead_research(conn, merge_dir)
    assert result["inserted"] == 3

    rows = conn.execute(
        "SELECT email, classification, source_type, status FROM lead_research_prospect"
    ).fetchall()
    by_email = {r[0]: r for r in rows}
    assert by_email["ana@hist.cl"][1] == CLASS_OLD_GMAIL
    assert by_email["ana@hist.cl"][2] == SOURCE_GMAIL
    assert by_email["old@follow.cl"][1] == CLASS_OLD_FOLLOWUP
    assert by_email["old@follow.cl"][2] == SOURCE_FOLLOWUP
    assert by_email["pedro@hold.cl"][1] == CLASS_ACTIVE_HOLD
    assert by_email["pedro@hold.cl"][2] == SOURCE_CASO_ACTIVO
    assert by_email["pedro@hold.cl"][3] == "hold_personalizado"


def test_gmail_not_net_new_safe_classification(tmp_path: Path, merge_dir: Path) -> None:
    conn = sqlite3.connect(":memory:")
    ensure_lead_research_tables(conn)
    ensure_lead_research_origin_columns(conn)
    merge_presentacion_into_lead_research(conn, merge_dir)
    count = conn.execute(
        "SELECT COUNT(*) FROM lead_research_prospect WHERE classification = 'net_new_safe_review'"
    ).fetchone()[0]
    assert count == 0


def test_cyberday_email_skipped(tmp_path: Path, merge_dir: Path) -> None:
    _write_batch1(
        merge_dir / "presentacion_batch1_final_send_25.csv",
        email="cyber@blocked.cl",
    )
    conn = sqlite3.connect(":memory:")
    ensure_lead_research_tables(conn)
    ensure_lead_research_origin_columns(conn)
    result = merge_presentacion_into_lead_research(conn, merge_dir)
    assert result["skipped_blocked"] >= 1
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM lead_research_prospect WHERE email = 'cyber@blocked.cl'"
        ).fetchone()[0]
        == 0
    )


def test_cyberday_loader_excludes_from_set(merge_dir: Path) -> None:
    cyber = load_cyberday_sent_emails(merge_dir / "cyber_production_send_log.json")
    assert "cyber@blocked.cl" in cyber
