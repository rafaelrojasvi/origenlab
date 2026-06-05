"""Tests for read-only NDR review queue generation."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import patch

from origenlab_email_pipeline.qa.ndr_review_queue import (
    APPLY_ONLY_CODE_BATCH_A,
    APPLY_ONLY_CODE_BATCH_B,
    apply_only_code_for_batch,
    build_ndr_review_queue,
    classify_ndr_candidate,
    write_approved_allowlist_template,
)


def test_batch_a_no_such_user_classification() -> None:
    batch, reason = classify_ndr_candidate(
        proposed_code="bounce_no_such_user",
        subject="Delivery Status Notification (Failure)",
        body_blob="550 5.1.1 User unknown",
        multi_recipient_uncertain=False,
    )
    assert batch == "A"
    assert reason == "no_such_user_final"


def test_batch_b_nxdomain_classification() -> None:
    batch, reason = classify_ndr_candidate(
        proposed_code="bounce_no_such_user",
        subject="DSN",
        body_blob="DNS type mx lookup responded with code NXDOMAIN",
        multi_recipient_uncertain=False,
    )
    assert batch == "B"
    assert reason == "nxdomain_or_domain_not_found"


def test_batch_c_mailbox_full_classification() -> None:
    batch, reason = classify_ndr_candidate(
        proposed_code="bounce_other",
        subject="DSN",
        body_blob="552 5.2.2 mailbox full",
        multi_recipient_uncertain=False,
    )
    assert batch == "C"
    assert reason == "mailbox_full_or_quota"


def test_batch_d_policy_access_classification() -> None:
    batch, reason = classify_ndr_candidate(
        proposed_code="bounce_access_denied",
        subject="DSN",
        body_blob="554 5.7.1 relay denied by policy",
        multi_recipient_uncertain=False,
    )
    assert batch == "D"
    assert reason in {"policy_or_access_denied", "access_denied_code"}


def test_delay_dsn_excluded_by_subject() -> None:
    batch, reason = classify_ndr_candidate(
        proposed_code="bounce_other",
        subject="Delivery Status Notification (Delay)",
        body_blob="still trying",
        multi_recipient_uncertain=False,
    )
    assert batch == "E"
    assert reason == "delay_dsn_excluded"


def _seed_db(db: Path) -> None:
    seed_date = date.today().isoformat()
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE emails (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            folder TEXT,
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
            body_has_html INTEGER,
            full_body_clean TEXT,
            top_reply_clean TEXT,
            attachment_count INTEGER,
            has_attachments INTEGER
        );
        CREATE TABLE contact_email_suppression (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            suppression_reason_code TEXT NOT NULL,
            suppression_reason_text TEXT,
            suppression_source TEXT,
            last_bounced_at TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT
        );
        """
    )
    # canonical contacto source_file prefix used by sql_predicate_contacto_gmail_source
    rows = [
        (
            1,
            "gmail:contacto@origenlab.cl/INBOX/file1.eml",
            "INBOX",
            "Delivery Status Notification (Failure)",
            "mailer-daemon@x",
            "",
            seed_date,
            seed_date,
            "Final-Recipient: rfc822; a@example.cl\n550 5.1.1 User unknown",
        ),
        (
            2,
            "gmail:contacto@origenlab.cl/INBOX/file2.eml",
            "INBOX",
            "Delivery Status Notification (Failure)",
            "mailer-daemon@x",
            "",
            seed_date,
            seed_date,
            "Final-Recipient: rfc822; b@example.cl\nDNS Error: code NXDOMAIN",
        ),
        (
            3,
            "gmail:contacto@origenlab.cl/INBOX/file3.eml",
            "INBOX",
            "Delivery Status Notification (Failure)",
            "mailer-daemon@x",
            "",
            seed_date,
            seed_date,
            "Final-Recipient: rfc822; c@example.cl\n552 5.2.2 mailbox full",
        ),
        (
            4,
            "gmail:contacto@origenlab.cl/INBOX/file4.eml",
            "INBOX",
            "Delivery Status Notification (Failure)",
            "mailer-daemon@x",
            "",
            seed_date,
            seed_date,
            "Final-Recipient: rfc822; d@example.cl\n554 5.7.1 relay denied",
        ),
        (
            5,
            "gmail:contacto@origenlab.cl/INBOX/file5.eml",
            "INBOX",
            "Delivery Status Notification (Failure)",
            "mailer-daemon@x",
            "",
            seed_date,
            seed_date,
            "Final-Recipient: rfc822; e@example.cl\nunknown weird response",
        ),
    ]
    for row in rows:
        conn.execute(
            """
            INSERT INTO emails (
                id, source_file, folder, subject, sender, recipients, date_raw, date_iso,
                body, body_text_clean, full_body_clean
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*row, row[8], row[8]),
        )
    conn.execute(
        """
        INSERT INTO contact_email_suppression (
            email, suppression_reason_code, suppression_reason_text, suppression_source, updated_by
        ) VALUES ('a@example.cl', 'bounce_no_such_user', 'preexisting', 'test', 'test')
        """
    )
    conn.commit()
    conn.close()


def test_already_suppressed_excluded_from_allowlists(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    _seed_db(db)
    out = tmp_path / "out"
    result = build_ndr_review_queue(
        sqlite_path=db,
        out_dir=out,
        since_days=2,
        date_label="2026_06_02",
    )
    assert "a@example.cl" not in result.allowlist_batch_a
    assert "b@example.cl" in result.allowlist_batch_b


def test_apply_only_code_per_batch() -> None:
    assert apply_only_code_for_batch("A") == APPLY_ONLY_CODE_BATCH_A
    assert apply_only_code_for_batch("B") == APPLY_ONLY_CODE_BATCH_B


def test_allowlist_batch_headers_use_correct_only_code(tmp_path: Path) -> None:
    db = tmp_path / "t_allow.txt"
    _seed_db(db)
    out = tmp_path / "out"
    build_ndr_review_queue(
        sqlite_path=db,
        out_dir=out,
        since_days=2,
        date_label="2026_06_02",
    )
    a_txt = (out / "apply_allowlist_batch_a.txt").read_text(encoding="utf-8")
    b_txt = (out / "apply_allowlist_batch_b.txt").read_text(encoding="utf-8")
    assert f"--only-code {APPLY_ONLY_CODE_BATCH_A}" in a_txt
    assert f"--only-code {APPLY_ONLY_CODE_BATCH_B}" in b_txt
    assert f"--only-code {APPLY_ONLY_CODE_BATCH_A}" not in b_txt


def test_approved_allowlist_template_headers(tmp_path: Path) -> None:
    path_a = tmp_path / "apply_allowlist_batch_a_APPROVED_TEMPLATE.txt"
    path_b = tmp_path / "apply_allowlist_batch_b_APPROVED_TEMPLATE.txt"
    write_approved_allowlist_template(path_a, "A", ["a@example.cl"])
    write_approved_allowlist_template(path_b, "B", ["b@example.cl"])
    a_txt = path_a.read_text(encoding="utf-8")
    b_txt = path_b.read_text(encoding="utf-8")
    assert f"--only-code {APPLY_ONLY_CODE_BATCH_A}" in a_txt
    assert f"--only-code {APPLY_ONLY_CODE_BATCH_B}" in b_txt
    assert "approves Batch A" in a_txt
    assert "approves Batch B" in b_txt


def test_allowlist_files_only_unsuppressed(tmp_path: Path) -> None:
    db = tmp_path / "t2.db"
    _seed_db(db)
    out = tmp_path / "out"
    build_ndr_review_queue(
        sqlite_path=db,
        out_dir=out,
        since_days=2,
        date_label="2026_06_02",
    )
    txt = (out / "apply_allowlist_batch_a.txt").read_text(encoding="utf-8")
    assert "a@example.cl" not in txt
    assert "DO NOT APPLY WITHOUT OPERATOR APPROVAL" in txt


def test_no_mutation_paths_called(tmp_path: Path) -> None:
    db = tmp_path / "t3.db"
    _seed_db(db)
    out = tmp_path / "out"
    with (
        patch("origenlab_email_pipeline.contact_email_suppression.upsert_contact_email_suppression") as upsert,
        patch("origenlab_email_pipeline.contact_domain_suppression.upsert_contact_domain_suppression") as upsert_domain,
    ):
        build_ndr_review_queue(
            sqlite_path=db,
            out_dir=out,
            since_days=2,
            date_label="2026_06_02",
        )
        upsert.assert_not_called()
        upsert_domain.assert_not_called()
