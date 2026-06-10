"""Parity tests: scan_email_contacts vs scan_email_contacts_from_features."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter

import pytest

from origenlab_email_pipeline.business_mart import DocAgg
from origenlab_email_pipeline.core.mart.build_email_mart_features_cli import (
    email_mart_feature_row_values,
)
from origenlab_email_pipeline.core.mart.build_options import MartBuildOptions
from origenlab_email_pipeline.core.mart.contact_org_builder import (
    scan_email_contacts,
    scan_email_contacts_from_features,
)
from origenlab_email_pipeline.core.mart.email_mart_features import compute_email_mart_feature
from origenlab_email_pipeline.core.mart.email_mart_features_schema import (
    ensure_email_mart_features_table,
)
from origenlab_email_pipeline.db import init_schema

_INTERNAL = frozenset({"origenlab.cl"})
_SLACK_DAYS = 30
_COMPUTED_AT = "2026-06-09T12:00:00+00:00"

_UPSERT_SQL = """
INSERT INTO email_mart_features (
  email_id, message_id, source_file, folder, sender_email, sender_domain,
  recipient_emails_json, external_targets_json, direction, is_noise,
  is_quote_email, is_invoice_email, is_purchase_email, equipment_tags_json,
  mart_date_iso, body_len, feature_source_hash, computed_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _default_options(**overrides: object) -> MartBuildOptions:
    base = {
        "internal_domains": _INTERNAL,
        "limit_emails": None,
        "dashboard_fast": False,
        "canonical_only": False,
        "since_days": None,
        "skip_document_master_if_unchanged": False,
        "mart_date_slack_days": _SLACK_DAYS,
        "use_email_mart_features": False,
    }
    base.update(overrides)
    return MartBuildOptions(**base)  # type: ignore[arg-type]


def _insert_email(
    conn: sqlite3.Connection,
    *,
    message_id: str,
    date_iso: str = "2026-06-01T10:00:00",
    sender: str = "Buyer <buyer@lab.cl>",
    recipients: str = "contacto@origenlab.cl",
    subject: str = "Subject",
    top_reply_clean: str = "top body",
    full_body_clean: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO emails (
          source_file, message_id, date_iso, folder, sender, recipients,
          subject, body, full_body_clean, top_reply_clean
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "gmail:contacto@origenlab.cl/INBOX",
            message_id,
            date_iso,
            "INBOX",
            sender,
            recipients,
            subject,
            top_reply_clean or full_body_clean or "",
            full_body_clean,
            top_reply_clean,
        ),
    )
    return int(cur.lastrowid)


def _upsert_feature_for_email(
    conn: sqlite3.Connection,
    email_id: int,
    *,
    message_id: str,
    sender: str,
    recipients: str,
    subject: str,
    top_reply_clean: str,
    full_body_clean: str,
    date_iso: str,
) -> None:
    feature = compute_email_mart_feature(
        email_id=email_id,
        message_id=message_id,
        source_file="gmail:contacto@origenlab.cl/INBOX",
        folder="INBOX",
        sender=sender,
        recipients=recipients,
        subject=subject,
        top_reply_clean=top_reply_clean,
        full_body_clean=full_body_clean,
        date_iso=date_iso,
        internal_domains=_INTERNAL,
        mart_date_slack_days=_SLACK_DAYS,
        computed_at=_COMPUTED_AT,
    )
    conn.execute(_UPSERT_SQL, email_mart_feature_row_values(feature))


def _seed_db_with_features(
    conn: sqlite3.Connection,
    emails: list[dict[str, object]],
) -> None:
    init_schema(conn)
    ensure_email_mart_features_table(conn)
    for spec in emails:
        email_id = _insert_email(
            conn,
            message_id=str(spec["message_id"]),
            date_iso=str(spec.get("date_iso", "2026-06-01T10:00:00")),
            sender=str(spec.get("sender", "Buyer <buyer@lab.cl>")),
            recipients=str(spec.get("recipients", "contacto@origenlab.cl")),
            subject=str(spec.get("subject", "Subject")),
            top_reply_clean=str(spec.get("top_reply_clean", "top body")),
            full_body_clean=str(spec.get("full_body_clean", "")),
        )
        _upsert_feature_for_email(
            conn,
            email_id,
            message_id=str(spec["message_id"]),
            sender=str(spec.get("sender", "Buyer <buyer@lab.cl>")),
            recipients=str(spec.get("recipients", "contacto@origenlab.cl")),
            subject=str(spec.get("subject", "Subject")),
            top_reply_clean=str(spec.get("top_reply_clean", "top body")),
            full_body_clean=str(spec.get("full_body_clean", "")),
            date_iso=str(spec.get("date_iso", "2026-06-01T10:00:00")),
        )
    conn.commit()


def _contact_snapshot(contact: dict[str, dict]) -> dict[str, dict]:
    snap: dict[str, dict] = {}
    for email, row in contact.items():
        snap[email] = {
            "domain": row["domain"],
            "org_name": row["org_name"],
            "org_type": row["org_type"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "total": row["total"],
            "inbound": row["inbound"],
            "outbound": row["outbound"],
            "quote_email": row["quote_email"],
            "invoice_email": row["invoice_email"],
            "purchase_email": row["purchase_email"],
            "business_doc_email": row["business_doc_email"],
            "quote_doc": row["quote_doc"],
            "invoice_doc": row["invoice_doc"],
            "equip": dict(row["equip"]),
        }
    return snap


def _assert_contact_maps_match(
    email_contact: dict[str, dict],
    feature_contact: dict[str, dict],
) -> None:
    assert set(email_contact) == set(feature_contact)
    for email in email_contact:
        assert _contact_snapshot({email: email_contact[email]}) == _contact_snapshot(
            {email: feature_contact[email]}
        )


def _run_both_scans(
    conn: sqlite3.Connection,
    doc_aggs: DocAgg,
) -> tuple[dict[str, dict], dict[str, dict]]:
    options = _default_options()
    email_contact, _ = scan_email_contacts(conn, options=options, doc_aggs=doc_aggs)
    feature_contact, _ = scan_email_contacts_from_features(conn, options=options, doc_aggs=doc_aggs)
    return email_contact, feature_contact


def test_feature_scan_inbound_external_quote_parity() -> None:
    conn = sqlite3.connect(":memory:")
    _seed_db_with_features(
        conn,
        [
            {
                "message_id": "inbound-quote",
                "subject": "Cotización",
                "top_reply_clean": "necesitamos cotización de equipos",
            }
        ],
    )
    email_contact, feature_contact = _run_both_scans(conn, DocAgg(set(), {}))
    conn.close()
    _assert_contact_maps_match(email_contact, feature_contact)
    assert email_contact["buyer@lab.cl"]["quote_email"] == 1
    assert email_contact["buyer@lab.cl"]["inbound"] == 1


def test_feature_scan_outbound_internal_to_external_parity() -> None:
    conn = sqlite3.connect(":memory:")
    _seed_db_with_features(
        conn,
        [
            {
                "message_id": "outbound-ext",
                "sender": "OrigenLab <contacto@origenlab.cl>",
                "recipients": "Buyer <buyer@external.cl>",
                "top_reply_clean": "follow up",
            }
        ],
    )
    email_contact, feature_contact = _run_both_scans(conn, DocAgg(set(), {}))
    conn.close()
    _assert_contact_maps_match(email_contact, feature_contact)
    assert email_contact["buyer@external.cl"]["outbound"] == 1


def test_feature_scan_internal_only_no_targets_parity() -> None:
    conn = sqlite3.connect(":memory:")
    _seed_db_with_features(
        conn,
        [
            {
                "message_id": "internal-only",
                "sender": "OrigenLab <contacto@origenlab.cl>",
                "recipients": "Ops <ops@origenlab.cl>",
                "top_reply_clean": "internal",
            }
        ],
    )
    email_contact, feature_contact = _run_both_scans(conn, DocAgg(set(), {}))
    conn.close()
    assert email_contact == {}
    assert feature_contact == {}


def test_feature_scan_noise_row_skipped_parity() -> None:
    conn = sqlite3.connect(":memory:")
    _seed_db_with_features(
        conn,
        [
            {
                "message_id": "noise-ndr",
                "sender": "Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
                "recipients": "contacto@origenlab.cl",
                "subject": "Delivery Status Notification",
                "top_reply_clean": "bounce notice",
            }
        ],
    )
    email_contact, feature_contact = _run_both_scans(conn, DocAgg(set(), {}))
    conn.close()
    assert email_contact == {}
    assert feature_contact == {}


def test_feature_scan_full_body_fallback_parity() -> None:
    conn = sqlite3.connect(":memory:")
    _seed_db_with_features(
        conn,
        [
            {
                "message_id": "full-quote",
                "subject": "Cotización",
                "top_reply_clean": "",
                "full_body_clean": "necesitamos cotización de equipos",
            }
        ],
    )
    email_contact, feature_contact = _run_both_scans(conn, DocAgg(set(), {}))
    conn.close()
    _assert_contact_maps_match(email_contact, feature_contact)
    assert email_contact["buyer@lab.cl"]["quote_email"] == 1


def test_feature_scan_date_first_last_seen_parity() -> None:
    conn = sqlite3.connect(":memory:")
    _seed_db_with_features(
        conn,
        [
            {
                "message_id": "early",
                "date_iso": "2026-05-01T09:00:00",
                "top_reply_clean": "hello",
            },
            {
                "message_id": "late",
                "date_iso": "2026-06-15T11:00:00",
                "top_reply_clean": "follow up",
            },
        ],
    )
    email_contact, feature_contact = _run_both_scans(conn, DocAgg(set(), {}))
    conn.close()
    _assert_contact_maps_match(email_contact, feature_contact)
    row = email_contact["buyer@lab.cl"]
    assert row["first_seen_at"] == "2026-05-01T09:00:00"
    assert row["last_seen_at"] == "2026-06-15T11:00:00"
    assert row["total"] == 2


def test_feature_scan_equipment_tags_parity() -> None:
    conn = sqlite3.connect(":memory:")
    _seed_db_with_features(
        conn,
        [
            {
                "message_id": "equip",
                "subject": "Cotizacion centrifuga",
                "top_reply_clean": "necesitamos centrifuga de laboratorio",
            }
        ],
    )
    email_contact, feature_contact = _run_both_scans(conn, DocAgg(set(), {}))
    conn.close()
    _assert_contact_maps_match(email_contact, feature_contact)
    assert email_contact["buyer@lab.cl"]["equip"].get("centrifuga", 0) >= 1


def test_feature_scan_doc_aggs_parity() -> None:
    conn = sqlite3.connect(":memory:")
    _seed_db_with_features(
        conn,
        [{"message_id": "doc-linked", "top_reply_clean": "see attachment"}],
    )
    doc_aggs = DocAgg(
        business_doc_email_ids={1},
        doc_counts_by_email={1: Counter({"quote": 2, "invoice": 1})},
    )
    email_contact, feature_contact = _run_both_scans(conn, doc_aggs)
    conn.close()
    _assert_contact_maps_match(email_contact, feature_contact)
    row = email_contact["buyer@lab.cl"]
    assert row["business_doc_email"] == 1
    assert row["quote_doc"] == 2
    assert row["invoice_doc"] == 1


def test_feature_scan_invalid_json_treated_as_empty(capsys: pytest.CaptureFixture[str]) -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    ensure_email_mart_features_table(conn)
    email_id = _insert_email(conn, message_id="bad-json", top_reply_clean="hello")
    conn.execute(
        _UPSERT_SQL,
        (
            email_id,
            "bad-json",
            "gmail:contacto@origenlab.cl/INBOX",
            "INBOX",
            "buyer@lab.cl",
            "lab.cl",
            '["contacto@origenlab.cl"]',
            "not-json",
            "inbound",
            0,
            0,
            0,
            0,
            "also-not-json",
            "2026-06-01",
            5,
            "hash",
            _COMPUTED_AT,
        ),
    )
    conn.commit()

    contact, scanned = scan_email_contacts_from_features(
        conn,
        options=_default_options(),
        doc_aggs=DocAgg(set(), {}),
    )
    conn.close()

    out = capsys.readouterr().out
    assert scanned == 1
    assert contact == {}
    assert "[mart-profile] feature_invalid_json_rows=1" in out


def test_feature_scan_prints_profile_lines(capsys: pytest.CaptureFixture[str]) -> None:
    conn = sqlite3.connect(":memory:")
    _seed_db_with_features(
        conn,
        [
            {
                "message_id": "one",
                "sender": "OrigenLab <contacto@origenlab.cl>",
                "recipients": "Buyer <buyer@external.cl>",
            }
        ],
    )
    scan_email_contacts_from_features(conn, options=_default_options(), doc_aggs=DocAgg(set(), {}))
    conn.close()
    out = capsys.readouterr().out
    assert "Scanned email mart features: 1" in out
    assert "[timing] email_feature_scan_seconds=" in out
    assert "[mart-profile] feature_noise_rows=0" in out
    assert "[mart-profile] feature_invalid_json_rows=0" in out
    assert "[mart-profile] feature_total_targets=1" in out
    assert "[mart-profile] feature_rows_with_targets=1" in out


def test_parse_feature_json_array_deterministic() -> None:
    from origenlab_email_pipeline.core.mart.contact_org_builder import _parse_feature_json_array

    items, invalid = _parse_feature_json_array(json.dumps(["a@b.cl", "c@d.cl"], separators=(",", ":")))
    assert items == ["a@b.cl", "c@d.cl"]
    assert invalid is False
