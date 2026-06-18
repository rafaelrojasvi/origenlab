"""DB-1 preflight static checks (no live Postgres required)."""

from __future__ import annotations

from pathlib import Path

FORBIDDEN_BODY_COLUMNS = frozenset(
    {
        "body",
        "body_html",
        "body_text_raw",
        "body_text_clean",
        "full_body_clean",
        "top_reply_clean",
        "raw_json",
    }
)

_ALEMBIC_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

DB1_MIGRATION_GLOBS = (
    "20260519_0011_api_schema.py",
    "20260519_0012_commercial_equipment_opportunity.py",
    "20260519_0013_commercial_warm_case.py",
    "20260519_0014_api_read_model_views.py",
    "20260519_0015_api_performance_indexes.py",
    "20260519_0016_api_readonly_grants.py",
)


def _db1_migration_sql() -> str:
    parts: list[str] = []
    for name in DB1_MIGRATION_GLOBS:
        path = _ALEMBIC_VERSIONS / name
        assert path.is_file(), f"missing migration file: {path}"
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts).lower()


def _db1_sql_execute_blocks() -> str:
    """Alembic op.execute(...) SQL only (excludes module docstrings)."""
    blocks: list[str] = []
    for name in DB1_MIGRATION_GLOBS:
        text = (_ALEMBIC_VERSIONS / name).read_text(encoding="utf-8")
        for segment in text.split("op.execute(")[1:]:
            if '"""' not in segment:
                continue
            sql = segment.split('"""', 2)[1]
            blocks.append(sql)
    return "\n".join(blocks).lower()


def test_db1_migrations_do_not_reference_commercial_case_table() -> None:
    sql = _db1_migration_sql()
    assert "commercial.case" not in sql
    assert "commercial.warm_case" in sql


def test_db1_migrations_do_not_select_forbidden_body_columns() -> None:
    sql = _db1_sql_execute_blocks()
    for col in FORBIDDEN_BODY_COLUMNS:
        assert col not in sql, f"DB-1 migration SQL must not reference {col!r}"


def test_db1_v_recent_email_view_has_no_hardcoded_2026_floor() -> None:
    views = (_ALEMBIC_VERSIONS / "20260519_0014_api_read_model_views.py").read_text(encoding="utf-8")
    views_lower = views.lower()
    start = views_lower.find("create or replace view api.v_recent_email")
    end = views_lower.find("create or replace view api.v_outreach_safety", start)
    assert start >= 0 and end > start
    recent_block = views_lower[start:end]
    assert "date_iso >= '2026-01-01'" not in recent_block


def test_db1_v_equipment_opportunity_joins_source_id_not_date_suffix() -> None:
    views = (_ALEMBIC_VERSIONS / "20260519_0014_api_read_model_views.py").read_text(encoding="utf-8").lower()
    assert "date_suffix = src.date_suffix" not in views
    assert "join latest_source ls on src.id = ls.id" in views


def test_0024_v_equipment_opportunity_appends_extra_json_at_end() -> None:
    """CREATE OR REPLACE VIEW cannot insert columns before existing view columns."""
    migration = (
        _ALEMBIC_VERSIONS / "20260614_0024_api_v_equipment_opportunity_extra_json.py"
    ).read_text(encoding="utf-8")
    upgrade_start = migration.index("def upgrade()")
    downgrade_start = migration.index("def downgrade()")
    upgrade_block = migration[upgrade_start:downgrade_start]
    assert "eo.operator_note,\n          eo.extra_json," not in upgrade_block
    assert upgrade_block.index("source_path") < upgrade_block.index("extra_json")
    assert upgrade_block.index("is_canonical_source") < upgrade_block.index("extra_json")


def test_0026_v_equipment_opportunity_appends_source_metadata_at_end() -> None:
    migration = (
        _ALEMBIC_VERSIONS / "20260617_0026_api_v_equipment_opportunity_source_metadata.py"
    ).read_text(encoding="utf-8")
    upgrade_start = migration.index("def upgrade()")
    downgrade_start = migration.index("def downgrade()")
    upgrade_block = migration[upgrade_start:downgrade_start]
    select_start = upgrade_block.index("eo.id AS opportunity_id")
    select_block = upgrade_block[select_start:]
    assert select_block.index("eo.extra_json") < select_block.index("ls.source_kind")
    assert select_block.index("ls.source_kind") < select_block.index("ls.artifact_basename")
    assert select_block.index("ls.artifact_basename") < select_block.index("ls.canonical_reason")


def test_0025_equipment_source_artifact_metadata_backfill() -> None:
    migration = (
        _ALEMBIC_VERSIONS / "20260617_0025_equipment_source_artifact_metadata.py"
    ).read_text(encoding="utf-8").lower()
    assert "source_kind" in migration
    assert "artifact_basename" in migration
    assert "existing_canonical_source" in migration
    assert "regexp_replace(csv_path" in migration


def test_db1_v_contact_profile_has_no_with_params_cte() -> None:
    views = (_ALEMBIC_VERSIONS / "20260519_0014_api_read_model_views.py").read_text(encoding="utf-8").lower()
    start = views.find("create or replace view api.v_contact_profile")
    end = views.find("def downgrade", start)
    block = views[start:end]
    assert "with params as" not in block


def test_db1_warm_case_indexes_present() -> None:
    warm = (_ALEMBIC_VERSIONS / "20260519_0013_commercial_warm_case.py").read_text(encoding="utf-8")
    assert "idx_warm_case_last_activity" in warm
    assert "idx_warm_case_open" in (_ALEMBIC_VERSIONS / "20260519_0015_api_performance_indexes.py").read_text(
        encoding="utf-8"
    )
