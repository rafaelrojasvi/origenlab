"""Tests for buyer-opportunity A/B queue builder."""

from __future__ import annotations

import csv
import importlib.util
import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load_module():
    path = REPO / "scripts/qa/build_buyer_opportunity_queue.py"
    spec = importlib.util.spec_from_file_location("build_buyer_opportunity_queue", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load_module()


def test_parse_emails_skips_protected_placeholder(mod) -> None:
    assert mod._parse_emails("[email protegido en web]") == []
    assert mod._parse_emails("a@x.cl; b@y.cl") == ["a@x.cl", "b@y.cl"]


def test_classify_email_flags_do_not_repeat(mod, tmp_path: Path) -> None:
    dnr = tmp_path / "do_not_repeat_master.csv"
    with dnr.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["email_norm"])
        w.writeheader()
        w.writerow({"email_norm": "seen@lab.cl"})
    for name in ("outreach_contacted_all.csv",):
        p = tmp_path / name
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["email_norm"])
            w.writeheader()
    (tmp_path.parent / "all_known_marketing_contacts_dedup.csv").write_text(
        "email_norm\n", encoding="utf-8"
    )
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE outreach_contact_state (contact_email_norm TEXT, state TEXT)"
    )
    conn.execute("CREATE TABLE emails (id INTEGER, date_iso TEXT, recipients TEXT, source_file TEXT)")
    conn.commit()
    conn.close()

    checker = mod.CrossChecker(db, reports_dir=tmp_path)
    status, flags = checker.classify_email("seen@lab.cl")
    assert status == "do_not_contact"
    assert "do_not_repeat_master" in flags

    status_clean, _ = checker.classify_email("new@lab.cl")
    assert status_clean == "clean_new_target"


def test_build_rows_marks_suppressed_private_lab(mod, tmp_path: Path) -> None:
    priv = tmp_path / "origenlab_private_lab_targets_20260518.csv"
    with priv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "prioridad",
                "institucion",
                "tipo",
                "region_ciudad",
                "contact_email",
                "fit_signal",
                "linea_origenlab_sugerida",
                "accion_sugerida",
                "source_url",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "prioridad": "A",
                "institucion": "Test Lab",
                "tipo": "lab",
                "region_ciudad": "X",
                "contact_email": "seen@lab.cl",
                "fit_signal": "fit",
                "linea_origenlab_sugerida": "micro",
                "accion_sugerida": "send",
                "source_url": "https://example.com",
            }
        )
    (tmp_path / "origenlab_relevant_tenders_20260518.csv").write_text(
        "codigo_licitacion,comprador,titulo,fecha_cierre,score,senales,accion_sugerida\n",
        encoding="utf-8",
    )
    (tmp_path / "origenlab_buyer_accounts_from_tenders_20260518.csv").write_text(
        "comprador,codigos,titulos_ejemplo,proximo_cierre,linea_origenlab_sugerida,senales,prioridad,licitaciones_relevantes\n",
        encoding="utf-8",
    )
    dnr = tmp_path / "do_not_repeat_master.csv"
    with dnr.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["email_norm"])
        w.writeheader()
        w.writerow({"email_norm": "seen@lab.cl"})
    for name in ("outreach_contacted_all.csv",):
        (tmp_path / name).write_text("email_norm\n", encoding="utf-8")
    (tmp_path.parent / "all_known_marketing_contacts_dedup.csv").write_text(
        "email_norm\n", encoding="utf-8"
    )
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE outreach_contact_state (contact_email_norm TEXT, state TEXT)"
    )
    conn.execute("CREATE TABLE emails (id INTEGER, date_iso TEXT, recipients TEXT, source_file TEXT)")
    conn.commit()
    conn.close()

    checker = mod.CrossChecker(db, reports_dir=tmp_path)
    rows = mod.build_rows(checker, reports_dir=tmp_path)
    assert len(rows) == 1
    assert rows[0]["current_status"] == "do_not_contact"
    assert rows[0]["ab_queue"] == ""
