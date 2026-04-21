"""Static checks for Alembic mart.document_master (Slice 2B); no DB required."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIGRATION = REPO / "alembic" / "versions" / "20260419_0003_mart_document_master.py"


def test_mart_document_master_migration_file_exists() -> None:
    assert MIGRATION.is_file()


def test_mart_document_master_creates_table_and_indexes() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE mart.document_master" in text
    assert "idx_mart_document_master_sender_domain" in text
    assert "idx_mart_document_master_recipient_domain" in text
    assert "idx_mart_document_master_sent_at" in text
    assert "idx_mart_document_master_doc_type" in text


def test_mart_document_master_references_archive() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "REFERENCES archive.attachments(id) ON DELETE CASCADE" in text
    assert "REFERENCES archive.emails(id) ON DELETE CASCADE" in text


def test_mart_document_master_no_other_mart_tables() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert text.count("CREATE TABLE mart.") == 1
    for other in (
        "contact_master",
        "organization_master",
        "opportunity_signals",
    ):
        assert f"CREATE TABLE mart.{other}" not in text


def test_mart_document_master_no_other_domain_tables() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    for bad in (
        "CREATE TABLE leads.",
        "CREATE TABLE commercial.",
        "CREATE TABLE outbound.",
        "CREATE TABLE supplier.",
        "CREATE TABLE archive.",
        "CREATE TABLE ops.",
    ):
        assert bad not in text


def test_mart_document_master_downgrade_safe() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    downgrade = text.split("def downgrade()")[1]
    assert "DROP SCHEMA" not in downgrade
    assert "CASCADE" not in downgrade


def test_mart_document_master_revision_chain() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "20260419_0003"' in text
    assert 'down_revision: Union[str, Sequence[str], None] = "20260419_0002"' in text


def test_mart_document_master_notes_no_sqlite_runtime() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "SQLite" in text or "sqlite" in text
