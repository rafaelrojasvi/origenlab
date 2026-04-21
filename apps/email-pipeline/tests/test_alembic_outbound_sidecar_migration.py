"""Static checks for Alembic outbound durable sidecar migration (Slice 3A)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIGRATION = REPO / "alembic" / "versions" / "20260419_0004_outbound_durable_sidecar.py"


def test_outbound_sidecar_migration_file_exists() -> None:
    assert MIGRATION.is_file()


def test_outbound_sidecar_creates_expected_tables() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE outbound.contact_email_suppression" in text
    assert "CREATE TABLE outbound.contact_domain_suppression" in text
    assert "CREATE TABLE outbound.outreach_contact_state" in text


def test_outbound_sidecar_creates_expected_indexes() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "idx_outbound_contact_email_suppression_reason" in text
    assert "idx_outbound_outreach_contact_state_state" in text
    assert "idx_outbound_outreach_contact_state_lead_id" in text
    assert "WHERE lead_id IS NOT NULL" in text


def test_outbound_sidecar_no_outbound_batch_yet() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "outbound_batch" not in text


def test_outreach_contact_state_lead_id_has_no_fk() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    start = text.index("CREATE TABLE outbound.outreach_contact_state")
    end = text.index(")", start)
    block = text[start:end]
    assert "lead_id BIGINT" in block
    assert "REFERENCES" not in block


def test_outbound_sidecar_downgrade_safe() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    downgrade = text.split("def downgrade()")[1]
    assert "DROP SCHEMA" not in downgrade
    assert "CASCADE" not in downgrade


def test_outbound_sidecar_no_other_domain_tables() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    for bad in (
        "CREATE TABLE leads.",
        "CREATE TABLE commercial.",
        "CREATE TABLE supplier.",
        "CREATE TABLE mart.",
        "CREATE TABLE archive.",
    ):
        assert bad not in text


def test_outbound_sidecar_revision_chain() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "20260419_0004"' in text
    assert 'down_revision: Union[str, Sequence[str], None] = "20260419_0003"' in text
