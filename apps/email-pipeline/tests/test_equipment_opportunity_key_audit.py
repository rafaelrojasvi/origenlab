"""Tests for equipment opportunity_key audit views and audit script."""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_ALEMBIC_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_equipment_opportunity_keys.py"


def _postgres_test_url_ready() -> str | None:
    url = (os.environ.get("ORIGENLAB_TEST_POSTGRES_URL") or "").strip()
    if not url:
        return None
    try:
        import psycopg

        from origenlab_email_pipeline.mart_core_postgres_migrate import normalize_postgres_url

        with psycopg.connect(normalize_postgres_url(url), connect_timeout=2):
            pass
        return url
    except Exception:
        return None


def _load_audit_script():
    spec = importlib.util.spec_from_file_location("audit_equipment_opportunity_keys", _SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_0029_migration_defines_audit_views_and_groups_by_opportunity_key() -> None:
    migration = (
        _ALEMBIC_VERSIONS / "20260617_0029_equipment_opportunity_key_audit_views.py"
    ).read_text(encoding="utf-8").lower()
    assert "commercial.v_equipment_opportunity_key_audit" in migration
    assert "api.v_equipment_opportunity_key_audit" in migration
    assert "group by eo.opportunity_key" in migration
    for column in (
        "row_count",
        "source_count",
        "canonical_row_count",
        "has_canonical",
        "source_artifacts",
        "canonical_reasons",
    ):
        assert column in migration
    assert "unique constraint" not in migration
    assert "add constraint" not in migration


def test_format_audit_row_includes_counts_and_artifacts() -> None:
    audit = _load_audit_script()
    line = audit.format_audit_row(
        {
            "opportunity_key": "equipment:equipment_queue:lp-001",
            "row_count": 2,
            "source_count": 2,
            "canonical_row_count": 1,
            "has_canonical": True,
            "codigo_licitacion": "LP-001",
            "sample_buyer": "Buyer One",
            "sample_equipment_category": "centrifuge",
            "source_artifacts": ["queue_a.csv", "queue_b.csv"],
            "canonical_reasons": ["manifest_canonical"],
            "last_synced_at": "2026-06-17T12:00:00+00:00",
        }
    )
    assert "rows=2" in line
    assert "sources=2" in line
    assert "has_canonical=True" in line
    assert "queue_a.csv" in line
    assert "manifest_canonical" in line


def test_main_skips_without_postgres_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    audit = _load_audit_script()
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    assert audit.main([]) == 0
    assert audit.SKIP_MESSAGE in capsys.readouterr().out


@pytest.mark.skipif(
    _postgres_test_url_ready() is None,
    reason="Set ORIGENLAB_TEST_POSTGRES_URL to a reachable disposable Postgres for integration tests.",
)
def test_key_audit_view_groups_repeated_opportunity_key_across_sources() -> None:
    pytest.importorskip("psycopg")
    from psycopg.types.json import Json

    from origenlab_email_pipeline.mart_core_postgres_migrate import normalize_postgres_url

    url = normalize_postgres_url(_postgres_test_url_ready())
    key = "equipment:equipment_queue:audit-key-001"
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    import psycopg

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM information_schema.views
                WHERE table_schema = 'api'
                  AND table_name = 'v_equipment_opportunity_key_audit'
                """
            )
            if cur.fetchone() is None:
                pytest.skip("api.v_equipment_opportunity_key_audit not migrated on test Postgres")

            cur.execute(
                """
                INSERT INTO commercial.equipment_opportunity_source (
                  manifest_path, csv_path, date_suffix, campaign_mode, row_count,
                  is_canonical, loader_version, source_kind, artifact_basename, canonical_reason
                ) VALUES
                  (%s, %s, %s, 'equipment_first', 1, TRUE, 'pytest', 'csv_artifact', %s, 'manifest_canonical'),
                  (%s, %s, %s, 'equipment_first', 1, FALSE, 'pytest', 'csv_artifact', %s, NULL)
                RETURNING id
                """,
                (
                    f"/tmp/manifest_{suffix}.json",
                    f"/tmp/queue_canonical_{suffix}.csv",
                    suffix,
                    f"queue_canonical_{suffix}.csv",
                    f"/tmp/manifest_{suffix}.json",
                    f"/tmp/queue_other_{suffix}.csv",
                    f"{suffix}2",
                    f"queue_other_{suffix}.csv",
                ),
            )
            source_ids = [int(row[0]) for row in cur.fetchall()]
            for source_id in source_ids:
                cur.execute(
                    """
                    INSERT INTO commercial.equipment_opportunity (
                      source_id, opportunity_key, codigo_licitacion, buyer,
                      equipment_category, extra_json
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source_id,
                        key,
                        "AUDIT-KEY-001",
                        "Audit Buyer",
                        "centrifuge",
                        Json({"title": "Audit title"}),
                    ),
                )
            cur.execute(
                """
                SELECT row_count, source_count, canonical_row_count, has_canonical
                FROM api.v_equipment_opportunity_key_audit
                WHERE opportunity_key = %s
                """,
                (key,),
            )
            row = cur.fetchone()
            assert row is not None
            row_count, source_count, canonical_row_count, has_canonical = row
            assert row_count == 2
            assert source_count == 2
            assert canonical_row_count == 1
            assert has_canonical is True
            cur.execute(
                """
                DELETE FROM commercial.equipment_opportunity
                WHERE opportunity_key = %s
                """,
                (key,),
            )
            cur.execute(
                """
                DELETE FROM commercial.equipment_opportunity_source
                WHERE id = ANY(%s)
                """,
                (source_ids,),
            )
        conn.commit()
