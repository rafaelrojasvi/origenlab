"""DB-3C: Postgres warm cases repository."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator
from unittest.mock import patch

import pytest

from origenlab_api.backends.factory import get_repository_bundle
from origenlab_api.repositories.postgres.warm_cases import (
    PostgresWarmCaseRepository,
    build_warm_cases_meta,
    map_warm_case_row,
    utc_cutoff,
)
from origenlab_api.repositories.sqlite.warm_cases import SqliteWarmCaseRepository
from origenlab_api.settings import Settings


def _fixture_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "case_id": "case:42",
        "last_email_id": 1001,
        "last_seen_at": datetime(2026, 5, 19, 14, 0, tzinfo=timezone.utc),
        "account_name": "Kelly Liu",
        "contact_email": "kelly@supplier.com",
        "subject": "Re: Ollital reactor 5L",
        "category": "supplier_reply",
        "status": "open",
        "next_action": "follow_up",
        "equipment_signal": "reactor",
        "snippet": "Re: Ollital reactor 5L",
        "gmail_url": None,
    }
    base.update(overrides)
    return base


def test_map_warm_case_row_fixture() -> None:
    item = map_warm_case_row(_fixture_row())
    assert item.case_id == "case:42"
    assert item.last_email_id == 1001
    assert item.category == "supplier_reply"
    assert item.last_seen_at is not None
    assert "2026-05-19" in item.last_seen_at


def test_build_warm_cases_meta_empty_has_note() -> None:
    meta = build_warm_cases_meta(items=[])
    assert meta.data_source == "postgres_mirror"
    assert meta.enrichment_available is True
    assert meta.reduced_mode is True
    assert "include-warm-cases" in meta.note


def test_build_warm_cases_meta_with_rows() -> None:
    item = map_warm_case_row(_fixture_row())
    meta = build_warm_cases_meta(items=[item])
    assert meta.reduced_mode is False
    assert meta.count == 1


def test_repository_bundle_default_uses_sqlite_warm_cases(tmp_path: Path) -> None:
    settings = Settings(
        api_backend="sqlite",
        sqlite_path=tmp_path / "x.sqlite",
    )
    bundle = get_repository_bundle(settings)
    assert isinstance(bundle.warm_cases, SqliteWarmCaseRepository)


def test_repository_bundle_postgres_uses_postgres_warm_cases() -> None:
    settings = Settings(
        api_backend="postgres",
        postgres_url="postgresql://127.0.0.1:5432/scratch",
    )
    bundle = get_repository_bundle(settings)
    assert isinstance(bundle.warm_cases, PostgresWarmCaseRepository)


@contextmanager
def _fake_postgres_connection(rows: list[dict[str, Any]]) -> Iterator[Any]:
    class FakeCursor:
        def __init__(self) -> None:
            self.last_sql = ""
            self.last_params: dict[str, Any] = {}

        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, sql: str, params: dict[str, Any]) -> None:
            self.last_sql = sql
            self.last_params = params

        def fetchall(self) -> list[dict[str, Any]]:
            return rows

    class FakeConn:
        def __init__(self) -> None:
            self.last_cursor: FakeCursor | None = None

        def cursor(self, *, row_factory: Any = None) -> FakeCursor:
            self.last_cursor = FakeCursor()
            return self.last_cursor

        def __enter__(self) -> FakeConn:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    fake = FakeConn()

    @contextmanager
    def _connect(_settings: Settings) -> Iterator[FakeConn]:
        yield fake

    with patch(
        "origenlab_api.repositories.postgres.warm_cases.postgres_connection",
        _connect,
    ):
        yield fake


def test_postgres_warm_cases_queries_view() -> None:
    settings = Settings(
        api_backend="postgres",
        postgres_url="postgresql://127.0.0.1:5432/test",
    )
    repo = PostgresWarmCaseRepository(settings)
    with _fake_postgres_connection([_fixture_row()]) as conn:
        items, meta = repo.list_warm_cases(
            days=14,
            limit=10,
            category="supplier_reply",
            positive_signal_only=True,
            include_noise=False,
        )
        cur = conn.last_cursor
    assert cur is not None
    assert "api.v_warm_case" in cur.last_sql
    assert "last_seen_at >= %(cutoff)s" in cur.last_sql
    assert cur.last_params["category"] == "supplier_reply"
    assert cur.last_params["include_noise"] is False
    assert "positive_categories" not in cur.last_params
    assert cur.last_params["limit"] == 40
    assert len(items) == 1
    assert meta.data_source == "postgres_mirror"


def test_postgres_warm_cases_no_rows_graceful() -> None:
    settings = Settings(
        api_backend="postgres",
        postgres_url="postgresql://127.0.0.1:5432/test",
    )
    repo = PostgresWarmCaseRepository(settings)
    with _fake_postgres_connection([]):
        items, meta = repo.list_warm_cases(days=7, limit=5)
    assert items == []
    assert meta.count == 0
    assert meta.reduced_mode is True
    assert meta.note


def test_postgres_warm_cases_include_noise_false_excludes_bounce_problem_in_sql() -> None:
    settings = Settings(
        api_backend="postgres",
        postgres_url="postgresql://127.0.0.1:5432/test",
    )
    repo = PostgresWarmCaseRepository(settings)
    with _fake_postgres_connection([]) as conn:
        repo.list_warm_cases(include_noise=False)
        cur = conn.last_cursor
    assert cur is not None
    assert "<> 'bounce'" in cur.last_sql
    assert "<> 'problem'" in cur.last_sql


def test_utc_cutoff_respects_days_window() -> None:
    cutoff = utc_cutoff(14)
    assert cutoff.tzinfo is not None
    assert cutoff <= datetime.now(timezone.utc)


@pytest.mark.skipif(
    not (os.environ.get("ORIGENLAB_TEST_POSTGRES_URL") or "").strip(),
    reason="Set ORIGENLAB_TEST_POSTGRES_URL for disposable Postgres integration.",
)
def test_postgres_warm_cases_integration_against_mirror() -> None:
    pytest.importorskip("psycopg")
    from psycopg import OperationalError

    url = os.environ["ORIGENLAB_TEST_POSTGRES_URL"].strip()
    settings = Settings(api_backend="postgres", postgres_url=url)
    repo = PostgresWarmCaseRepository(settings)
    try:
        items, meta = repo.list_warm_cases(days=30, limit=5, positive_signal_only=False)
    except OperationalError as exc:
        pytest.skip(f"Postgres not reachable at ORIGENLAB_TEST_POSTGRES_URL: {exc}")
    assert meta.data_source == "postgres_mirror"
    assert meta.read_only is True
    if items:
        assert meta.reduced_mode is False
        assert items[0].case_id
    else:
        assert meta.reduced_mode is True
        assert "include-warm-cases" in meta.note
