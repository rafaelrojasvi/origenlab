"""lead_contact_research: validation, upsert, archive hint, RW flag."""

from __future__ import annotations

import sqlite3

import pytest

from origenlab_email_pipeline.business_mart_schema import BUSINESS_MART_SCHEMA_SQL
from origenlab_email_pipeline.lead_contact_research import (
    CONTACT_RESEARCH_STATUSES,
    archive_org_hint_for_domain,
    delete_contact_research,
    fetch_contact_research_row,
    streamlit_leads_review_rw_enabled,
    upsert_contact_research,
    validate_contact_research_payload,
)
from origenlab_email_pipeline.leads_schema import ensure_leads_tables_ddl_base, finalize_lead_master_source_keys


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _minimal(conn: sqlite3.Connection) -> None:
    ensure_leads_tables_ddl_base(conn)
    finalize_lead_master_source_keys(conn)
    conn.execute(
        """
        INSERT INTO lead_master (id, source_name, source_record_id, org_name)
        VALUES (1, 's', 'r1', 'Org A')
        """
    )
    conn.commit()


def test_contact_research_status_constants() -> None:
    assert "nuevo" in CONTACT_RESEARCH_STATUSES
    assert "listo_para_contacto" in CONTACT_RESEARCH_STATUSES


def test_validate_rejects_bad_status() -> None:
    with pytest.raises(ValueError, match="Estado"):
        validate_contact_research_payload(
            contact_research_status="vacio",
            resolved_domain=None,
            resolved_contact_name=None,
            resolved_contact_email=None,
            contact_source=None,
            contact_research_notes="x",
            updated_by=None,
        )


def test_validate_nuevo_requires_some_content() -> None:
    with pytest.raises(ValueError, match="nada que guardar"):
        validate_contact_research_payload(
            contact_research_status="nuevo",
            resolved_domain=None,
            resolved_contact_name=None,
            resolved_contact_email=None,
            contact_source=None,
            contact_research_notes=None,
            updated_by=None,
        )


def test_validate_descartado_allows_empty_payload() -> None:
    p = validate_contact_research_payload(
        contact_research_status="descartado",
        resolved_domain=None,
        resolved_contact_name=None,
        resolved_contact_email=None,
        contact_source=None,
        contact_research_notes=None,
        updated_by=None,
    )
    assert p.contact_research_status == "descartado"


def test_validate_normalizes_domain_email() -> None:
    p = validate_contact_research_payload(
        contact_research_status="contacto_encontrado",
        resolved_domain="WWW.EXAMPLE.GOB.CL",
        resolved_contact_name="  Ana Pérez  ",
        resolved_contact_email="Ana.Perez@EXAMPLE.GOB.CL",
        contact_source="  web  ",
        contact_research_notes="ok",
        updated_by="t1",
    )
    assert p.resolved_domain == "example.gob.cl"
    assert p.resolved_contact_email == "ana.perez@example.gob.cl"
    assert p.resolved_contact_name == "Ana Pérez"


def test_validate_rejects_bad_email() -> None:
    with pytest.raises(ValueError, match="Correo"):
        validate_contact_research_payload(
            contact_research_status="investigar_contacto",
            resolved_domain=None,
            resolved_contact_name=None,
            resolved_contact_email="not-an-email",
            contact_source=None,
            contact_research_notes="x",
            updated_by=None,
        )


def test_upsert_fetch_delete_roundtrip() -> None:
    conn = _conn()
    _minimal(conn)
    p = validate_contact_research_payload(
        contact_research_status="listo_para_contacto",
        resolved_domain="x.cl",
        resolved_contact_name="C",
        resolved_contact_email="c@x.cl",
        contact_source="manual",
        contact_research_notes="n",
        updated_by="op",
    )
    upsert_contact_research(conn, lead_id=1, payload=p, at_iso="2026-01-01T00:00:00Z")
    conn.commit()
    got = fetch_contact_research_row(conn, 1)
    assert got is not None
    assert got["resolved_domain"] == "x.cl"
    assert got["contact_research_status"] == "listo_para_contacto"
    delete_contact_research(conn, 1)
    conn.commit()
    assert fetch_contact_research_row(conn, 1) is None


def test_archive_org_hint() -> None:
    conn = _conn()
    conn.executescript(BUSINESS_MART_SCHEMA_SQL)
    conn.execute(
        """
        INSERT INTO organization_master (
          domain, organization_name_guess, total_emails, total_contacts
        ) VALUES ('lab.cl', 'Lab', 9, 2)
        """
    )
    conn.commit()
    name, n = archive_org_hint_for_domain(conn, "lab.cl")
    assert name == "Lab"
    assert n == 9
    assert archive_org_hint_for_domain(conn, "missing.cl") == (None, None)


def test_fetch_contact_research_row_missing_table_returns_none() -> None:
    conn = _conn()
    _minimal(conn)
    # Table lead_contact_research not created (DDL not run).
    assert fetch_contact_research_row(conn, 1) is None


def test_streamlit_rw_flag_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_STREAMLIT_LEADS_REVIEW_RW", raising=False)
    assert streamlit_leads_review_rw_enabled() is False
    monkeypatch.setenv("ORIGENLAB_STREAMLIT_LEADS_REVIEW_RW", "1")
    assert streamlit_leads_review_rw_enabled() is True
    monkeypatch.setenv("ORIGENLAB_STREAMLIT_LEADS_REVIEW_RW", "0")
    assert streamlit_leads_review_rw_enabled() is False
