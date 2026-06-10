"""Tests for email mart feature scan parity audit."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.core.mart.build_email_mart_features_cli import (
    email_mart_feature_row_values,
)
from origenlab_email_pipeline.core.mart.build_options import MartBuildOptions
from origenlab_email_pipeline.core.mart.contact_org_builder import EmailMartFeaturesEmptyError
from origenlab_email_pipeline.core.mart.email_mart_feature_scan_parity import (
    compare_contact_maps,
    print_email_mart_feature_scan_parity_report,
    run_audit_email_mart_feature_scan_from_argv,
    run_email_mart_feature_scan_parity,
)
from origenlab_email_pipeline.core.mart.email_mart_features import compute_email_mart_feature
from origenlab_email_pipeline.core.mart.email_mart_features_schema import (
    ensure_email_mart_features_table,
)
from origenlab_email_pipeline.db import init_schema

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"
_SCRIPT = REPO / "scripts" / "qa" / "audit_email_mart_feature_scan.py"
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


def _seed_fixture_db(conn: sqlite3.Connection) -> None:
    init_schema(conn)
    ensure_email_mart_features_table(conn)
    specs = [
        {
            "message_id": "inbound-quote",
            "subject": "Cotización",
            "top_reply_clean": "necesitamos cotización de equipos",
        },
        {
            "message_id": "outbound-ext",
            "sender": "OrigenLab <contacto@origenlab.cl>",
            "recipients": "Buyer <buyer@external.cl>",
            "top_reply_clean": "follow up",
        },
        {
            "message_id": "internal-only",
            "sender": "OrigenLab <contacto@origenlab.cl>",
            "recipients": "Ops <ops@origenlab.cl>",
            "top_reply_clean": "internal",
        },
    ]
    for spec in specs:
        email_id = _insert_email(
            conn,
            message_id=str(spec["message_id"]),
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
            date_iso="2026-06-01T10:00:00",
        )
    conn.commit()


def _mart_table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in ("contact_master", "organization_master", "opportunity_signals"):
        counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return counts


def test_audit_cli_runner_importable() -> None:
    assert callable(run_audit_email_mart_feature_scan_from_argv)


def test_parity_success_on_fixture_db() -> None:
    conn = sqlite3.connect(":memory:")
    _seed_fixture_db(conn)

    report = run_email_mart_feature_scan_parity(conn, options=_default_options())
    conn.close()

    assert report.scanned_emails == 3
    assert report.scanned_features == 3
    assert report.contacts_old == report.contacts_feature
    assert report.contact_count_delta == 0
    assert report.mismatched_contacts == 0
    assert report.missing_in_feature == 0
    assert report.extra_in_feature == 0
    assert report.organization_count_delta == 0
    assert report.opportunity_signal_count_delta == 0
    assert not report.has_mismatch


def test_parity_report_output_contains_stable_counters(capsys: pytest.CaptureFixture[str]) -> None:
    conn = sqlite3.connect(":memory:")
    _seed_fixture_db(conn)
    report = run_email_mart_feature_scan_parity(conn, options=_default_options())
    conn.close()

    print_email_mart_feature_scan_parity_report(report)
    out = capsys.readouterr().out
    assert "email_mart_feature_scan_parity" in out
    assert "scanned_emails=3" in out
    assert "scanned_features=3" in out
    assert "contacts_old=" in out
    assert "contacts_feature=" in out
    assert "contact_count_delta=0" in out
    assert "mismatched_contacts=0" in out
    assert "elapsed_old_seconds=" in out
    assert "elapsed_feature_seconds=" in out


def test_mismatch_exits_non_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    _seed_fixture_db(conn)
    conn.execute(
        "UPDATE email_mart_features SET external_targets_json = '[]' WHERE email_id = 2"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(db))
    cp = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--internal-domain",
            "origenlab.cl",
        ],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(_SRC)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert cp.returncode == 1
    assert "email_mart_feature_scan_parity" in cp.stdout
    assert "mismatched_contacts=" in cp.stdout


def test_allow_mismatch_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    _seed_fixture_db(conn)
    conn.execute(
        "UPDATE email_mart_features SET external_targets_json = '[]' WHERE email_id = 2"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(db))
    cp = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--internal-domain",
            "origenlab.cl",
            "--allow-mismatch",
        ],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(_SRC)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert cp.returncode == 0, cp.stderr
    assert "mismatched_contacts=" in cp.stdout


def test_empty_feature_table_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    init_schema(conn)
    ensure_email_mart_features_table(conn)
    _insert_email(conn, message_id="only-email", top_reply_clean="hello")
    conn.commit()
    conn.close()

    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(db))
    cp = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--internal-domain",
            "origenlab.cl",
        ],
        cwd=str(REPO),
        env={**os.environ, "PYTHONPATH": str(_SRC)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    combined = cp.stdout + cp.stderr
    assert cp.returncode != 0
    assert "email_mart_features is empty; run build-email-mart-features --apply first" in combined


def test_audit_is_read_only_does_not_rebuild_mart_tables(tmp_path: Path) -> None:
    db = tmp_path / "emails.sqlite"
    conn = sqlite3.connect(db)
    _seed_fixture_db(conn)
    before = _mart_table_counts(conn)
    conn.execute(
        "INSERT INTO contact_master (email, domain) VALUES ('seed@example.com', 'example.com')"
    )
    conn.commit()
    before["contact_master"] += 1

    run_email_mart_feature_scan_parity(conn, options=_default_options())
    after = _mart_table_counts(conn)
    conn.close()

    assert after == before


def test_compare_contact_maps_detects_field_mismatch() -> None:
    from collections import Counter

    old = {
        "a@b.cl": {
            "domain": "b.cl",
            "org_name": "B",
            "org_type": "other",
            "first_seen_at": "2026-01-01",
            "last_seen_at": "2026-02-01",
            "total": 1,
            "inbound": 1,
            "outbound": 0,
            "quote_email": 0,
            "invoice_email": 0,
            "purchase_email": 0,
            "business_doc_email": 0,
            "quote_doc": 0,
            "invoice_doc": 0,
            "equip": Counter(),
        }
    }
    feature = {
        "a@b.cl": {
            **old["a@b.cl"],
            "quote_email": 1,
            "equip": Counter(),
        }
    }
    mismatched, missing, extra = compare_contact_maps(old, feature)
    assert mismatched == 1
    assert missing == 0
    assert extra == 0


def test_empty_features_raises_in_helper() -> None:
    conn = sqlite3.connect(":memory:")
    init_schema(conn)
    ensure_email_mart_features_table(conn)
    _insert_email(conn, message_id="x", top_reply_clean="body")
    conn.commit()

    with pytest.raises(EmailMartFeaturesEmptyError, match="email_mart_features is empty"):
        run_email_mart_feature_scan_parity(conn, options=_default_options())


def test_origenlab_subcommand_maps_to_script() -> None:
    from origenlab_email_pipeline.operator_cli.constants import SUBCOMMAND_SCRIPTS

    assert (
        SUBCOMMAND_SCRIPTS["audit-email-mart-feature-scan"]
        == "scripts/qa/audit_email_mart_feature_scan.py"
    )
