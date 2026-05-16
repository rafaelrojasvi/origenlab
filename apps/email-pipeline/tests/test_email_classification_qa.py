"""Unit tests for read-only email classification QA heuristics (not production classifier)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

from origenlab_email_pipeline.contacto_gmail_source import (
    CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE,
    sql_predicate_contacto_gmail_source,
)
from origenlab_email_pipeline.email_classification_qa import (
    canonical_where_for_alias,
    classify_email_row,
    detect_bad_email_or_bounce,
    detect_purchase_or_order_signal,
    detect_quote_request_inbound,
    detect_university_signals,
    inbound_exists_after_sent,
    mark_no_response_candidates,
    qa_operational_internal_domains,
)

CANON = "gmail:contacto@origenlab.cl/INBOX"


def _empty_suppliers() -> frozenset[str]:
    return frozenset()


def _internal() -> frozenset[str]:
    return qa_operational_internal_domains()


def test_detect_quote_request_inbound_spanish() -> None:
    hit, conf, ev = detect_quote_request_inbound(
        True,
        "Buenos días, necesitamos ficha técnica y precio para centrifuga X.",
    )
    assert hit is True
    assert "high" in conf
    assert "equipment" in ev or "commercial" in ev


def test_detect_quote_request_inbound_negative_non_inbox() -> None:
    hit, _, _ = detect_quote_request_inbound(
        False,
        "necesitamos cotización urgente",
    )
    assert hit is False


def test_detect_bad_email_or_bounce_mailer_daemon() -> None:
    hit, conf, ev = detect_bad_email_or_bounce(
        "Mail Delivery Subsystem <mailer-daemon@google.com>",
        "Delivery Status Notification (Failure)",
        "",
    )
    assert hit is True
    assert conf == "high_confidence"
    assert ev in {"bounce_sender", "is_noise_sender", "ndr_subject_or_snippet"}


def test_detect_bad_email_or_bounce_ndr_subject() -> None:
    hit, conf, ev = detect_bad_email_or_bounce(
        "Servicio <noreply@x.cl>",
        "Undeliverable: message to user@x.cl",
        "body",
    )
    assert hit is True
    assert conf == "high_confidence"


def test_detect_university_domain_and_keyword() -> None:
    ok, ev = detect_university_signals(
        "random",
        "Jane <j@stanford.edu>",
        None,
    )
    assert ok is True
    assert "domain_tail" in ev or "edu" in ev

    ok2, ev2 = detect_university_signals(
        "Coordinación universidad de Chile",
        "a@b.cl",
        None,
    )
    assert ok2 is True
    assert "keyword" in ev2


def test_canonical_where_for_alias_contains_contacto_prefix() -> None:
    w = canonical_where_for_alias("e")
    assert "e.source_file" in w
    assert CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE in w


def test_sql_predicate_default_column_unqualified() -> None:
    w = sql_predicate_contacto_gmail_source()
    assert "source_file" in w
    assert "." not in w.split()[0]


def test_qa_operational_internal_domains_defaults_no_pollution() -> None:
    doms = qa_operational_internal_domains()
    for x in (
        "dhl.com",
        "facebookmail.com",
        "mercadopublico.cl",
        "twitter.com",
        "wherex.com",
        "soviquim.cl",
        "labx.com",
    ):
        assert x not in doms
    assert "origenlab.cl" in doms and "labdelivery.cl" in doms


def test_qa_operational_internal_domains_env_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORIGENLAB_INTERNAL_DOMAINS", "subsidiary.cl, @partner.cl")
    d = qa_operational_internal_domains()
    assert "subsidiary.cl" in d
    assert "partner.cl" in d
    assert "origenlab.cl" in d


def test_classify_marketplace_domain_priority_over_commercial_blob() -> None:
    rc = classify_email_row(
        folder="INBOX",
        subject="Resultado cotización",
        sender="notificaciones@mercadopublico.cl",
        recipients="contacto@origenlab.cl",
        body="Su cotización en Mercado Público; precio y plazo de entrega adjuntos.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv=None,
        supplier_domains=_empty_suppliers(),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "marketplace_or_procurement_platform"


def test_classify_wherex_marketplace() -> None:
    rc = classify_email_row(
        folder="INBOX",
        subject="OC publicada",
        sender="alertas@wherex.com",
        recipients="contacto@origenlab.cl",
        body="Orden de compra publicada; requerimos precio.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv=None,
        supplier_domains=_empty_suppliers(),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "marketplace_or_procurement_platform"


def test_classify_dhl_logistics() -> None:
    rc = classify_email_row(
        folder="INBOX",
        subject="Shipment delivered",
        sender="no.reply@dhl.com",
        recipients="contacto@origenlab.cl",
        body="Your shipment has been delivered. Precio no aplica.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv=None,
        supplier_domains=_empty_suppliers(),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "logistics_or_notification"


def test_classify_facebookmail_logistics() -> None:
    rc = classify_email_row(
        folder="INBOX",
        subject="Notification",
        sender="noreply@facebookmail.com",
        recipients="contacto@origenlab.cl",
        body="You have a new notification.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv=None,
        supplier_domains=_empty_suppliers(),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "logistics_or_notification"


def test_detect_quote_strong_solicito_cotizacion() -> None:
    hit, conf, _ = detect_quote_request_inbound(
        True,
        "Estimados, solicito cotización formal de los ítems listados.",
    )
    assert hit and conf == "high_confidence"


def test_detect_quote_medium_valor_only() -> None:
    hit, conf, _ = detect_quote_request_inbound(True, "Necesito el valor unitario de cada repuesto.")
    assert hit and "medium" in conf


def test_cotizacion_sent_document_master_quote_only() -> None:
    rc = classify_email_row(
        folder="[Gmail]/Enviados",
        subject="Fwd",
        sender="contacto@origenlab.cl",
        recipients="a@b.cl",
        body="Ver adjunto.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv="quote",
        supplier_domains=_empty_suppliers(),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "cotizacion_sent"
    assert "medium" in rc.confidence


def test_classify_cotizacion_sent_with_doc_quote() -> None:
    rc = classify_email_row(
        folder="[Gmail]/Enviados",
        subject="Cotización",
        sender="contacto@origenlab.cl",
        recipients="buyer@hospital.cl",
        body="Adjuntamos cotización según lo conversado.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv="quote,invoice",
        supplier_domains=_empty_suppliers(),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "cotizacion_sent"
    assert "high" in rc.confidence


def test_classify_supplier_domain() -> None:
    rc = classify_email_row(
        folder="INBOX",
        subject="Lista mayo",
        sender="rep@acme-supplier-test.invalid",
        recipients="contacto@origenlab.cl",
        body="",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv=None,
        supplier_domains=frozenset({"acme-supplier-test.invalid"}),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "supplier_or_vendor"


def test_mark_no_response_and_inbound_exists(tmp_path: Path) -> None:
    db = tmp_path / "nr.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            source_file TEXT NOT NULL,
            folder TEXT,
            sender TEXT,
            recipients TEXT,
            subject TEXT,
            date_iso TEXT,
            body TEXT,
            full_body_clean TEXT,
            top_reply_clean TEXT
        );
        """
    )
    src = "gmail:contacto@origenlab.cl/[Gmail]/Enviados"
    now = datetime.now(timezone.utc)
    day_sent = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    day_in = (now - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO emails (id, source_file, folder, sender, recipients, subject, date_iso, body, full_body_clean, top_reply_clean)
        VALUES (1, ?, '[Gmail]/Enviados', 'contacto@origenlab.cl', 'Buyer <buyer@cliente-test.cl>', 'Cotización', ?,
                'Adjuntamos cotización en PDF.', '', '')
        """,
        (src, day_sent),
    )
    conn.commit()
    pred = sql_predicate_contacto_gmail_source()
    internal = _internal()
    cand = mark_no_response_candidates(
        conn,
        canonical_where_sql=pred,
        days=400,
        limit=50,
        internal_domains_lower=internal,
    )
    assert len(cand) == 1
    assert cand[0]["id"] == 1

    conn.execute(
        """
        INSERT INTO emails (id, source_file, folder, sender, recipients, subject, date_iso, body, full_body_clean, top_reply_clean)
        VALUES (2, ?, 'INBOX', 'buyer@cliente-test.cl', 'contacto@origenlab.cl', 'Re: Cotización', ?,
                'Gracias recibimos la cotización.', '', '')
        """,
        (CANON, day_in),
    )
    conn.commit()

    cand2 = mark_no_response_candidates(
        conn,
        canonical_where_sql=pred,
        days=400,
        limit=50,
        internal_domains_lower=internal,
    )
    assert cand2 == []

    cw = canonical_where_for_alias("e")
    assert inbound_exists_after_sent(
        conn,
        sent_id=1,
        sent_date_iso=day_sent,
        counterparty_emails_lower={"buyer@cliente-test.cl"},
        counterparty_domains_lower={"cliente-test.cl"},
        canonical_predicate_on_e=cw,
    ) is True
    conn.close()


def test_audit_email_classification_quality_script_smoke(tmp_path: Path) -> None:
    db = tmp_path / "audit.sqlite"
    script = REPO / "scripts" / "qa" / "audit_email_classification_quality.py"
    now = datetime.now(timezone.utc)
    day_iso = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            source_file TEXT NOT NULL,
            folder TEXT,
            sender TEXT,
            recipients TEXT,
            subject TEXT,
            date_iso TEXT,
            body TEXT,
            full_body_clean TEXT,
            top_reply_clean TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO emails VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            1,
            CANON,
            "INBOX",
            "x@y.com",
            "contacto@origenlab.cl",
            "RFQ",
            day_iso,
            "Please send us a quote for two units.",
            "",
            "",
        ),
    )
    conn.commit()
    conn.close()

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(db),
            "--days",
            "800",
            "--limit",
            "100",
            "--json",
            "--no-csv",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert cp.returncode == 0, cp.stderr + cp.stdout
    payload = json.loads(cp.stdout)
    assert payload["summary"]["rows_scanned"] == 1
    assert payload["summary"]["counts_by_primary"].get("quote_request_inbound") == 1


def test_audit_script_opportunity_signals_group_concat_no_distinct_separator_crash(
    tmp_path: Path,
) -> None:
    """SQLite rejects GROUP_CONCAT(DISTINCT col, sep); audit must use a dedupe subquery."""
    db = tmp_path / "sig.sqlite"
    script = REPO / "scripts" / "qa" / "audit_email_classification_quality.py"
    now = datetime.now(timezone.utc)
    day_iso = (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE emails (id INTEGER PRIMARY KEY, source_file TEXT NOT NULL, folder TEXT, "
        "sender TEXT, recipients TEXT, subject TEXT, date_iso TEXT, body TEXT, full_body_clean TEXT, top_reply_clean TEXT)"
    )
    conn.execute(
        "INSERT INTO emails VALUES (?,?,?,?,?,?,?,?,?,?)",
        (1, CANON, "INBOX", "buyer@z.cl", "contacto@origenlab.cl", "Hi", day_iso, "hello", "", ""),
    )
    conn.executescript(
        """
        CREATE TABLE opportunity_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_type TEXT NOT NULL,
            entity_kind TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            email_id INTEGER,
            attachment_id INTEGER,
            score REAL,
            details_json TEXT,
            created_at TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO opportunity_signals (signal_type, entity_kind, entity_key, email_id) VALUES (?,?,?,?)",
        [
            ("inbound_rfq", "contact", "buyer@z.cl", 1),
            ("inbound_rfq", "contact", "buyer@z.cl_dup", 1),
            ("warm_lead", "contact", "buyer@z.cl", 1),
        ],
    )
    conn.commit()
    conn.close()

    out_json = tmp_path / "audit_full.json"
    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--db",
            str(db),
            "--days",
            "30",
            "--limit",
            "50",
            "--out",
            str(out_json),
            "--no-csv",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert cp.returncode == 0, cp.stderr + cp.stdout
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["rows_scanned"] == 1
    ex0 = next((x for x in payload["review_csv_rows"] if x["email_id"] == "1"), None)
    assert ex0 is not None
    assert "inbound_rfq" in ex0["notes"]
    assert "warm_lead" in ex0["notes"]
    assert "recommended_action" in ex0 and ex0["recommended_action"]
    assert ex0.get("confidence") in {"high_confidence", "medium_confidence", "weak_signal", "needs_manual_review"}


def test_priority_sent_cotiz_medium_beats_supplier_cc() -> None:
    rc = classify_email_row(
        folder="[Gmail]/Enviados",
        subject="Re: Oferta",
        sender="contacto@origenlab.cl",
        recipients="buyer@x.cl, rep@acme-supplier-test.invalid",
        body="Adjuntamos cotización según lo conversado.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv=None,
        supplier_domains=frozenset({"acme-supplier-test.invalid"}),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "cotizacion_sent"


    rc = classify_email_row(
        folder="INBOX",
        subject="Pedido",
        sender="rep@acme-supplier-test.invalid",
        recipients="contacto@origenlab.cl",
        body="Desde universidad de Chile proyecto interno: necesitamos valor unitario.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv=None,
        supplier_domains=frozenset({"acme-supplier-test.invalid"}),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "supplier_or_vendor"


def test_priority_logistics_beats_medium_quote() -> None:
    rc = classify_email_row(
        folder="INBOX",
        subject="Shipment update",
        sender="track@dhl.com",
        recipients="contacto@origenlab.cl",
        body="Su envío está en tránsito. precio del flete ya pagado.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv=None,
        supplier_domains=_empty_suppliers(),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "logistics_or_notification"


def test_priority_cotizacion_sent_high_beats_supplier_on_sent() -> None:
    rc = classify_email_row(
        folder="[Gmail]/Enviados",
        subject="Cotización",
        sender="contacto@origenlab.cl",
        recipients="buyer@h.cl, rep@acme-supplier-test.invalid",
        body="Adjuntamos cotización formal según lo solicitado.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv="quote",
        supplier_domains=frozenset({"acme-supplier-test.invalid"}),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "cotizacion_sent"
    assert rc.recommended_action == "revisar_cotizacion"


def test_priority_university_beats_weak_quote_only() -> None:
    rc = classify_email_row(
        folder="INBOX",
        subject="Lab",
        sender="researcher@stanford.edu",
        recipients="contacto@origenlab.cl",
        body="We need the equipo for the shelf.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv=None,
        supplier_domains=_empty_suppliers(),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "university_or_research"


def test_recommended_action_quote_request() -> None:
    rc = classify_email_row(
        folder="INBOX",
        subject="Consulta",
        sender="buyer@cliente.cl",
        recipients="contacto@origenlab.cl",
        body="Solicito cotización de dos centrífugas.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv=None,
        supplier_domains=_empty_suppliers(),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "quote_request_inbound"
    assert rc.recommended_action == "responder_solicitud"


@pytest.mark.parametrize(
    "legacy",
    [False, True],
)
def test_audit_script_json_includes_legacy_note_when_flag(legacy: bool, tmp_path: Path) -> None:
    db = tmp_path / "leg.sqlite"
    script = REPO / "scripts" / "qa" / "audit_email_classification_quality.py"
    now = datetime.now(timezone.utc)
    day_iso = (now - timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE emails (id INTEGER PRIMARY KEY, source_file TEXT NOT NULL, folder TEXT, "
        "sender TEXT, recipients TEXT, subject TEXT, date_iso TEXT, body TEXT, full_body_clean TEXT, top_reply_clean TEXT)"
    )
    conn.execute(
        "INSERT INTO emails VALUES (?,?,?,?,?,?,?,?,?,?)",
        (1, CANON, "INBOX", "a@b.c", "contacto@origenlab.cl", "Hi", day_iso, "hello", "", ""),
    )
    conn.commit()
    conn.close()
    cmd = [
        sys.executable,
        str(script),
        "--db",
        str(db),
        "--days",
        "900",
        "--limit",
        "20",
        "--json",
        "--no-csv",
    ]
    if legacy:
        cmd.append("--legacy-also")
    cp = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, timeout=90)
    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout)
    if legacy:
        assert "legacy" in (payload["summary"].get("legacy_note") or "").lower()
    assert payload["summary"]["legacy_flag"] is legacy


def test_detect_purchase_or_order_signal_strong_inbound() -> None:
    hit, conf, ev = detect_purchase_or_order_signal(
        is_inbox=True,
        blob="Adjunto orden de compra OC-2026-44 para despacho.",
        sender="compras@hospital.cl",
        recipients="contacto@origenlab.cl",
        internal_domains_lower=_internal(),
    )
    assert hit is True
    assert conf == "high_confidence"
    assert "purchase" in ev


def test_classify_email_row_purchase_primary() -> None:
    rc = classify_email_row(
        folder="INBOX",
        subject="Orden de compra 9912",
        sender="compras@cliente.cl",
        recipients="contacto@origenlab.cl",
        body="Confirmamos orden de compra para equipos.",
        full_body_clean="",
        top_reply_clean="",
        doc_types_csv=None,
        supplier_domains=_empty_suppliers(),
        internal_domains_lower=_internal(),
    )
    assert rc.primary == "purchase_or_order_signal"
    assert rc.recommended_action == "revisar_cliente_activo"
