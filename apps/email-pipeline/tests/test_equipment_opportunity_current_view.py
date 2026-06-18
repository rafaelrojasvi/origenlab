"""Tests for api.v_equipment_opportunity_current read model."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

# Integration tests against ORIGENLAB_TEST_POSTGRES_URL must never globally rewrite
# canonical source state (e.g. UPDATE ... SET is_canonical = FALSE). Prefer inserting
# isolated fixture rows and rolling back the transaction.


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


@pytest.mark.skipif(
    _postgres_test_url_ready() is None,
    reason="Set ORIGENLAB_TEST_POSTGRES_URL to a reachable disposable Postgres for integration tests.",
)
def test_current_view_returns_one_canonical_row_per_key_and_excludes_stale_keys() -> None:
    """Uses a rolled-back transaction; does not mutate pre-existing canonical sources."""
    pytest.importorskip("psycopg")
    from psycopg.types.json import Json

    from origenlab_email_pipeline.mart_core_postgres_migrate import normalize_postgres_url

    url = normalize_postgres_url(_postgres_test_url_ready())
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    key_canonical = f"equipment:equipment_queue:current-{suffix}"
    key_stale_only = f"equipment:equipment_queue:stale-{suffix}"
    # api.v_equipment_opportunity picks latest is_canonical=TRUE source by synced_at DESC.
    future_synced_at = datetime.now(timezone.utc) + timedelta(days=3650)

    import psycopg

    with psycopg.connect(url) as conn:
        conn.autocommit = False
        canonical_source_id: int | None = None
        stale_source_id: int | None = None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM information_schema.views
                    WHERE table_schema = 'api'
                      AND table_name = 'v_equipment_opportunity_current'
                    """
                )
                if cur.fetchone() is None:
                    conn.rollback()
                    pytest.skip("api.v_equipment_opportunity_current not migrated on test Postgres")

                cur.execute(
                    """
                    INSERT INTO commercial.equipment_opportunity_source (
                      manifest_path, csv_path, date_suffix, campaign_mode, row_count,
                      is_canonical, loader_version, source_kind, artifact_basename,
                      canonical_reason, synced_at
                    ) VALUES
                      (%s, %s, %s, 'equipment_first', 1, TRUE, 'pytest', 'csv_artifact', %s, 'manifest_canonical', %s),
                      (%s, %s, %s, 'equipment_first', 1, FALSE, 'pytest', 'csv_artifact', %s, NULL, %s)
                    RETURNING id, is_canonical
                    """,
                    (
                        f"/tmp/manifest_{suffix}.json",
                        f"/tmp/canonical_{suffix}.csv",
                        suffix,
                        f"canonical_{suffix}.csv",
                        future_synced_at,
                        f"/tmp/manifest_{suffix}.json",
                        f"/tmp/stale_{suffix}.csv",
                        f"{suffix}2",
                        f"stale_{suffix}.csv",
                        future_synced_at - timedelta(days=1),
                    ),
                )
                source_rows = cur.fetchall()
                canonical_source_id = next(int(row[0]) for row in source_rows if row[1] is True)
                stale_source_id = next(int(row[0]) for row in source_rows if row[1] is False)

                for source_id, key, codigo in (
                    (canonical_source_id, key_canonical, f"CUR-{suffix}"),
                    (stale_source_id, key_stale_only, f"STALE-{suffix}"),
                ):
                    cur.execute(
                        """
                        INSERT INTO commercial.equipment_opportunity (
                          source_id, opportunity_key, codigo_licitacion, buyer, extra_json
                        ) VALUES (%s, %s, %s, %s, %s)
                        """,
                        (source_id, key, codigo, "Buyer", Json({})),
                    )

                cur.execute(
                    """
                    SELECT opportunity_key
                    FROM api.v_equipment_opportunity_current
                    WHERE opportunity_key = ANY(%s)
                    ORDER BY opportunity_key
                    """,
                    ([key_canonical, key_stale_only],),
                )
                keys = [row[0] for row in cur.fetchall()]
                assert keys == [key_canonical]

                cur.execute(
                    """
                    SELECT count(*) = count(DISTINCT opportunity_key)
                    FROM api.v_equipment_opportunity_current
                    """
                )
                assert cur.fetchone()[0] is True
        finally:
            conn.rollback()
