"""Static checks for Alembic outbound export audit migration (Slice 3B)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIGRATION = REPO / "alembic" / "versions" / "20260419_0005_outbound_export_audit_tables.py"


def test_outbound_export_audit_migration_file_exists() -> None:
    assert MIGRATION.is_file()


def test_outbound_export_audit_creates_tables() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE outbound.outbound_batch" in text
    assert "CREATE TABLE outbound.outbound_batch_recipient" in text


def test_outbound_batch_has_jsonb_and_text_array() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "sent_preflight_json JSONB NOT NULL" in text
    assert "sent_folders TEXT[] NOT NULL" in text


def test_outbound_batch_recipient_fk_to_batch() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "batch_id BIGINT NOT NULL REFERENCES outbound.outbound_batch(id) ON DELETE CASCADE" in text


def test_outbound_batch_recipient_has_lead_id_without_fk() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "lead_id BIGINT" in text
    assert "lead_id BIGINT REFERENCES" not in text
    assert "REFERENCES leads." not in text


def test_outbound_batch_recipient_unique_batch_email_exists() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX uq_outbound_batch_recipient_batch_email" in text
    assert "ON outbound.outbound_batch_recipient(batch_id, email_norm)" in text


def test_outbound_export_audit_indexes_exist() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    for idx in (
        "idx_outbound_batch_lane_created_at",
        "idx_outbound_batch_created_at",
        "idx_outbound_batch_recipient_batch_id",
        "idx_outbound_batch_recipient_email_norm",
        "idx_outbound_batch_recipient_lead_id",
        "idx_outbound_batch_recipient_eligibility_result",
        "idx_outbound_batch_recipient_exclusion_reason",
    ):
        assert idx in text
    assert "WHERE lead_id IS NOT NULL" in text


def test_outbound_export_audit_no_schema_drops_in_downgrade() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    downgrade = text.split("def downgrade()")[1]
    assert "DROP SCHEMA" not in downgrade
    assert "CASCADE" not in downgrade


def test_outbound_export_audit_no_other_domain_tables() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    for bad in (
        "CREATE TABLE leads.",
        "CREATE TABLE commercial.",
        "CREATE TABLE supplier.",
    ):
        assert bad not in text


def test_outbound_export_audit_revision_chain() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "20260419_0005"' in text
    assert 'down_revision: Union[str, Sequence[str], None] = "20260419_0004"' in text
