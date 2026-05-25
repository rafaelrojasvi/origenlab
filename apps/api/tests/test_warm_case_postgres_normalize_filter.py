"""Postgres warm-case repo: normalize before positive category filter."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator
from unittest.mock import patch

from origenlab_api.repositories.postgres.warm_cases import PostgresWarmCaseRepository
from origenlab_api.settings import Settings


def _row(**overrides: Any) -> dict[str, Any]:
    base = {
        "case_id": "case:1",
        "last_email_id": 1,
        "last_seen_at": datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
        "account_name": "Banco",
        "contact_email": "serviciodetransferencias@bancochile.cl",
        "subject": "FACTURA 6",
        "category": "payment_admin",
        "status": "open",
        "next_action": "old",
        "equipment_signal": "",
        "snippet": "",
        "gmail_url": None,
    }
    base.update(overrides)
    return base


@contextmanager
def _fake_conn(rows: list[dict[str, Any]]) -> Iterator[Any]:
    class FakeCursor:
        def __enter__(self) -> FakeCursor:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, _sql: str, _params: dict[str, Any]) -> None:
            return None

        def fetchall(self) -> list[dict[str, Any]]:
            return rows

    class FakeConn:
        def cursor(self, *, row_factory: Any = None) -> FakeCursor:
            return FakeCursor()

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


def test_postgres_positive_filter_keeps_payment_admin_after_normalize() -> None:
    settings = Settings(api_backend="postgres", postgres_url="postgresql://127.0.0.1/db")
    repo = PostgresWarmCaseRepository(settings)
    with _fake_conn([_row(), _row(contact_email="monica.silva@dhl.com", subject="PROPUESTA COMERCIAL DHL", category="vendor_logistics")]):
        items, _meta = repo.list_warm_cases(limit=10, positive_signal_only=True)
    emails = {i.contact_email.lower() for i in items}
    assert "serviciodetransferencias@bancochile.cl" in emails
    assert "monica.silva@dhl.com" in emails


def test_postgres_internal_contacto_dropped_by_default() -> None:
    settings = Settings(api_backend="postgres", postgres_url="postgresql://127.0.0.1/db")
    repo = PostgresWarmCaseRepository(settings)
    with _fake_conn(
        [
            _row(
                contact_email="contacto@origenlab.cl",
                subject="Re: Quotation Request",
                category="waiting_client",
            )
        ]
    ):
        items, _meta = repo.list_warm_cases(limit=10, positive_signal_only=False)
    assert items == []
