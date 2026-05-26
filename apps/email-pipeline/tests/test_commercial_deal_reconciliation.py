"""Reconciliation and redaction tests for SERVA/CEAF commercial deal preview."""

from __future__ import annotations

import json
from decimal import Decimal

from origenlab_email_pipeline.commercial.deal_field_parsers import (
    chilean_iva_gross_from_net,
    reconcile_supplier_payment_excluding_freight,
)
from origenlab_email_pipeline.commercial.deal_preview_redaction import (
    public_preview_must_not_contain,
    redact_preview_for_public,
)
from origenlab_email_pipeline.commercial.serva_ceaf_deal_confirmed import (
    CLIENT_PAYMENT_RECEIVED_CLP,
    build_confirmed_events,
    build_confirmed_fields,
)
from origenlab_email_pipeline.commercial.serva_ceaf_deal_preview import (
    build_serva_ceaf_deal_preview,
    connect_sqlite_readonly,
)
from test_serva_ceaf_deal_preview import _seed_deal_db


def test_chilean_iva_net_times_119_equals_gross() -> None:
    assert chilean_iva_gross_from_net(1_260_000, Decimal("0.19")) == 1_499_400


def test_proforma_minus_freight_reconciles_wise_payment() -> None:
    rec = reconcile_supplier_payment_excluding_freight(
        invoice_total_eur=Decimal("363.00"),
        freight_quoted_eur=Decimal("145.00"),
        amount_paid_eur=Decimal("218.00"),
    )
    assert rec["reconciliation_status"] == "reconciled_excluding_supplier_freight"
    assert rec["freight_excluded_from_wire"] is True
    assert rec["expected_payment_excluding_freight_eur"] == "218.00"
    assert "mismatch" not in str(rec["note"]).lower()


def test_client_payment_received_clp_operator_confirmed() -> None:
    fields = build_confirmed_fields()
    pay = fields["client_payment_received_clp"]
    assert pay["value"] == CLIENT_PAYMENT_RECEIVED_CLP
    assert pay["currency"] == "CLP"
    assert pay["confidence"] == "operator_confirmed"
    assert pay["needs_review"] is False
    events = build_confirmed_events()
    client_pay = [e for e in events if e["event_type"] == "client_payment_received"]
    assert len(client_pay) == 1
    assert client_pay[0]["amount_gross_clp"] == CLIENT_PAYMENT_RECEIVED_CLP
    assert client_pay[0]["amount_net_clp"] == 1_260_000
    assert client_pay[0]["subject"] == "FACTURA 6"


def test_gross_margin_still_needs_review(tmp_path) -> None:
    db = tmp_path / "emails.sqlite"
    _seed_deal_db(db)
    conn = connect_sqlite_readonly(db)
    try:
        preview = build_serva_ceaf_deal_preview(conn)
    finally:
        conn.close()
    margin = preview["gross_margin"]
    assert margin["status"] == "needs_review"
    assert margin["basis"] == "client_sale_amount_net_clp_ex_vat"
    assert margin["client_sale_amount_net_clp"] == 1_260_000
    assert "wise" in margin["reason"].lower()
    assert "dhl" in margin["reason"].lower() or "logistics" in margin["reason"].lower()
    assert preview["client_vat_breakdown"]["gross_from_net_formula_check"] is True


def test_public_export_redacts_sensitive_payment_and_ids(tmp_path) -> None:
    db = tmp_path / "emails.sqlite"
    _seed_deal_db(db)
    conn = connect_sqlite_readonly(db)
    try:
        preview = build_serva_ceaf_deal_preview(conn)
    finally:
        conn.close()

    public = preview["public_export"]
    blob = json.dumps(public, ensure_ascii=False)
    violations = public_preview_must_not_contain(blob)
    assert violations == [], f"public export still contains: {violations}"
    assert "INT_EMP" not in blob
    assert "2152655677" not in blob
    pf = public["fields"]
    assert pf["client_sale_amount_net_clp"]["value"] in (1_260_000, "1260000")
    assert pf["client_sale_amount_gross_clp"]["value"] in (1_499_400, "1499400")
    assert pf["client_iva_amount_clp"]["value"] in (239_400, "239400")
    assert float(pf["client_iva_rate"]["value"]) == 0.19
    assert public["fields"]["supplier_payment_transfer_id"]["value"] == "****5677"

    events = public["events"]
    pay_ev = next(e for e in events if e["event_type"] == "client_payment_received")
    assert pay_ev.get("operation_id") == "[REDACTED]"
    sup_ev = next(e for e in events if e["event_type"] == "supplier_payment_sent")
    assert sup_ev.get("transfer_id") == "****5677"

    # Operator preview retains full IDs for local review
    op_blob = json.dumps(preview, ensure_ascii=False)
    assert "2152655677" in op_blob
    assert "INT_EMP" in op_blob


def test_redact_helper_idempotent() -> None:
    base = {
        "deal_key": "x",
        "fields": build_confirmed_fields(),
        "events": build_confirmed_events(),
    }
    once = redact_preview_for_public(base)
    twice = redact_preview_for_public(once)
    assert twice["fields"]["supplier_payment_transfer_id"]["value"] == "****5677"
    assert "public_export" not in twice
