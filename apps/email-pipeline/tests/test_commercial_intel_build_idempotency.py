from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from origenlab_email_pipeline.db import connect, insert_email
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema


def _load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    return module


@pytest.fixture()
def seeded_db(tmp_path: Path) -> Path:
    db = tmp_path / "emails.sqlite"
    conn = connect(db)
    try:
        migrate_sqlite_schema(
            conn,
            layers={SchemaLayer.ARCHIVE_AND_MART, SchemaLayer.COMMERCIAL_INTEL},
        )
        insert_email(
            conn,
            source_file="gmail:contacto@origenlab.cl/INBOX",
            folder="INBOX",
            message_id="<1@test>",
            subject="Cotizacion microscopio para laboratorio",
            sender="Lab Demo <compras@labdemo.cl>",
            recipients="contacto@origenlab.cl",
            date_raw="",
            date_iso="2026-03-25T10:00:00Z",
            body="",
            body_html="",
            body_text_raw="Necesitamos cotizacion de microscopio.",
            body_text_clean="Necesitamos cotizacion de microscopio.",
            body_source_type="plain",
            body_has_plain=True,
            body_has_html=False,
            full_body_clean="Necesitamos cotizacion de microscopio.",
            top_reply_clean="Necesitamos cotizacion de microscopio.",
            attachment_count=0,
            has_attachments=False,
        )
        insert_email(
            conn,
            source_file="gmail:contacto@origenlab.cl/INBOX",
            folder="INBOX",
            message_id="<2@test>",
            subject="Factura y despacho",
            sender="Proveedor Demo <ventas@supplier.cl>",
            recipients="contacto@origenlab.cl",
            date_raw="",
            date_iso="2026-03-25T11:00:00Z",
            body="",
            body_html="",
            body_text_raw="Factura pendiente con despacho.",
            body_text_clean="Factura pendiente con despacho.",
            body_source_type="plain",
            body_has_plain=True,
            body_has_html=False,
            full_body_clean="Factura pendiente con despacho.",
            top_reply_clean="Factura pendiente con despacho.",
            attachment_count=0,
            has_attachments=False,
        )
        conn.commit()
    finally:
        conn.close()
    return db


def test_build_script_is_idempotent_for_counts(
    seeded_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    mod = _load_script(
        repo_root / "scripts" / "commercial" / "build_commercial_intel_v1.py",
        "build_commercial_intel_v1_mod",
    )
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(seeded_db))
    monkeypatch.setenv("ORIGENLAB_GMAIL_WORKSPACE_USER", "contacto@origenlab.cl")

    monkeypatch.setattr(mod.sys, "argv", ["build_commercial_intel_v1.py", "--rebuild"])
    rc = mod.main()
    assert rc == 0

    conn = connect(seeded_db)
    try:
        first = {
            "facts": conn.execute("SELECT COUNT(*) FROM commercial_email_signal_fact").fetchone()[0],
            "org": conn.execute("SELECT COUNT(*) FROM organization_candidate").fetchone()[0],
            "contact": conn.execute("SELECT COUNT(*) FROM contact_candidate").fetchone()[0],
            "opp": conn.execute("SELECT COUNT(*) FROM opportunity_candidate").fetchone()[0],
        }
    finally:
        conn.close()

    monkeypatch.setattr(mod.sys, "argv", ["build_commercial_intel_v1.py"])
    rc2 = mod.main()
    assert rc2 == 0

    conn2 = connect(seeded_db)
    try:
        second = {
            "facts": conn2.execute("SELECT COUNT(*) FROM commercial_email_signal_fact").fetchone()[0],
            "org": conn2.execute("SELECT COUNT(*) FROM organization_candidate").fetchone()[0],
            "contact": conn2.execute("SELECT COUNT(*) FROM contact_candidate").fetchone()[0],
            "opp": conn2.execute("SELECT COUNT(*) FROM opportunity_candidate").fetchone()[0],
        }
    finally:
        conn2.close()
    assert first == second

