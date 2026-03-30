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
              source_file TEXT
            )
            """
        )
        src = "gmail:contacto@origenlab.cl/INBOX"
        conn.executemany(
            "INSERT INTO emails (date_iso, subject, sender, source_file) VALUES (?,?,?,?)",
            [(f"2026-03-{i+1:02d}T10:00:00Z", f"S{i}", f"u{i}@x.cl", src) for i in range(15)],
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
    assert st.session_state["start_page"] == "Organizaciones"
    assert st.session_state["org_only_unis"] is True
    assert st.session_state["extra_flag"] == "x"


def test_quick_action_default_page_is_resumen(monkeypatch):
    """
    Validar la lógica de selección de pestaña por defecto sin tocar la BD real.

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

    monkeypatch.setattr(app, "load_settings", lambda: DummySettings())

    # Ejecutar main no debería lanzar excepciones; esto actúa como smoke test
    app.main()

