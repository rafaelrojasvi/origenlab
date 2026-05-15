"""Static checks for canonical mart mirror migration."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIGRATION = REPO / "alembic" / "versions" / "20260516_0007_mart_canonical_mirror_tables.py"


def test_canonical_migration_exists() -> None:
    assert MIGRATION.is_file()
    text = MIGRATION.read_text(encoding="utf-8")
    assert "mart.contact_master_canonical" in text
    assert "mart.organization_master_canonical" in text
    assert "mart.opportunity_signals_canonical" in text
    assert 'down_revision' in text and "20260515_0006" in text
