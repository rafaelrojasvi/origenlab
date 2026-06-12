"""Tests for read-only contact universe review export."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from origenlab_email_pipeline.leads.contact_universe_review import (
    BUCKET_ACTIVE,
    BUCKET_BLOCKED,
    BUCKET_FOLLOWUP,
    BUCKET_NET_NEW,
    BucketInput,
    build_contact_universe_review,
    classify_recommended_bucket,
    collect_candidates_from_sources,
    extract_emails_from_csv_row,
    extract_emails_from_json_value,
    is_redsalud_domain,
    normalize_review_domain,
    redsalud_family_label,
    write_contact_universe_review_outputs,
)


def test_extract_emails_from_csv_row_dedupes_and_normalizes() -> None:
    row = {
        "contact_email": "Alice@Example.COM, bob@example.com",
        "email": "alice@example.com",
    }
    emails = extract_emails_from_csv_row(row)
    assert emails == ["alice@example.com", "bob@example.com"]


def test_extract_emails_from_json_nested_keys() -> None:
    payload = [
        {"buyer_email": "buyer@hospital.cl", "notes": "ignore"},
        {"technical_email": "", "general_contact_email": "lab@clinic.cl"},
    ]
    emails = extract_emails_from_json_value(payload)
    assert sorted(emails) == ["buyer@hospital.cl", "lab@clinic.cl"]


def test_collect_candidates_from_sources_merges_sources(tmp_path: Path) -> None:
    csv_a = tmp_path / "list_a.csv"
    csv_b = tmp_path / "list_b.csv"
    csv_a.write_text(
        "contact_email,institution_name\nalpha@test.cl,Hospital A\n",
        encoding="utf-8",
    )
    csv_b.write_text(
        "email,organization\nalpha@test.cl,Hospital A\nbeta@test.cl,Hospital B\n",
        encoding="utf-8",
    )
    store, inventory = collect_candidates_from_sources(
        [(csv_a, "active_current"), (csv_b, "active_current")]
    )
    assert len(store) == 2
    assert store["alpha@test.cl"].source_count == 2
    assert "list_a.csv" in store["alpha@test.cl"].source_files
    assert "list_b.csv" in store["alpha@test.cl"].source_files
    assert inventory[0]["emails_extracted"] == "1"
    assert inventory[1]["emails_extracted"] == "2"


@pytest.mark.parametrize(
    ("inp", "expected_bucket"),
    [
        (
            BucketInput(email="a@b.cl", sent_count=2, inbound_count=0),
            BUCKET_FOLLOWUP,
        ),
        (
            BucketInput(email="a@b.cl", sent_count=0, inbound_count=0),
            BUCKET_NET_NEW,
        ),
        (
            BucketInput(email="a@b.cl", suppressed_email=True),
            BUCKET_BLOCKED,
        ),
        (
            BucketInput(email="a@b.cl", bounced=True),
            BUCKET_BLOCKED,
        ),
        (
            BucketInput(email="a@b.cl", has_response=True),
            BUCKET_ACTIVE,
        ),
        (
            BucketInput(email="a@b.cl", has_active_or_warm_case=True),
            BUCKET_ACTIVE,
        ),
    ],
)
def test_classify_recommended_bucket_cases(inp: BucketInput, expected_bucket: str) -> None:
    bucket, _reason = classify_recommended_bucket(inp)
    assert bucket == expected_bucket


def test_redsalud_domain_normalization_preserves_variants() -> None:
    for domain in ("redsalud.gob.cl", "redsalud.gov.cl", "redsalud.cl"):
        assert is_redsalud_domain(domain)
        assert normalize_review_domain(domain) == domain
        assert redsalud_family_label(domain) == domain
    assert redsalud_family_label("procurement.redsalud.gob.cl") == "redsalud.gob.cl"
    assert normalize_review_domain("user@redsalud.gov.cl") == "redsalud.gov.cl"


def _seed_sqlite(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          recipients TEXT,
          sender TEXT,
          subject TEXT,
          source_file TEXT,
          folder TEXT,
          date_raw TEXT,
          date_iso TEXT
        );
        CREATE TABLE contact_email_suppression (
          email TEXT PRIMARY KEY,
          suppression_reason_code TEXT NOT NULL,
          suppression_reason_text TEXT,
          suppression_source TEXT,
          last_bounced_at TEXT,
          updated_at TEXT NOT NULL,
          updated_by TEXT
        );
        CREATE TABLE contact_domain_suppression (
          domain_norm TEXT PRIMARY KEY,
          suppression_reason_text TEXT,
          updated_at TEXT NOT NULL,
          updated_by TEXT
        );
        CREATE TABLE outreach_contact_state (
          contact_email_norm TEXT PRIMARY KEY,
          state TEXT NOT NULL,
          source TEXT,
          first_contacted_at TEXT,
          last_contacted_at TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO emails (recipients, sender, subject, source_file, folder, date_iso)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "followup@test.cl",
            "contacto@origenlab.cl",
            "Follow up",
            "gmail:contacto@origenlab.cl/inbox.mbox",
            "[Gmail]/Enviados",
            "2026-01-15T10:00:00+00:00",
        ),
    )
    conn.execute(
        """
        INSERT INTO emails (recipients, sender, subject, source_file, folder, date_iso)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "",
            "active@test.cl",
            "Re: quote",
            "gmail:contacto@origenlab.cl/inbox.mbox",
            "INBOX",
            "2026-02-01T12:00:00+00:00",
        ),
    )
    conn.execute(
        """
        INSERT INTO contact_email_suppression (email, suppression_reason_code, updated_at, updated_by)
        VALUES (?, ?, ?, ?)
        """,
        ("blocked@test.cl", "bounce_no_such_user", "2026-01-01", "test"),
    )
    conn.commit()
    conn.close()


def test_build_contact_universe_review_end_to_end(tmp_path: Path) -> None:
    active = tmp_path / "active" / "current"
    active.mkdir(parents=True)
    (active / "all_known_marketing_contacts_dedup.csv").write_text(
        "contact_email,institution_name\n"
        "netnew@test.cl,Clinica Nueva\n"
        "followup@test.cl,Hospital Viejo\n"
        "blocked@test.cl,Hospital Blocked\n"
        "active@test.cl,Hospital Activo\n"
        "admin@redsalud.gob.cl,RedSalud\n"
        "procurement@redsalud.gov.cl,RedSalud Gov\n"
        "info@redsalud.cl,RedSalud CL\n",
        encoding="utf-8",
    )
    db = tmp_path / "test.sqlite"
    _seed_sqlite(db)

    result = build_contact_universe_review(
        repo_root=tmp_path,
        sqlite_path=db,
        active_current=active,
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados",),
        now=datetime(2026, 6, 11, tzinfo=UTC),
    )

    by_email = {row["email"]: row for row in result.candidates}
    assert by_email["followup@test.cl"]["recommended_bucket"] == BUCKET_FOLLOWUP
    assert by_email["netnew@test.cl"]["recommended_bucket"] == BUCKET_NET_NEW
    assert by_email["blocked@test.cl"]["recommended_bucket"] == BUCKET_BLOCKED
    assert by_email["active@test.cl"]["recommended_bucket"] == BUCKET_ACTIVE

    out_dir = active / "contact_universe_review"
    paths = write_contact_universe_review_outputs(result, out_dir)
    assert paths["summary_md"].is_file()
    assert paths["all_candidates"].is_file()
    with paths["all_candidates"].open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert "recommended_bucket" in reader.fieldnames
        rows = list(reader)
    assert len(rows) >= 4

    redsalud_domains = {r["domain"] for r in result.redsalud_examples if r["email"]}
    assert "redsalud.gob.cl" in redsalud_domains or any(
        "redsalud" in (r.get("domain") or "") for r in result.redsalud_examples
    )
    assert any(r.get("email") == "admin@redsalud.gob.cl" for r in result.redsalud_examples)

    payload = json.loads(json.dumps(result.summary))
    assert payload["total_candidates"] >= 4
    assert payload["followup_candidates"] >= 1
