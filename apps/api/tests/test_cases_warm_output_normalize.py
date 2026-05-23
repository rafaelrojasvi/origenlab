"""Warm-case response normalization (audit-driven, read-only)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.main import create_app
from origenlab_api.services.warm_case_output_normalize import (
    is_auto_reply_subject,
    normalize_warm_case_item,
    resolve_normalized_category,
)
from origenlab_api.schemas.cases import WarmCaseItem
from origenlab_api.settings import Settings

_CONTACTO_INBOX = "gmail:contacto@origenlab.cl/INBOX"
_CONTACTO_SENT = "gmail:contacto@origenlab.cl/[Gmail]/Enviados"


def _item(
    *,
    contact_email: str,
    subject: str,
    category: str = "client_reply",
) -> WarmCaseItem:
    return WarmCaseItem(
        case_id="gmail-contacto-1",
        last_email_id=1,
        last_seen_at="2026-05-22T10:00:00-04:00",
        account_name="Test",
        contact_email=contact_email,
        subject=subject,
        category=category,  # type: ignore[arg-type]
        status="new",
        next_action="old",
        equipment_signal="",
        snippet="",
        gmail_url=None,
    )


def test_auto_reply_subject_detection() -> None:
    assert is_auto_reply_subject("Automatic reply: Quotation Request")
    assert is_auto_reply_subject("Out of office until Monday")


def test_normalize_dhl_vendor_logistics() -> None:
    raw = _item(contact_email="monica.silva@dhl.com", subject="PROPUESTA COMERCIAL DHL")
    out = normalize_warm_case_item(raw)
    assert out is not None
    assert out.category == "vendor_logistics"
    assert out.category != "client_reply"
    assert "logística" in out.next_action.lower()


def test_normalize_dlab_supplier() -> None:
    raw = _item(contact_email="chloe.yang@dlabsci.com", subject="DLAB visit reply")
    out = normalize_warm_case_item(raw)
    assert out is not None
    assert out.category == "supplier_reply"
    assert "proveedor" in out.next_action.lower()


def test_normalize_crtopmachine_supplier() -> None:
    raw = _item(contact_email="ariel@crtopmachine.com", subject="Re: reactor inquiry")
    assert resolve_normalized_category(raw) == "supplier_reply"


def test_normalize_asynt_supplier() -> None:
    raw = _item(contact_email="sales@asynt.com", subject="Re: reactor specs")
    assert resolve_normalized_category(raw) == "supplier_reply"


def test_normalize_serva_auto_reply_hidden_by_default() -> None:
    raw = _item(
        contact_email="order@serva.de",
        subject="Automatic reply: Quotation Request",
        category="supplier_reply",
    )
    assert normalize_warm_case_item(raw, include_noise=False) is None
    shown = normalize_warm_case_item(raw, include_noise=True)
    assert shown is not None
    assert shown.category == "auto_reply"


def test_normalize_banco_payment_admin() -> None:
    raw = _item(contact_email="x@bancochile.cl", subject="FACTURA 6")
    out = normalize_warm_case_item(raw)
    assert out is not None
    assert out.category == "payment_admin"
    assert "pago" in out.next_action.lower()


def test_normalize_ollital_and_ortoalresa_stay_supplier() -> None:
    oll = _item(contact_email="kelly@ollital.com", subject="Re: Ollital reactor 5L")
    out = normalize_warm_case_item(oll)
    assert out is not None
    assert out.category == "supplier_reply"

    orto = _item(
        contact_email="carmen.llorente@ortoalresa.com",
        subject="RE: Cotizar Centrifuga",
        category="supplier_reply",
    )
    assert normalize_warm_case_item(orto) is not None
    assert normalize_warm_case_item(orto).category == "supplier_reply"


def test_quote_sent_preserved_for_outbound_customer_thread() -> None:
    raw = _item(
        contact_email="contacto@origenlab.cl",
        subject="Re: Solicitud de cotización",
        category="quote_sent",
    )
    out = normalize_warm_case_item(raw)
    assert out is not None
    assert out.category == "quote_sent"


def _warm_client(tmp_path: Path, rows: list[tuple]) -> TestClient:
    db = tmp_path / "t.sqlite"
    active = tmp_path / "current"
    active.mkdir(parents=True)
    (active / "manifest.json").write_text(
        json.dumps({"canonical_files": [], "campaign_mode": "equipment_first"}),
        encoding="utf-8",
    )
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            date_iso TEXT,
            source_file TEXT,
            folder TEXT,
            sender TEXT,
            subject TEXT
        )
        """
    )
    for row in rows:
        conn.execute(
            "INSERT INTO emails (date_iso, source_file, folder, sender, subject) VALUES (?, ?, ?, ?, ?)",
            row,
        )
    conn.commit()
    conn.close()
    app = create_app()
    from origenlab_api.settings import get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(
        sqlite_path=db,
        active_current=active,
    )
    return TestClient(app)


def test_cases_warm_api_normalizes_audit_samples(tmp_path: Path) -> None:
    rows = [
        (
            "2026-05-22T16:09:00-04:00",
            _CONTACTO_INBOX,
            "INBOX",
            "Monica Silva <monica.silva@dhl.com>",
            "PROPUESTA COMERCIAL DHL",
        ),
        (
            "2026-05-22T16:31:00-04:00",
            _CONTACTO_INBOX,
            "INBOX",
            "chloe.yang@dlabsci.com",
            "DLAB catalogue visit",
        ),
        (
            "2026-05-22T15:47:00-04:00",
            _CONTACTO_INBOX,
            "INBOX",
            "Serva_Order <order@serva.de>",
            "Automatic reply: Quotation Request",
        ),
        (
            "2026-05-22T11:34:00-04:00",
            _CONTACTO_INBOX,
            "INBOX",
            "serviciodetransferencias@bancochile.cl",
            "FACTURA 6",
        ),
        (
            "2026-05-22T22:14:00-04:00",
            _CONTACTO_INBOX,
            "INBOX",
            "Kelly <kelly@ollital.com>",
            "Re: Ollital reactor 5L",
        ),
        (
            "2026-05-20T18:19:00-04:00",
            _CONTACTO_INBOX,
            "INBOX",
            "Carmen Llorente <carmen.llorente@ortoalresa.com>",
            "RE: Cotizar Centrifuga",
        ),
        (
            "2026-05-20T16:14:00-04:00",
            _CONTACTO_SENT,
            "[Gmail]/Enviados",
            "contacto@origenlab.cl",
            "Re: Solicitud de cotización Virbac",
        ),
    ]
    client = _warm_client(tmp_path, rows)
    data = client.get("/cases/warm?positive_signal_only=false&limit=50").json()
    by_email = {i["contact_email"].lower(): i for i in data["items"]}

    assert by_email["monica.silva@dhl.com"]["category"] == "vendor_logistics"
    assert by_email["chloe.yang@dlabsci.com"]["category"] == "supplier_reply"
    assert "order@serva.de" not in by_email
    assert by_email["serviciodetransferencias@bancochile.cl"]["category"] == "payment_admin"
    assert by_email["kelly@ollital.com"]["category"] == "supplier_reply"
    assert by_email["carmen.llorente@ortoalresa.com"]["category"] == "supplier_reply"
    assert by_email["contacto@origenlab.cl"]["category"] == "quote_sent"
