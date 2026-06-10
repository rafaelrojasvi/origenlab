"""Tests for email_mart_features schema and pure extraction helpers."""

from __future__ import annotations

import json
import sqlite3

from origenlab_email_pipeline.core.mart.email_mart_features import (
    compute_email_mart_feature,
    compute_feature_source_hash,
    select_mart_body_text,
)
from origenlab_email_pipeline.core.mart.email_mart_features_schema import (
    ensure_email_mart_features_table,
)
from origenlab_email_pipeline.db import init_schema
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema

_INTERNAL = frozenset({"origenlab.cl"})
_COMPUTED_AT = "2026-06-09T12:00:00+00:00"
_SLACK_DAYS = 30


def _feature_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email_id": 1,
        "message_id": "msg-1",
        "source_file": "gmail:contacto@origenlab.cl/INBOX",
        "folder": "INBOX",
        "sender": "Buyer <buyer@lab.cl>",
        "recipients": "contacto@origenlab.cl",
        "subject": "Subject",
        "top_reply_clean": "top body",
        "full_body_clean": "full body",
        "date_iso": "2026-06-01T10:00:00",
        "internal_domains": _INTERNAL,
        "mart_date_slack_days": _SLACK_DAYS,
        "computed_at": _COMPUTED_AT,
    }
    base.update(overrides)
    return base


def _hash_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "message_id": "msg-1",
        "sender": "Buyer <buyer@lab.cl>",
        "recipients": "contacto@origenlab.cl",
        "subject": "Subject",
        "top_reply_clean": "top body",
        "full_body_clean": "full body",
        "date_iso": "2026-06-01T10:00:00",
        "internal_domains": _INTERNAL,
        "mart_date_slack_days": _SLACK_DAYS,
    }
    base.update(overrides)
    return base


def test_db_import_smoke() -> None:
    from origenlab_email_pipeline.db import connect, init_schema

    assert connect is not None
    assert init_schema is not None


def test_init_schema_creates_email_mart_features_table() -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='email_mart_features'"
    ).fetchone()
    assert row is not None
    indexes = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='email_mart_features'"
        ).fetchall()
    }
    assert "idx_email_mart_features_sender_domain" in indexes
    assert "idx_email_mart_features_direction" in indexes
    assert "idx_email_mart_features_is_noise" in indexes
    conn.close()


def test_ensure_email_mart_features_table_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY,
          source_file TEXT NOT NULL,
          message_id TEXT
        )
        """
    )
    ensure_email_mart_features_table(conn)
    ensure_email_mart_features_table(conn)
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='email_mart_features'"
    ).fetchone()[0] == 1
    conn.close()


def test_migrate_sqlite_schema_includes_email_mart_features() -> None:
    conn = sqlite3.connect(":memory:")
    migrate_sqlite_schema(conn, layers={SchemaLayer.ARCHIVE_AND_MART})
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='email_mart_features'"
    ).fetchone()
    conn.close()


def test_compute_inbound_external_feature() -> None:
    feature = compute_email_mart_feature(**_feature_kwargs())

    assert feature.direction == "inbound"
    assert feature.sender_email == "buyer@lab.cl"
    assert feature.sender_domain == "lab.cl"
    assert json.loads(feature.recipient_emails_json) == ["contacto@origenlab.cl"]
    assert json.loads(feature.external_targets_json) == ["buyer@lab.cl"]
    assert feature.is_noise == 0
    assert feature.body_len == len("top body")


def test_compute_outbound_internal_to_external_recipient() -> None:
    feature = compute_email_mart_feature(
        **_feature_kwargs(
            sender="OrigenLab <contacto@origenlab.cl>",
            recipients="Buyer <buyer@external.cl>",
            top_reply_clean="outbound body",
        )
    )

    assert feature.direction == "outbound"
    assert feature.sender_email == "contacto@origenlab.cl"
    assert feature.sender_domain == "origenlab.cl"
    assert json.loads(feature.external_targets_json) == ["buyer@external.cl"]


def test_compute_internal_only_direction_and_empty_targets() -> None:
    feature = compute_email_mart_feature(
        **_feature_kwargs(
            sender="OrigenLab <contacto@origenlab.cl>",
            recipients="Ops <ops@origenlab.cl>",
            top_reply_clean="internal only",
        )
    )

    assert feature.direction == "outbound"
    assert json.loads(feature.external_targets_json) == []
    assert json.loads(feature.recipient_emails_json) == ["ops@origenlab.cl"]


def test_top_reply_clean_preferred_over_full_body_clean() -> None:
    assert select_mart_body_text("top", "full") == "top"
    feature = compute_email_mart_feature(**_feature_kwargs())
    assert feature.body_len == 8

    intents_top = compute_email_mart_feature(
        **_feature_kwargs(
            top_reply_clean="necesitamos cotización",
            full_body_clean="ignored invoice text",
            subject="Cotización",
        )
    )
    assert intents_top.is_quote_email == 1
    assert intents_top.is_invoice_email == 0


def test_full_body_clean_fallback_when_top_empty() -> None:
    assert select_mart_body_text("", "fallback body") == "fallback body"
    feature = compute_email_mart_feature(
        **_feature_kwargs(top_reply_clean="", full_body_clean="fallback body")
    )
    assert feature.body_len == 13

    intents_full = compute_email_mart_feature(
        **_feature_kwargs(
            top_reply_clean="",
            full_body_clean="necesitamos cotización",
            subject="Cotización",
        )
    )
    assert intents_full.is_quote_email == 1


def test_feature_source_hash_changes_when_subject_or_body_changes() -> None:
    base = compute_feature_source_hash(**_hash_kwargs())
    changed_subject = compute_feature_source_hash(**_hash_kwargs(subject="Changed"))
    changed_body = compute_feature_source_hash(**_hash_kwargs(top_reply_clean="different"))
    assert base != changed_subject
    assert base != changed_body
    assert changed_subject != changed_body


def test_feature_source_hash_unchanged_when_full_body_changes_but_top_nonempty() -> None:
    first = compute_feature_source_hash(
        **_hash_kwargs(top_reply_clean="top body", full_body_clean="full body")
    )
    second = compute_feature_source_hash(
        **_hash_kwargs(top_reply_clean="top body", full_body_clean="different full body")
    )
    assert first == second


def test_feature_source_hash_changes_when_top_empty_and_full_body_changes() -> None:
    first = compute_feature_source_hash(
        **_hash_kwargs(top_reply_clean="", full_body_clean="fallback body")
    )
    second = compute_feature_source_hash(
        **_hash_kwargs(top_reply_clean="", full_body_clean="different fallback body")
    )
    assert first != second


def test_feature_source_hash_changes_when_selected_top_reply_changes() -> None:
    first = compute_feature_source_hash(**_hash_kwargs(top_reply_clean="top body"))
    second = compute_feature_source_hash(**_hash_kwargs(top_reply_clean="other top body"))
    assert first != second


def test_json_fields_are_valid_deterministic_arrays() -> None:
    feature = compute_email_mart_feature(
        **_feature_kwargs(
            subject="Cotización espectrofotometro",
            top_reply_clean="necesitamos cotización",
        )
    )

    recipients = json.loads(feature.recipient_emails_json)
    targets = json.loads(feature.external_targets_json)
    tags = json.loads(feature.equipment_tags_json)

    assert isinstance(recipients, list)
    assert isinstance(targets, list)
    assert isinstance(tags, list)
    assert recipients == ["contacto@origenlab.cl"]
    assert targets == ["buyer@lab.cl"]
    assert tags == sorted(tags)
    assert "espectrofotometro" in tags

    again = compute_email_mart_feature(
        **_feature_kwargs(
            subject="Cotización espectrofotometro",
            top_reply_clean="necesitamos cotización",
        )
    )
    assert again.recipient_emails_json == feature.recipient_emails_json
    assert again.external_targets_json == feature.external_targets_json
    assert again.equipment_tags_json == feature.equipment_tags_json
    assert again.feature_source_hash == feature.feature_source_hash
