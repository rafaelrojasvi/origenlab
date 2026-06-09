"""Mart email body scan profiling (observability only)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from origenlab_email_pipeline.business_mart import DocAgg
from origenlab_email_pipeline.core.mart.build_options import MartBuildOptions
from origenlab_email_pipeline.core.mart.contact_org_builder import scan_email_contacts
from origenlab_email_pipeline.db import init_schema

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]


def _default_options() -> MartBuildOptions:
    return MartBuildOptions(
        internal_domains=frozenset({"origenlab.cl"}),
        limit_emails=None,
        dashboard_fast=False,
        canonical_only=False,
        since_days=None,
        skip_document_master_if_unchanged=False,
        mart_date_slack_days=30,
    )


def _insert_email(
    conn: sqlite3.Connection,
    *,
    message_id: str,
    top_reply_clean: str,
    full_body_clean: str,
) -> None:
    conn.execute(
        """
        INSERT INTO emails (
          source_file, message_id, date_iso, folder, sender, recipients,
          subject, body, full_body_clean, top_reply_clean
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "gmail:contacto@origenlab.cl/INBOX",
            message_id,
            "2026-06-01T10:00:00",
            "INBOX",
            "Buyer <buyer@lab.cl>",
            "contacto@origenlab.cl",
            "Subject",
            top_reply_clean or full_body_clean or "",
            full_body_clean,
            top_reply_clean,
        ),
    )


def test_scan_email_contacts_prints_mart_body_profile(capsys) -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    _insert_email(conn, message_id="top-only", top_reply_clean="top text", full_body_clean="ignored full")
    _insert_email(conn, message_id="fallback", top_reply_clean="", full_body_clean="fallback body")
    _insert_email(conn, message_id="empty", top_reply_clean="", full_body_clean="")
    conn.commit()

    _, scanned = scan_email_contacts(
        conn,
        options=_default_options(),
        doc_aggs=DocAgg(set(), {}),
    )
    conn.close()

    out = capsys.readouterr().out
    assert scanned == 3
    assert "Scanned emails (for mart): 3" in out
    assert "[timing] email_scan_seconds=" in out
    assert "[mart-profile] top_reply_nonempty_rows=1" in out
    assert "[mart-profile] top_reply_empty_rows=2" in out
    assert "[mart-profile] full_body_fallback_used_rows=1" in out
    assert "[mart-profile] top_reply_total_chars=8" in out
    assert "[mart-profile] full_body_fallback_total_chars=13" in out
