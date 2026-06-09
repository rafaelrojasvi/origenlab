"""Mart email body scan profiling and lazy full-body fallback."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from origenlab_email_pipeline.business_mart import DocAgg
from origenlab_email_pipeline.core.mart import contact_org_builder
from origenlab_email_pipeline.core.mart.build_options import MartBuildOptions
from origenlab_email_pipeline.core.mart.contact_org_builder import scan_email_contacts
from origenlab_email_pipeline.db import init_schema

_PIPELINE_ROOT = Path(__file__).resolve().parents[1]

_MART_SCAN_TIMING_LINES = (
    "[timing] mart_scan_body_seconds=",
    "[timing] mart_scan_noise_seconds=",
    "[timing] mart_scan_address_parse_seconds=",
    "[timing] mart_scan_intent_seconds=",
    "[timing] mart_scan_equipment_seconds=",
    "[timing] mart_scan_doc_lookup_seconds=",
    "[timing] mart_scan_target_build_seconds=",
    "[timing] mart_scan_contact_update_seconds=",
    "[timing] mart_scan_date_seconds=",
)

_MART_SCAN_BODY_PROFILE_LINES = (
    "[mart-profile] body_total_chars=",
    "[mart-profile] body_max_chars=",
    "[mart-profile] body_rows_gt_2k=",
    "[mart-profile] body_rows_gt_5k=",
    "[mart-profile] body_rows_gt_10k=",
    "[mart-profile] body_rows_gt_50k=",
)

_MART_SCAN_FETCH_PROFILE_LINES = (
    "[timing] mart_scan_fetchmany_seconds=",
    "[timing] mart_scan_measured_stage_seconds=",
    "[timing] mart_scan_unattributed_seconds=",
    "[mart-profile] mart_scan_batches=",
    "[mart-profile] mart_scan_batch_size=5000",
)

_MART_TARGET_GATED_PROFILE_LINES = (
    "[mart-profile] mart_target_candidate_rows=",
    "[mart-profile] mart_no_target_rows=",
    "[mart-profile] mart_target_candidate_body_chars=",
    "[mart-profile] mart_no_target_body_chars=",
    "[mart-profile] mart_target_candidate_rows_gt_2k=",
    "[mart-profile] mart_no_target_rows_gt_2k=",
    "[mart-profile] mart_target_candidate_rows_gt_10k=",
    "[mart-profile] mart_no_target_rows_gt_10k=",
)

_MART_PRE_NOISE_TARGET_PROFILE_LINES = (
    "[mart-profile] mart_pre_noise_target_candidate_rows=",
    "[mart-profile] mart_pre_noise_no_target_rows=",
    "[mart-profile] mart_pre_noise_target_candidate_body_chars=",
    "[mart-profile] mart_pre_noise_no_target_body_chars=",
    "[mart-profile] mart_pre_noise_target_candidate_rows_gt_2k=",
    "[mart-profile] mart_pre_noise_no_target_rows_gt_2k=",
    "[mart-profile] mart_pre_noise_target_candidate_rows_gt_10k=",
    "[mart-profile] mart_pre_noise_no_target_rows_gt_10k=",
    "[timing] mart_pre_noise_target_preview_seconds=",
)


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
    subject: str = "Subject",
    sender: str = "Buyer <buyer@lab.cl>",
    recipients: str = "contacto@origenlab.cl",
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
            sender,
            recipients,
            subject,
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
    assert "[mart-profile] full_body_lazy_fetches=2" in out
    assert "[timing] full_body_lazy_fetch_seconds=" in out
    for line in _MART_SCAN_TIMING_LINES:
        assert line in out
    for line in _MART_SCAN_BODY_PROFILE_LINES:
        assert line in out
    for line in _MART_SCAN_FETCH_PROFILE_LINES:
        assert line in out
    for line in _MART_TARGET_GATED_PROFILE_LINES:
        assert line in out
    for line in _MART_PRE_NOISE_TARGET_PROFILE_LINES:
        assert line in out
    assert "[mart-profile] body_total_chars=21" in out
    assert "[mart-profile] body_max_chars=13" in out
    assert "[mart-profile] mart_scan_batches=2" in out
    assert "[mart-profile] mart_target_candidate_rows=3" in out
    assert "[mart-profile] mart_no_target_rows=0" in out
    assert "[mart-profile] mart_pre_noise_target_candidate_rows=3" in out
    assert "[mart-profile] mart_pre_noise_no_target_rows=0" in out


def test_top_reply_present_skips_lazy_full_body_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    _insert_email(conn, message_id="top-only", top_reply_clean="top text", full_body_clean="never read")
    conn.commit()

    fetch_mock = MagicMock(side_effect=AssertionError("lazy fetch should not run"))
    monkeypatch.setattr(contact_org_builder, "fetch_full_body_clean_for_email", fetch_mock)

    contact, scanned = scan_email_contacts(
        conn,
        options=_default_options(),
        doc_aggs=DocAgg(set(), {}),
    )
    conn.close()

    assert scanned == 1
    fetch_mock.assert_not_called()
    assert contact["buyer@lab.cl"]["total"] >= 0


def test_lazy_fallback_increments_profile_counters(capsys) -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    _insert_email(conn, message_id="fallback", top_reply_clean="", full_body_clean="fallback body")
    conn.commit()

    scan_email_contacts(conn, options=_default_options(), doc_aggs=DocAgg(set(), {}))
    conn.close()

    out = capsys.readouterr().out
    assert "[mart-profile] top_reply_empty_rows=1" in out
    assert "[mart-profile] full_body_fallback_used_rows=1" in out
    assert "[mart-profile] full_body_lazy_fetches=1" in out


def test_empty_top_and_full_keeps_body_empty(capsys) -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    _insert_email(conn, message_id="empty", top_reply_clean="", full_body_clean="")
    conn.commit()

    contact, scanned = scan_email_contacts(
        conn,
        options=_default_options(),
        doc_aggs=DocAgg(set(), {}),
    )
    conn.close()

    out = capsys.readouterr().out
    assert scanned == 1
    assert "[mart-profile] top_reply_empty_rows=1" in out
    assert "[mart-profile] full_body_fallback_used_rows=0" in out
    assert "[mart-profile] full_body_lazy_fetches=1" in out
    assert contact["buyer@lab.cl"]["quote_email"] == 0
    assert contact["buyer@lab.cl"]["total"] == 1


def test_quote_intent_from_top_reply_clean() -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    _insert_email(
        conn,
        message_id="top-quote",
        top_reply_clean="necesitamos cotización de equipos",
        full_body_clean="ignored",
        subject="Cotización",
    )
    conn.commit()

    contact, _ = scan_email_contacts(conn, options=_default_options(), doc_aggs=DocAgg(set(), {}))
    conn.close()

    row = contact["buyer@lab.cl"]
    assert row["quote_email"] == 1
    assert row["total"] == 1


def test_target_gated_body_opportunity_counters(capsys) -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    _insert_email(
        conn,
        message_id="inbound-external",
        top_reply_clean="inbound body",
        full_body_clean="",
        sender="Buyer <buyer@lab.cl>",
        recipients="contacto@origenlab.cl",
    )
    _insert_email(
        conn,
        message_id="outbound-external",
        top_reply_clean="outbound body",
        full_body_clean="",
        sender="OrigenLab <contacto@origenlab.cl>",
        recipients="Buyer <buyer@external.cl>",
    )
    _insert_email(
        conn,
        message_id="internal-only",
        top_reply_clean="internal only",
        full_body_clean="",
        sender="OrigenLab <contacto@origenlab.cl>",
        recipients="Ops <ops@origenlab.cl>",
    )
    conn.commit()

    scan_email_contacts(conn, options=_default_options(), doc_aggs=DocAgg(set(), {}))
    conn.close()

    out = capsys.readouterr().out
    for line in _MART_TARGET_GATED_PROFILE_LINES:
        assert line in out
    for line in _MART_PRE_NOISE_TARGET_PROFILE_LINES:
        assert line in out
    assert "[mart-profile] mart_target_candidate_rows=2" in out
    assert "[mart-profile] mart_no_target_rows=1" in out
    assert "[mart-profile] mart_target_candidate_body_chars=25" in out
    assert "[mart-profile] mart_no_target_body_chars=13" in out
    assert "[mart-profile] mart_pre_noise_target_candidate_rows=2" in out
    assert "[mart-profile] mart_pre_noise_no_target_rows=1" in out
    assert "[mart-profile] mart_pre_noise_target_candidate_body_chars=25" in out
    assert "[mart-profile] mart_pre_noise_no_target_body_chars=13" in out


def test_quote_intent_from_lazy_full_body_when_top_empty() -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    _insert_email(
        conn,
        message_id="full-quote",
        top_reply_clean="",
        full_body_clean="necesitamos cotización de equipos",
        subject="Cotización",
    )
    conn.commit()

    contact, _ = scan_email_contacts(conn, options=_default_options(), doc_aggs=DocAgg(set(), {}))
    conn.close()

    row = contact["buyer@lab.cl"]
    assert row["quote_email"] == 1
    assert row["total"] == 1
