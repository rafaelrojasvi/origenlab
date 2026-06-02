from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
import streamlit as st


def _load_app_module():
    """Cargar apps/business_mart_app.py como módulo sin requerir paquete apps."""
    root = Path(__file__).resolve().parents[1]
    app_path = root / "apps" / "business_mart_app.py"
    spec = importlib.util.spec_from_file_location("business_mart_app", app_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    return module


app = _load_app_module()
APP_SOURCE = (Path(__file__).resolve().parents[1] / "apps" / "business_mart_app.py").read_text(encoding="utf-8")


def test_sidebar_includes_clasificacion_comercial() -> None:
    assert "Clasificación comercial" in APP_SOURCE
    assert "render_clasificacion_comercial_page" in APP_SOURCE
    assert "PRIMARY_SIDEBAR_PAGES" in APP_SOURCE


def test_sidebar_api_preview_wired_when_enabled() -> None:
    assert "primary_sidebar_pages" in APP_SOURCE
    assert "render_api_preview_page" in APP_SOURCE
    assert 'page == "API preview"' in APP_SOURCE
    from origenlab_email_pipeline.streamlit_api_preview import primary_sidebar_pages

    base = ["Inicio", "Outbound / No repetir"]
    assert "API preview" not in primary_sidebar_pages(base)


def test_inicio_uses_canonical_operational_kpis_not_full_mart_headline() -> None:
    assert "Contactos operativos Gmail" in APP_SOURCE
    assert "Mart completo / histórico" in APP_SOURCE
    assert 'render_kpi_metric("Contactos (mart)"' not in APP_SOURCE
    assert "canonical_only=True" in APP_SOURCE
    assert "Atajos exploratorios (mart)" not in APP_SOURCE


def test_sidebar_api_preview_appears_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8001")
    from origenlab_email_pipeline.streamlit_api_preview import primary_sidebar_pages

    assert "API preview" in primary_sidebar_pages(["Inicio"])


def test_date_prefix_and_days_since_helpers():
    assert app._date_prefix_for_compare("2026-03-29T12:00:00Z") == "2026-03-29"
    assert app._date_prefix_for_compare(None) is None
    assert app._date_prefix_for_compare("") is None
    d = app._days_since_iso_prefix("2026-03-29")
    assert d is not None and d >= 0


def test_where_contacto_gmail_source_uses_expected_pattern() -> None:
    assert "gmail:contacto@origenlab.cl" in app._where_contacto_gmail_source()
    assert "e.source_file" in app._where_contacto_gmail_source(table_alias="e")


def test_load_contacto_gmail_activity_summary_counts_gmail_contacto(tmp_path: Path) -> None:
    db_path = tmp_path / "cg.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE emails (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date_iso TEXT,
              subject TEXT,
              sender TEXT,
              source_file TEXT
            )
            """
        )
        src = "gmail:contacto@origenlab.cl/INBOX"
        conn.executemany(
            "INSERT INTO emails (date_iso, subject, sender, source_file) VALUES (?,?,?,?)",
            [
                ("2026-03-20T10:00:00Z", "A", "a@x.cl", src),
                ("2026-03-28T10:00:00Z", "B", "b@y.cl", src),
                ("2033-01-01T00:00:00Z", "Future", "c@z.cl", src),
                ("2026-01-01T00:00:00Z", "Imap", "d@z.cl", "imap:contacto@origenlab.cl/INBOX"),
            ],
        )
        conn.commit()
        s = app.load_contacto_gmail_activity_summary(conn, slack_days=2)
        assert s.total_rows == 3
        assert s.most_recent_plausible_iso is not None
        assert "2033" not in s.most_recent_plausible_iso
        assert s.count_7d <= s.count_30d <= s.count_90d <= s.total_rows
    finally:
        conn.close()


def test_load_contacto_gmail_recent_emails_df_respects_limit(tmp_path: Path) -> None:
    db_path = tmp_path / "cg2.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE emails (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date_iso TEXT,
              subject TEXT,
              sender TEXT,
              folder TEXT,
              attachment_count INTEGER,
              body TEXT,
              full_body_clean TEXT,
              top_reply_clean TEXT,
              source_file TEXT
            )
            """
        )
        src = "gmail:contacto@origenlab.cl/INBOX"
        conn.executemany(
            "INSERT INTO emails (date_iso, subject, sender, folder, attachment_count, source_file) VALUES (?,?,?,?,?,?)",
            [(f"2026-03-{i+1:02d}T10:00:00Z", f"S{i}", f"u{i}@x.cl", "INBOX", 0, src) for i in range(15)],
        )
        conn.commit()
        df = app.load_contacto_gmail_recent_emails_df(conn, limit=5)
        assert len(df) == 5
    finally:
        conn.close()


def test_load_email_date_health_excludes_future_dated_from_plausible_max(tmp_path: Path) -> None:
    db_path = tmp_path / "e.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE emails (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date_iso TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO emails (date_iso) VALUES (?)",
            [
                ("2001-01-03T21:35:47+00:00",),
                ("2024-06-01T10:00:00Z",),
                ("2033-06-09T15:09:53+01:00",),
            ],
        )
        conn.commit()
        h = app.load_email_date_health(conn, slack_days=2)
        assert h.future_dated_count >= 1
        assert h.raw_max is not None and "2033" in h.raw_max
        assert h.plausible_max_date_iso is not None
        assert "2033" not in h.plausible_max_date_iso
        assert "2024" in h.plausible_max_date_iso or "2001" in h.plausible_max_date_iso
    finally:
        conn.close()


def test_load_email_date_health_emails_extra_where_limits_to_canonical(tmp_path: Path) -> None:
    from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source

    db_path = tmp_path / "e2.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE emails (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date_iso TEXT,
              source_file TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO emails (date_iso, source_file) VALUES (?, ?)",
            [
                ("2024-06-01T10:00:00Z", "gmail:contacto@origenlab.cl/INBOX"),
                ("2033-06-09T15:09:53+01:00", "/mbox/contacto@labdelivery.cl/x/mbox"),
            ],
        )
        conn.commit()
        pred = sql_predicate_contacto_gmail_source()
        h = app.load_email_date_health(conn, slack_days=2, emails_extra_where=pred)
        assert h.raw_max is not None and "2033" not in h.raw_max
        assert h.plausible_max_date_iso is not None and "2024" in h.plausible_max_date_iso
    finally:
        conn.close()


def test_friendly_org_type_labels_in_spanish():
    assert "Educación" in app._friendly_org_type("education")
    assert "Empresa" in app._friendly_org_type("business")
    assert "Gobierno" in app._friendly_org_type("gov")
    assert "personal" in app._friendly_org_type("personal")
    assert app._friendly_org_type(None) == "Sin clasificar"


def test_friendly_doc_type_labels_in_spanish():
    assert app._friendly_doc_type("quote") == "Cotización"
    assert app._friendly_doc_type("invoice") == "Factura"
    assert "Lista de precios" in app._friendly_doc_type("price_list")
    assert "Orden de compra" in app._friendly_doc_type("purchase_order")
    # Código desconocido cae en etiqueta genérica
    assert app._friendly_doc_type("something_else") == "Otro documento"


def test_signal_label_returns_business_friendly_spanish():
    label, desc = app._signal_label("quote_email_plus_quote_doc")
    assert "Cotización" in label
    assert "cotización repetidos" in desc

    label, desc = app._signal_label("education_with_quote_activity")
    assert "Universidad" in label
    assert "educación" in desc

    label, desc = app._signal_label("dormant_contact")
    assert "Cuenta dormida" in label
    assert "alto historial" in desc

    # Señal desconocida devuelve el código original pero con descripción genérica
    code = "unknown_signal_code"
    label, desc = app._signal_label(code)
    assert label == code
    assert "Señal heurística" in desc


def test_fmt_marketing_variant_labels() -> None:
    from origenlab_email_pipeline.tatiana_copilot.borrador_support import fmt_marketing_variant
    from origenlab_email_pipeline.tatiana_copilot.marketing_outreach import (
        MARKETING_VARIANT_FOLLOWUP,
        MARKETING_VARIANT_GENERAL,
        MARKETING_VARIANT_UNIVERSIDADES,
    )

    assert "Presentacion" in fmt_marketing_variant(MARKETING_VARIANT_GENERAL)
    assert "Universidades" in fmt_marketing_variant(MARKETING_VARIANT_UNIVERSIDADES)
    assert "Follow-up" in fmt_marketing_variant(MARKETING_VARIANT_FOLLOWUP)


def test_load_existing_pilot_batch_reads_csv_and_case_json(tmp_path: Path) -> None:
    from origenlab_email_pipeline.tatiana_copilot.borrador_support import load_existing_pilot_batch

    batch = tmp_path / "pilot_batch"
    batch.mkdir()
    (batch / "pilot_review.csv").write_text(
        "case_id,subject_input,generated_subject\nc1,Subj,Gen\n",
        encoding="utf-8",
    )
    (batch / "case_c1.json").write_text(
        '{"case":{"case_id":"c1","subject":"Subj"},"generated_draft":"Hola","prompt_blocks":{}}',
        encoding="utf-8",
    )
    df, cases, err = load_existing_pilot_batch(str(batch))
    assert err is None
    assert df is not None
    assert len(df) == 1
    assert cases is not None
    assert len(cases) == 1
    assert cases[0]["case"]["case_id"] == "c1"


def test_load_existing_pilot_batch_orders_cases_like_csv_not_glob(tmp_path: Path) -> None:
    """Filenames sort as c1 before c2, but CSV lists c2 first — cases must follow CSV."""
    from origenlab_email_pipeline.tatiana_copilot.borrador_support import load_existing_pilot_batch

    batch = tmp_path / "pilot_batch_order"
    batch.mkdir()
    (batch / "pilot_review.csv").write_text(
        "case_id,subject_input,generated_subject\n"
        "c2,Second,Gen2\n"
        "c1,First,Gen1\n",
        encoding="utf-8",
    )
    (batch / "case_c1.json").write_text(
        '{"case":{"case_id":"c1","subject":"First"},"generated_draft":"A","prompt_blocks":{}}',
        encoding="utf-8",
    )
    (batch / "case_c2.json").write_text(
        '{"case":{"case_id":"c2","subject":"Second"},"generated_draft":"B","prompt_blocks":{}}',
        encoding="utf-8",
    )
    _df, cases, err = load_existing_pilot_batch(str(batch))
    assert err is None
    assert cases is not None
    assert len(cases) == 2
    assert [cases[i]["case"]["case_id"] for i in range(2)] == ["c2", "c1"]


def test_page_status_values_cover_key_client_pages() -> None:
    from origenlab_email_pipeline.streamlit_page_status import PAGE_STATUS_PRESETS, page_status_values

    expected_pages = {
        "Inicio",
        "Seguimientos y casos",
        "Contactos y organizaciones",
        "Outbound / No repetir",
        "Histórico / Archivo legacy",
        "Herramientas / Runbook",
        "Salud de datos",
        "Actividad contacto Gmail",
        "Casos para revisar",
        "Cola outreach marketing",
        "Borrador comercial",
        "Qué hacer hoy",
        "Leads y cuentas",
        "Proveedores",
        "Candidatos comerciales",
        "Oportunidades",
        "API preview",
    }
    assert expected_pages.issubset(set(PAGE_STATUS_PRESETS.keys()))
    for page in expected_pages:
        values = page_status_values(page)
        assert values["source"]
        assert values["freshness"]


def test_client_clarity_copy_mentions_are_present_in_source() -> None:
    prior_src = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "origenlab_email_pipeline"
        / "streamlit_prioridad_pages.py"
    ).read_text(encoding="utf-8")
    assert "Cada tarjeta viene de **una** cola SQL distinta" in prior_src
    assert "### Revisar borradores guardados" in prior_src
    assert "### Crear nuevo borrador" in prior_src


def test_navigate_to_sets_session_state_and_calls_rerun(monkeypatch):
    # Asegurar un session_state limpio para el test
    st.session_state.clear()

    called = {"rerun": False}

    def fake_rerun() -> None:
        called["rerun"] = True

    # Sustituimos st.rerun por una función que marque la llamada
    monkeypatch.setattr(app.st, "rerun", fake_rerun, raising=False)

    app._navigate_to("Organizaciones", org_only_unis=True, extra_flag="x")

    assert called["rerun"] is True
    assert st.session_state["start_page"] == "Contactos y organizaciones"
    assert st.session_state.get("coy_inner") == "Organizaciones"
    assert st.session_state["org_only_unis"] is True
    assert st.session_state["extra_flag"] == "x"


def test_quick_action_main_smoke_default_inicio(monkeypatch):
    """
    Validar que ``main()`` no falle en el arranque por defecto (Inicio) sin BD real.

    Emulamos un entorno mínimo donde:
    - _connect_ro devuelve un objeto con los métodos usados.
    - _has_table siempre devuelve True para evitar mensajes de error técnicos.
    - _load_df devuelve dataframes pequeños y controlados.
    """

    class DummyConn:
        def close(self) -> None:
            pass

    # Forzar que no falle la comprobación de tablas
    monkeypatch.setattr(app, "_connect_ro", lambda _: DummyConn())
    monkeypatch.setattr(app, "_has_table", lambda _conn, _name: True)

    def fake_load_df(_conn, sql: str, params: tuple = ()) -> pd.DataFrame:  # type: ignore[override]
        # Devolvemos el mínimo necesario según la consulta.
        if "FROM emails" in sql and "COUNT(*)" in sql:
            return pd.DataFrame([{"c": 10}])
        if "FROM contact_master" in sql and "COUNT(*)" in sql:
            return pd.DataFrame([{"c": 5}])
        if "FROM organization_master" in sql and "COUNT(*)" in sql:
            return pd.DataFrame([{"c": 3}])
        if "FROM document_master" in sql and "sender_domain, doc_type" in sql:
            return pd.DataFrame(columns=["sender_domain", "doc_type"])
        if "FROM document_master" in sql and "COUNT(*)" in sql:
            return pd.DataFrame([{"c": 4}])
        if "MIN(date_iso)" in sql:
            return pd.DataFrame([{"primera": "2020-01-01", "ultima": "2024-12-31"}])
        # Tablas resumen simples
        if "FROM organization_master" in sql:
            return pd.DataFrame(
                [
                    {
                        "dominio": "example.com",
                        "organizacion": "Example",
                        "tipo_org": "education",
                        "primera": "2020-01-01",
                        "ultima": "2024-12-31",
                        "total": 10,
                        "contactos": 3,
                        "cotiz_email": 2,
                        "cotiz_docs": 1,
                        "factura_email": 1,
                        "factura_docs": 0,
                        "compra_email": 0,
                        "doc_emails": 1,
                    }
                ]
            )
        # Por defecto, un df vacío no rompe la app
        return pd.DataFrame()

    monkeypatch.setattr(app, "_load_df", fake_load_df)

    # Stub muy simple de load_settings.resolved_sqlite_path para evitar dependencias externas.
    class DummySettings:
        def resolved_sqlite_path(self):
            return "/tmp/dummy.sqlite"

        def resolved_reports_dir(self):
            from pathlib import Path

            return Path("/tmp")

    monkeypatch.setattr(app, "load_settings", lambda: DummySettings())
    monkeypatch.setattr(
        app,
        "load_contacto_gmail_activity_summary",
        lambda conn, slack_days=2: app.ContactoGmailActivitySummary(10, 1, 2, 3, "2024-06-01T00:00:00Z"),
    )
    monkeypatch.setattr(app, "count_canonical_sent_inbox", lambda _c: (3, 2))
    monkeypatch.setattr(app, "count_canonical_operational_contacts", lambda _c: 5)
    monkeypatch.setattr(app, "count_canonical_operational_organizations", lambda _c: 3)
    monkeypatch.setattr(app, "count_canonical_operational_opportunity_signals", lambda _c: 2)
    monkeypatch.setattr(app, "count_canonical_unique_external_senders", lambda _c: 4)
    monkeypatch.setattr(app, "count_archive_mart_table", lambda _c, _t: 100)
    monkeypatch.setattr(app, "count_canonical_duplicate_message_id_groups", lambda _c: 0)
    monkeypatch.setattr(app, "count_canonical_missing_message_id", lambda _c: 0)
    monkeypatch.setattr(app, "count_canonical_missing_date_iso", lambda _c: 0)
    monkeypatch.setattr(app, "count_canonical_attachments", lambda _c: 0)
    monkeypatch.setattr(app, "count_canonical_empty_body", lambda _c: 0)
    monkeypatch.setattr(app, "load_inicio_recent_canonical_rows", lambda *_a, **_k: [])

    monkeypatch.setattr(
        "origenlab_email_pipeline.read.today_workspace.gather_today_workspace_rows",
        lambda *_a, **_k: [],
    )

    from origenlab_email_pipeline.outbound_readiness_check import OutboundReadinessReport

    def fake_assess(*_a, **_k):
        return OutboundReadinessReport(
            verdict="ready",
            sqlite_path="/tmp/dummy.sqlite",
            sqlite_exists=True,
            sqlite_read_only=True,
        )

    monkeypatch.setattr(app, "assess_outbound_readiness", fake_assess)
    monkeypatch.setattr(app, "_safe_count", lambda _c, _t: 7)

    # Ejecutar main no debería lanzar excepciones; esto actúa como smoke test
    app.main()

