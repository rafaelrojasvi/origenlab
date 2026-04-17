"""Tests for marketing export gate-context loading (Sent, suppression, outreach, GateContext)."""

from __future__ import annotations

import sqlite3

import pytest

from origenlab_email_pipeline.candidate_export_gate import GateContext
from origenlab_email_pipeline.contact_domain_suppression import (
    ensure_contact_domain_suppression_table,
    upsert_contact_domain_suppression,
    validate_contact_domain_suppression_payload,
)
from origenlab_email_pipeline.marketing_export_context import (
    DEFAULT_EXCLUDE_DOMAINS,
    DEFAULT_SENT_FOLDERS,
    build_marketing_export_gate_context,
    load_outreach_state_map,
    load_sent_recipient_norms,
    load_suppressed_contact_domains,
    load_suppressed_norms,
    norm_lead_email,
)
import origenlab_email_pipeline.next_marketing_queue as next_marketing_queue


def test_norm_lead_email_prefers_email_norm_and_first_mailbox() -> None:
    assert norm_lead_email("  A@B.CL ", None) == "a@b.cl"
    assert norm_lead_email(None, "x <Y@Z.org>") == "y@z.org"
    assert norm_lead_email("", "") is None


def test_load_sent_recipient_norms_parses_recipients_in_sent_folders() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE emails (recipients TEXT, source_file TEXT, folder TEXT)"
    )
    conn.execute(
        "INSERT INTO emails VALUES (?, ?, ?)",
        ("To: one@cliente.cl, Two@OTHER.cl", "gmail:contacto@origenlab.cl/123", "[Gmail]/Enviados"),
    )
    conn.commit()
    got = load_sent_recipient_norms(
        conn,
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados",),
    )
    assert got == {"one@cliente.cl", "two@other.cl"}
    conn.close()


def test_load_sent_recipient_norms_empty_when_no_emails_table() -> None:
    conn = sqlite3.connect(":memory:")
    assert load_sent_recipient_norms(conn, gmail_user="u@x.cl", sent_folders=("[Gmail]/Sent Mail",)) == set()
    conn.close()


def test_load_suppressed_norms() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE contact_email_suppression (
            email TEXT PRIMARY KEY,
            suppression_reason_code TEXT,
            suppression_reason_text TEXT,
            suppression_source TEXT,
            last_bounced_at TEXT,
            updated_at TEXT,
            updated_by TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO contact_email_suppression VALUES (?,?,?,?,?,?,?)",
        ("  Blocked@X.CL  ", "manual_do_not_contact", None, None, None, "t", "t"),
    )
    conn.commit()
    assert load_suppressed_norms(conn) == {"blocked@x.cl"}
    conn.close()


def test_load_outreach_state_map_only_blocking_states() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE outreach_contact_state (
            contact_email_norm TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            first_contacted_at TEXT,
            last_contacted_at TEXT,
            source TEXT,
            notes TEXT,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            lead_id INTEGER
        )"""
    )
    conn.execute(
        "INSERT INTO outreach_contact_state VALUES (?,?,?,?,?,?,?,?,?)",
        ("c@d.cl", "contacted", None, None, None, None, "t", "t", None),
    )
    conn.execute(
        "INSERT INTO outreach_contact_state VALUES (?,?,?,?,?,?,?,?,?)",
        ("n@o.cl", "not_contacted", None, None, None, None, "t", "t", None),
    )
    conn.commit()
    m = load_outreach_state_map(conn)
    assert m == {"c@d.cl": "contacted"}
    conn.close()


def test_load_suppressed_contact_domains() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_contact_domain_suppression_table(conn)
    upsert_contact_domain_suppression(
        conn,
        payload=validate_contact_domain_suppression_payload(
            domain="blocked.example",
            suppression_reason_text="t",
            updated_by="t",
        ),
    )
    conn.commit()
    assert load_suppressed_contact_domains(conn) == frozenset({"blocked.example"})
    conn.close()


def test_build_marketing_export_gate_context_shape_and_blocked_domains() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE emails (recipients TEXT, source_file TEXT, folder TEXT)")
    conn.execute(
        "INSERT INTO emails VALUES (?, ?, ?)",
        ("r@sent-in.cl", "gmail:u@x.cl/1", "[Gmail]/Sent Mail"),
    )
    conn.commit()
    ctx = build_marketing_export_gate_context(
        conn,
        gmail_user="u@x.cl",
        sent_folders=("[Gmail]/Sent Mail",),
        extra_exclude_domains=("extra.block.cl",),
        skip_noise_filter=True,
        skip_supplier_domain_filter=True,
        strict_contact_graph_noise=True,
    )
    assert isinstance(ctx, GateContext)
    assert ctx.sent_recipient_norms == frozenset({"r@sent-in.cl"})
    assert ctx.suppressed_norms == frozenset()
    assert ctx.suppressed_contact_domains == frozenset()
    assert ctx.outreach_state_by_email == {}
    assert ctx.supplier_domains == frozenset()
    assert ctx.skip_noise_filter is True
    assert ctx.skip_supplier_domain_filter is True
    assert ctx.strict_contact_graph_noise is True
    expected_blocked = frozenset(
        d.strip().lower() for d in list(DEFAULT_EXCLUDE_DOMAINS) + ["extra.block.cl"] if d.strip()
    )
    assert ctx.blocked_domains == expected_blocked
    conn.close()


def test_next_marketing_queue_reexports_same_gate_helpers() -> None:
    """Backward compatibility: queue module exposes same callables as marketing_export_context."""
    import origenlab_email_pipeline.marketing_export_context as mec

    assert next_marketing_queue.build_marketing_export_gate_context is mec.build_marketing_export_gate_context
    assert next_marketing_queue.load_suppressed_contact_domains is mec.load_suppressed_contact_domains
    assert next_marketing_queue.load_sent_recipient_norms is mec.load_sent_recipient_norms
    assert next_marketing_queue.load_suppressed_norms is mec.load_suppressed_norms
    assert next_marketing_queue.load_outreach_state_map is mec.load_outreach_state_map
    assert next_marketing_queue.norm_lead_email is mec.norm_lead_email
    assert next_marketing_queue.DEFAULT_SENT_FOLDERS is mec.DEFAULT_SENT_FOLDERS
    assert next_marketing_queue.DEFAULT_EXCLUDE_DOMAINS is mec.DEFAULT_EXCLUDE_DOMAINS
