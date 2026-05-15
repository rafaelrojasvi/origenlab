"""Static checks for Alembic mart core dashboard tables (Slice 1 API)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIGRATION = REPO / "alembic" / "versions" / "20260515_0006_mart_core_dashboard_tables.py"


def test_mart_core_migration_file_exists() -> None:
    assert MIGRATION.is_file()


def test_mart_core_creates_dashboard_tables() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE mart.contact_master" in text
    assert "CREATE TABLE mart.organization_master" in text
    assert "CREATE TABLE mart.opportunity_signals" in text


def test_mart_core_indexes() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "idx_mart_contact_master_domain" in text
    assert "idx_mart_organization_master_last_seen" in text
    assert "idx_mart_opportunity_signals_entity" in text


def test_mart_core_revision_chain() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "20260515_0006"' in text
    assert 'down_revision: Union[str, Sequence[str], None] = "20260419_0005"' in text


def test_mart_core_no_archive_fk_on_contact_org() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "REFERENCES archive." not in text.split("mart.contact_master")[1].split("mart.organization_master")[0]
