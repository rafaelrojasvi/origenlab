"""Cyber campaign context audit — open-quote safety classification."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from origenlab_email_pipeline.campaigns.cyber_campaign_context_audit import (
    ACTION_DO_NOT_SEND,
    ACTION_GENERIC,
    ACTION_WARM,
    CLASS_ACTIVE_WAITING_ORIGENLAB,
    CLASS_ACTIVE_WAITING_SUPPLIER,
    CLASS_NET_NEW_SAFE,
    CLASS_OLD_QUOTE_NO_REPLY,
    CLASS_RECENT_CLIENT_REPLY,
    ContactContext,
    ThreadMessage,
    audit_cyber_top25,
    classify_contact_for_cyber,
    write_cyber_context_audit_outputs,
)


def _seed_emails(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE contact_master (
          email TEXT PRIMARY KEY,
          contact_name_best TEXT,
          domain TEXT,
          organization_name_guess TEXT,
          organization_type_guess TEXT,
          first_seen_at TEXT,
          last_seen_at TEXT,
          total_emails INTEGER,
          inbound_emails INTEGER,
          outbound_emails INTEGER,
          quote_email_count INTEGER,
          invoice_email_count INTEGER,
          purchase_email_count INTEGER,
          business_doc_email_count INTEGER,
          quote_doc_count INTEGER,
          invoice_doc_count INTEGER,
          top_equipment_tags TEXT,
          confidence_score REAL
        );
        CREATE TABLE organization_master (
          domain TEXT PRIMARY KEY,
          organization_name_guess TEXT,
          organization_type_guess TEXT,
          first_seen_at TEXT,
          last_seen_at TEXT,
          total_emails INTEGER,
          total_contacts INTEGER,
          quote_email_count INTEGER,
          invoice_email_count INTEGER,
          purchase_email_count INTEGER,
          business_doc_email_count INTEGER,
          quote_doc_count INTEGER,
          invoice_doc_count INTEGER,
          top_equipment_tags TEXT,
          key_contacts TEXT
        );
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_file TEXT,
          folder TEXT,
          message_id TEXT,
          subject TEXT,
          sender TEXT,
          recipients TEXT,
          date_raw TEXT,
          date_iso TEXT,
          body TEXT,
          body_html TEXT,
          body_text_raw TEXT,
          body_text_clean TEXT,
          body_source_type TEXT,
          body_has_plain INTEGER,
          top_reply_clean TEXT
        );
        """
    )


def test_net_new_without_thread_gets_generic() -> None:
    ctx = ContactContext(
        email="new@lab.cl",
        organization="Lab Nuevo",
        segment="net_new_safe",
        reason_for_inclusion="Phase 10D",
        selection_rationale="Phase10D",
        domain="lab.cl",
        thread=[],
    )
    row = classify_contact_for_cyber(
        ctx, now=datetime(2026, 5, 31, tzinfo=timezone.utc)
    )
    assert row.quote_safety_classification == CLASS_NET_NEW_SAFE
    assert row.recommended_action == ACTION_GENERIC


def test_recent_client_quote_request_blocks_cyber() -> None:
    ctx = ContactContext(
        email="cliente@uni.cl",
        organization="Universidad",
        segment="warm_open",
        reason_for_inclusion="warm",
        selection_rationale="warm",
        domain="uni.cl",
        thread=[
            ThreadMessage(
                date_iso="2026-05-28T10:00:00+00:00",
                folder="INBOX",
                subject="Solicitud cotización centrífuga",
                body="Necesitamos cotización formal",
                direction="inbound",
            ),
            ThreadMessage(
                date_iso="2026-05-20T10:00:00+00:00",
                folder="[Gmail]/Enviados",
                subject="Re: equipos",
                body="Gracias por escribir",
                direction="outbound",
            ),
        ],
    )
    row = classify_contact_for_cyber(
        ctx, now=datetime(2026, 5, 31, tzinfo=timezone.utc)
    )
    assert row.quote_safety_classification == CLASS_ACTIVE_WAITING_ORIGENLAB
    assert row.recommended_action == ACTION_DO_NOT_SEND


def test_old_quote_no_reply_allows_warm_followup() -> None:
    ctx = ContactContext(
        email="buyer@food.cl",
        organization="FoodCo",
        segment="previous_buyer_responder",
        reason_for_inclusion="compras",
        selection_rationale="previous",
        domain="food.cl",
        contact_purchase_count=5,
        thread=[
            ThreadMessage(
                date_iso="2026-05-10T10:00:00+00:00",
                folder="[Gmail]/Enviados",
                subject="Cotización equipos laboratorio",
                body="Adjunto cotización solicitada",
                direction="outbound",
            ),
        ],
    )
    row = classify_contact_for_cyber(
        ctx, now=datetime(2026, 5, 31, tzinfo=timezone.utc)
    )
    assert row.quote_safety_classification == CLASS_OLD_QUOTE_NO_REPLY
    assert row.recommended_action == ACTION_WARM


def test_cesmec_blocked_from_cyber() -> None:
    ctx = ContactContext(
        email="juan@bureauveritas.com",
        organization="CESMEC",
        segment="net_new_safe",
        reason_for_inclusion="Phase 10D",
        selection_rationale="Phase10D",
        domain="bureauveritas.com",
        thread=[],
    )
    row = classify_contact_for_cyber(
        ctx, now=datetime(2026, 5, 31, tzinfo=timezone.utc)
    )
    assert row.quote_safety_classification == CLASS_RECENT_CLIENT_REPLY
    assert row.recommended_action == ACTION_DO_NOT_SEND


def test_unach_hielscher_blocked() -> None:
    ctx = ContactContext(
        email="susana@unach.cl",
        organization="UNACH",
        segment="warm_open",
        reason_for_inclusion="warm",
        selection_rationale="warm",
        domain="unach.cl",
        thread=[],
    )
    row = classify_contact_for_cyber(
        ctx, now=datetime(2026, 5, 31, tzinfo=timezone.utc)
    )
    assert row.quote_safety_classification == CLASS_ACTIVE_WAITING_SUPPLIER
    assert row.recommended_action == ACTION_DO_NOT_SEND


def test_audit_writes_outputs(tmp_path: Path) -> None:
    out = tmp_path / "current"
    out.mkdir()
    (out / "cyber_top25_org_deduped.csv").write_text(
        "email,organization,contact_name,segment,reason_for_inclusion,product_angle,"
        "suggested_subject,suggested_message,safety_status,exclusion_reason,domain,"
        "secondary_contact_emails,geo_status,selection_rationale\n"
        "safe@lab.cl,Lab Safe,,net_new_safe,Phase 10D,angle,sub,msg,eligible,,lab.cl,,chile_ok,Phase10D\n",
        encoding="utf-8",
    )
    (out / "cyber_same_domain_review.csv").write_text(
        "email,organization,contact_name,segment,reason_for_inclusion,product_angle,"
        "suggested_subject,suggested_message,safety_status,exclusion_reason\n",
        encoding="utf-8",
    )
    (out / "cyber_excluded_blocked.csv").write_text(
        "email,organization,contact_name,segment,reason_for_inclusion,product_angle,"
        "suggested_subject,suggested_message,safety_status,exclusion_reason\n",
        encoding="utf-8",
    )

    conn = sqlite3.connect(":memory:")
    _seed_emails(conn)
    conn.execute(
        "INSERT INTO contact_master (email, domain, quote_email_count, purchase_email_count, "
        "inbound_emails, outbound_emails) VALUES ('safe@lab.cl', 'lab.cl', 0, 0, 0, 0)"
    )
    conn.commit()

    result = audit_cyber_top25(conn, out_dir=out)
    paths = write_cyber_context_audit_outputs(result, out)
    assert paths["generic"].is_file()
    assert paths["report"].is_file()
    assert result.summary["send_now_generic"] == 1
    conn.close()
