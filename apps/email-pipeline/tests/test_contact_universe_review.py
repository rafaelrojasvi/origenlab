"""Tests for read-only contact universe review export."""

from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from origenlab_email_pipeline.leads.contact_universe_review import (
    BUCKET_ACTIVE,
    BUCKET_BLOCKED,
    BUCKET_FOLLOWUP,
    BUCKET_NET_NEW,
    BucketInput,
    SourcePlanEntry,
    build_contact_universe_review,
    build_source_plan,
    classify_recommended_bucket,
    collect_candidates_from_sources,
    extract_emails_from_csv_row,
    extract_emails_from_json_value,
    is_redsalud_domain,
    normalize_review_domain,
    outreach_is_active_conversation,
    redsalud_family_label,
    source_skip_reason,
    write_contact_universe_review_outputs,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "leads" / "build_contact_universe_review.py"


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
        [
            SourcePlanEntry(csv_a, "active_current", scan=True, display_path="list_a.csv"),
            SourcePlanEntry(csv_b, "active_current", scan=True, display_path="list_b.csv"),
        ]
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


def test_outreach_contacted_is_followup_not_active_conversation() -> None:
    assert outreach_is_active_conversation("contacted", warm=False) is False
    inp = BucketInput(
        email="a@b.cl",
        sent_count=2,
        inbound_count=0,
        has_active_or_warm_case=False,
    )
    bucket, _reason = classify_recommended_bucket(inp)
    assert bucket == BUCKET_FOLLOWUP


def test_outreach_replied_and_warm_are_active_conversation() -> None:
    assert outreach_is_active_conversation("replied", warm=False) is True
    assert outreach_is_active_conversation("contacted", warm=True) is True


def test_redsalud_domain_normalization_preserves_variants() -> None:
    for domain in ("redsalud.gob.cl", "redsalud.gov.cl", "redsalud.cl"):
        assert is_redsalud_domain(domain)
        assert normalize_review_domain(domain) == domain
        assert redsalud_family_label(domain) == domain
    assert redsalud_family_label("procurement.redsalud.gob.cl") == "redsalud.gob.cl"
    assert normalize_review_domain("user@redsalud.gov.cl") == "redsalud.gov.cl"


def test_source_skip_reason_blocks_noisy_paths(tmp_path: Path) -> None:
    repo = tmp_path
    lic = repo / "reports/local/lic_2024.csv"
    lic.parent.mkdir(parents=True)
    lic.write_text("contact_email\nx@y.cl\n", encoding="utf-8")
    assert source_skip_reason(lic, repo) == "skipped_hard_path:reports/local"

    huge = repo / "reports/out/archive/research/huge.csv"
    huge.parent.mkdir(parents=True)
    huge.write_bytes(b"x" * (26 * 1024 * 1024))
    assert source_skip_reason(huge, repo) == "skipped_size_cap"

    tests_csv = repo / "tests/fixtures/sample.csv"
    tests_csv.parent.mkdir(parents=True)
    tests_csv.write_text("email\na@b.cl\n", encoding="utf-8")
    assert source_skip_reason(tests_csv, repo) == "skipped_hard_path:tests"


def test_inventory_noise_paths_not_scanned_by_default(tmp_path: Path) -> None:
    repo = tmp_path
    active = repo / "reports/out/active/current"
    active.mkdir(parents=True)

    noisy = repo / "reports/local/lic_2024.csv"
    noisy.parent.mkdir(parents=True)
    noisy.write_text("contact_email\nnoise@chilecompra.cl\n", encoding="utf-8")

    inventory = [
        "reports/local/lic_2024.csv",
        "tests/fixtures/noise.csv",
    ]
    (active / "contact_csv_inventory.json").write_text(json.dumps(inventory), encoding="utf-8")

    json_dir = repo / "scripts/leads/campaigns/data"
    json_dir.mkdir(parents=True)
    (json_dir / "redsalud_campaign.json").write_text(
        json.dumps([{"contact_email": "admin@redsalud.gob.cl", "institution_name": "RedSalud"}]),
        encoding="utf-8",
    )

    (active / "all_known_marketing_contacts_dedup.csv").write_text(
        "contact_email,institution_name\nother@test.cl,Other\n",
        encoding="utf-8",
    )

    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()

    plan = build_source_plan(repo, active_current=active, include_inventory_sources=False)
    inventory_entries = [e for e in plan if e.source_type == "inventory"]
    assert inventory_entries
    assert all(not e.scan for e in inventory_entries)
    assert all("inventory_not_scanned_by_default" in e.notes for e in inventory_entries)

    result = build_contact_universe_review(
        repo_root=repo,
        sqlite_path=db,
        active_current=active,
        gmail_user="contacto@origenlab.cl",
        sent_folders=("[Gmail]/Enviados",),
        now=datetime(2026, 6, 11, tzinfo=UTC),
    )

    emails = {row["email"] for row in result.candidates}
    assert "noise@chilecompra.cl" not in emails
    assert "admin@redsalud.gob.cl" in emails

    inv_rows = [r for r in result.source_inventory if r["source_type"] == "inventory"]
    assert inv_rows
    assert any("inventory_not_scanned_by_default" in r["notes"] for r in inv_rows)
    assert any("would_skip" in r["notes"] for r in inv_rows)


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
            "contacted_only@test.cl",
            "contacto@origenlab.cl",
            "Prior send",
            "gmail:contacto@origenlab.cl/inbox.mbox",
            "[Gmail]/Enviados",
            "2026-01-10T10:00:00+00:00",
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
    conn.execute(
        """
        INSERT INTO outreach_contact_state (contact_email_norm, state, source)
        VALUES (?, ?, ?)
        """,
        ("contacted_only@test.cl", "contacted", "test"),
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
        "contacted_only@test.cl,Hospital Contacted\n"
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
    assert by_email["contacted_only@test.cl"]["recommended_bucket"] == BUCKET_FOLLOWUP
    assert by_email["contacted_only@test.cl"]["has_active_or_warm_case"] == "false"
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

    assert any(r.get("email") == "admin@redsalud.gob.cl" for r in result.redsalud_examples)

    payload = json.loads(json.dumps(result.summary))
    assert payload["total_candidates"] >= 4
    assert payload["followup_candidates"] >= 1
    assert payload["include_inventory_sources"] is False


def test_contact_universe_review_script_read_only_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    active = tmp_path / "active" / "current"
    active.mkdir(parents=True)
    (active / "all_known_marketing_contacts_dedup.csv").write_text(
        "contact_email,institution_name\nsmoke@test.cl,Smoke\n",
        encoding="utf-8",
    )
    db = tmp_path / "smoke.sqlite"
    sqlite3.connect(db).close()

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db),
            "--active-current",
            str(active),
            "--out-dir",
            str(active / "contact_universe_review"),
            "--json",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["total_candidates"] >= 1
    assert (active / "contact_universe_review" / "all_candidate_emails.csv").is_file()

    db_mtime = db.stat().st_mtime
    proc2 = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db),
            "--active-current",
            str(active),
            "--json",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc2.returncode == 0, proc2.stderr
    assert db.stat().st_mtime == db_mtime
