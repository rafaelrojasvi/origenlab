"""Postgres recent emails repository read contract."""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

from origenlab_api.backends.factory import get_repository_bundle
from origenlab_api.repositories.postgres.email import (
    PostgresEmailRecentRepository,
    build_scope_note,
    date_cutoff_iso,
    map_recent_email_row,
)
from origenlab_api.repositories.sqlite.email import SqliteEmailRecentRepository
from origenlab_api.settings import Settings


def _fixture_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "email_id": 42,
        "date_iso": "2026-05-19T10:00:00-04:00",
        "subject_preview": "Cotización equipo",
        "sender_preview": "client@example.cl",
        "source_file": None,
        "folder_hint": "[Gmail]/Enviados",
        "has_positive_signal": True,
        "has_suppression_signal": False,
        "predicted_label": "customer",
    }
    base.update(overrides)
    return base


def test_map_recent_email_row_maps_required_public_fields() -> None:
    mapped = map_recent_email_row(_fixture_row())
    assert mapped["email_id"] == 42
    assert mapped["date_iso"] == "2026-05-19T10:00:00-04:00"
    assert mapped["subject_preview"] == "Cotización equipo"
    assert mapped["sender_preview"] == "client@example.cl"
    assert mapped["folder_hint"] == "[Gmail]/Enviados"
    assert mapped["has_positive_signal"] is True
    assert mapped["has_suppression_signal"] is False


def test_map_recent_email_row_omits_unsafe_internal_fields() -> None:
    mapped = map_recent_email_row(
        _fixture_row(
            body="full mime body",
            raw_body="raw",
            headers={"From": "x@y.cl"},
            recipients_raw="a@b.cl",
        )
    )
    for field in ("body", "raw_body", "headers", "recipients_raw", "predicted_label"):
        assert field not in mapped


def test_map_recent_email_row_null_source_file_uses_folder_hint() -> None:
    mapped = map_recent_email_row(_fixture_row())
    assert mapped["source_file"] is None
    assert mapped["folder_hint"] == "[Gmail]/Enviados"


def test_map_recent_email_row_with_source_file_sets_folder_hint() -> None:
    mapped = map_recent_email_row(
        _fixture_row(source_file="gmail:contacto@origenlab.cl/[Gmail]/Enviados")
    )
    assert mapped["source_file"] == "gmail:contacto@origenlab.cl/[Gmail]/Enviados"
    assert mapped["folder_hint"] == "[Gmail]"


def test_build_scope_note_empty_mentions_sync() -> None:
    note = build_scope_note(items=[])
    assert "recent emails" in note.lower()
    assert "sync" in note.lower()


def test_build_scope_note_null_source_file() -> None:
    note = build_scope_note(items=[{"source_file": None}])
    assert "source_file" in note


def test_date_cutoff_iso_respects_days_window() -> None:
    cutoff_7 = date_cutoff_iso(7)
    cutoff_30 = date_cutoff_iso(30)
    assert len(cutoff_7) == 10
    assert cutoff_30 < cutoff_7


def test_repository_bundle_postgres_uses_postgres_recent_emails() -> None:
    settings = Settings(
        api_backend="postgres",
        postgres_url="postgresql://127.0.0.1:5432/scratch",
    )
    bundle = get_repository_bundle(settings)
    assert isinstance(bundle.email_recent, PostgresEmailRecentRepository)


def test_repository_bundle_sqlite_uses_sqlite_recent_emails(tmp_path: Path) -> None:
    settings = Settings(api_backend="sqlite", sqlite_path=tmp_path / "x.sqlite")
    bundle = get_repository_bundle(settings)
    assert isinstance(bundle.email_recent, SqliteEmailRecentRepository)


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
        "origenlab_api.repositories.postgres.email.postgres_connection",
        _connect,
    ):
        yield fake


def test_postgres_recent_emails_repository_does_not_use_sqlite_fallback() -> None:
    import origenlab_api.repositories.postgres.email as pg_email

    source = inspect.getsource(pg_email)
    forbidden = (
        "list_recent_emails",
        "resolved_sqlite_path",
        "sqlite3",
        "emails.sqlite",
    )
    for token in forbidden:
        assert token not in source


def test_postgres_recent_emails_queries_mirror_view() -> None:
    settings = Settings(
        api_backend="postgres",
        postgres_url="postgresql://127.0.0.1:5432/test",
    )
    repo = PostgresEmailRecentRepository(settings)
    with _fake_postgres_connection([_fixture_row()]) as conn:
        result = repo.list_recent(days=14, limit=10, exclude_noise=True, folder="enviados")
        cur = conn.last_cursor
    assert cur is not None
    assert "api.v_recent_email" in cur.last_sql
    assert "date_iso DESC NULLS LAST" in cur.last_sql
    assert cur.last_params["limit"] == 10
    assert cur.last_params["exclude_noise"] is True
    assert cur.last_params["folder"] == "enviados"
    assert isinstance(cur.last_params["cutoff_date"], str)
    assert len(result.items) == 1
    assert result.meta.data_source == "postgres_mirror"
    assert result.enrichment_available is True
    assert result.reduced_mode is False


def test_postgres_recent_emails_passes_days_window_to_sql_cutoff() -> None:
    settings = Settings(
        api_backend="postgres",
        postgres_url="postgresql://127.0.0.1:5432/test",
    )
    repo = PostgresEmailRecentRepository(settings)
    with _fake_postgres_connection([]) as conn:
        repo.list_recent(days=21, limit=5)
        cur = conn.last_cursor
    assert cur is not None
    expected = (date.today() - timedelta(days=21)).isoformat()
    assert cur.last_params["cutoff_date"] == expected


def test_postgres_recent_emails_caps_limit_to_200() -> None:
    settings = Settings(
        api_backend="postgres",
        postgres_url="postgresql://127.0.0.1:5432/test",
    )
    repo = PostgresEmailRecentRepository(settings)
    rows = [_fixture_row(email_id=1000 + index) for index in range(250)]
    with _fake_postgres_connection(rows) as conn:
        repo.list_recent(limit=500)
        cur = conn.last_cursor
    assert cur is not None
    assert cur.last_params["limit"] == 200


def test_postgres_recent_emails_exclude_noise_params_in_sql() -> None:
    settings = Settings(
        api_backend="postgres",
        postgres_url="postgresql://127.0.0.1:5432/test",
    )
    repo = PostgresEmailRecentRepository(settings)
    with _fake_postgres_connection([]) as conn:
        repo.list_recent(exclude_noise=True)
        cur = conn.last_cursor
    assert cur is not None
    assert "has_suppression_signal" in cur.last_sql
    assert "mailer-daemon" in cur.last_sql
    assert cur.last_params["noise_labels"]


def test_postgres_recent_emails_empty_results_use_reduced_mode() -> None:
    settings = Settings(
        api_backend="postgres",
        postgres_url="postgresql://127.0.0.1:5432/test",
    )
    repo = PostgresEmailRecentRepository(settings)
    with _fake_postgres_connection([]):
        result = repo.list_recent(days=7, limit=5)
    assert result.items == []
    assert result.reduced_mode is True
    assert result.meta.data_source == "postgres_mirror"
    assert result.meta.read_only is True
    assert result.enrichment_available is True
    assert "sync" in result.scope_note.lower()
