"""Static checks for Alembic archive slice 2A (emails / attachments / extracts); no DB required."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIGRATION = REPO / "alembic" / "versions" / "20260419_0002_archive_emails_attachments_extracts.py"


def test_archive_migration_file_exists() -> None:
    assert MIGRATION.is_file()


def test_archive_migration_creates_tables_and_indexes() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE archive.emails" in text
    assert "CREATE TABLE archive.attachments" in text
    assert "CREATE TABLE archive.attachment_extracts" in text
    assert "idx_archive_emails_message_id" in text
    assert "idx_archive_emails_date_iso" in text
    assert "idx_archive_emails_body_source_type" in text
    assert "idx_archive_emails_source_file_folder" in text
    assert "idx_archive_attachments_email_id" in text
    assert "idx_archive_attachments_sha256" in text
    assert "idx_archive_attachment_extracts_attachment_id" in text
    assert "idx_archive_attachment_extracts_doc_type" in text
    assert "idx_archive_attachment_extracts_status_method" in text


def test_archive_migration_message_id_not_unique() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert re.search(r"UNIQUE\s*\(\s*message_id\s*\)", text) is None
    assert re.search(r"message_id\s+TEXT\s+UNIQUE", text) is None


def test_archive_migration_expected_foreign_keys() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "REFERENCES archive.emails(id) ON DELETE CASCADE" in text
    assert "REFERENCES archive.attachments(id) ON DELETE CASCADE" in text


def test_archive_migration_downgrade_no_cascade() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    downgrade = text.split("def downgrade()")[1]
    assert "CASCADE" not in downgrade


def test_archive_migration_does_not_create_other_schemas_tables() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    for bad in (
        "CREATE TABLE mart.",
        "CREATE TABLE leads.",
        "CREATE TABLE commercial.",
        "CREATE TABLE outbound.",
        "CREATE TABLE supplier.",
        "document_master",
    ):
        assert bad not in text
    assert "DROP SCHEMA" not in text


def test_archive_migration_revision_chain() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "20260419_0002"' in text
    assert 'down_revision: Union[str, Sequence[str], None] = "20260419_0001"' in text
