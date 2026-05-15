"""Tests for read-only FastAPI Slice 1 (mocked Postgres)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator
import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from origenlab_api.config import reset_api_settings_cache
from origenlab_api.main import create_app
from origenlab_email_pipeline.contacto_gmail_source import CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE
from origenlab_email_pipeline.operational_scope import (
    ARCHIVE_SCOPE_NOTE,
    CANONICAL_SCOPE_NOTE,
)

# Scratch-like mart mirror: archive counts >> canonical (regression guard).
_SCRATCH_CANONICAL = {
    "mart.contact_master_canonical": 497,
    "mart.organization_master_canonical": 261,
    "mart.opportunity_signals_canonical": 200,
}
_SCRATCH_ARCHIVE = {
    "mart.contact_master": 27198,
    "mart.organization_master": 10688,
    "mart.opportunity_signals": 2705,
}


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class FakeConn:
    """Minimal psycopg-like connection for query tests."""

    def __init__(self) -> None:
        self.tables = {
            ("mart", "contact_master"): True,
            ("mart", "organization_master"): True,
            ("mart", "opportunity_signals"): True,
            ("mart", "contact_master_canonical"): True,
            ("mart", "organization_master_canonical"): True,
            ("mart", "opportunity_signals_canonical"): True,
            ("outbound", "contact_email_suppression"): True,
            ("outbound", "contact_domain_suppression"): True,
            ("outbound", "outreach_contact_state"): True,
        }
        self.counts = {**_SCRATCH_ARCHIVE, **_SCRATCH_CANONICAL}
        self.counts.update(
            {
                "outbound.contact_email_suppression": 2,
                "outbound.contact_domain_suppression": 1,
                "outbound.outreach_contact_state": 4,
            }
        )

    def _count_cursor(self, qualified: str) -> _FakeCursor:
        return _FakeCursor([{"n": self.counts[qualified]}])

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        s = " ".join(sql.split()).lower()
        if "information_schema.tables" in s:
            schema = params[0]
            table = params[1]
            ok = self.tables.get((schema, table), False)
            return _FakeCursor([{"?": 1}] if ok else [])
        if "count(*)" in s:
            for qualified in (
                "mart.contact_master_canonical",
                "mart.organization_master_canonical",
                "mart.opportunity_signals_canonical",
                "mart.contact_master",
                "mart.organization_master",
                "mart.opportunity_signals",
            ):
                if qualified in s:
                    return self._count_cursor(qualified)
        if "count(*)" in s and "contact_email_suppression" in s:
            return _FakeCursor([{"n": self.counts["outbound.contact_email_suppression"]}])
        if "count(*)" in s and "contact_domain_suppression" in s:
            return _FakeCursor([{"n": self.counts["outbound.contact_domain_suppression"]}])
        if "count(*)" in s and "outreach_contact_state" in s:
            if "group by" in s:
                return _FakeCursor([{"st": "contacted", "n": 2}])
            return _FakeCursor([{"n": self.counts["outbound.outreach_contact_state"]}])
        if "from mart.contact_master_canonical" in s and "select email" in s:
            return _FakeCursor(
                [
                    {
                        "email": "lab@example.cl",
                        "contact_name_best": "Lab",
                        "domain": "example.cl",
                        "organization_name_guess": "Example",
                        "organization_type_guess": "lab",
                        "first_seen_at": None,
                        "last_seen_at": None,
                        "total_emails": 1,
                        "confidence_score": 0.9,
                        "top_equipment_tags": "micro",
                    }
                ]
            )
        if "from mart.organization_master_canonical" in s and "select domain" in s:
            return _FakeCursor(
                [
                    {
                        "domain": "lab.cl",
                        "organization_name_guess": "Lab Canonical",
                        "organization_type_guess": "lab",
                        "first_seen_at": None,
                        "last_seen_at": None,
                        "total_emails": 10,
                        "total_contacts": 2,
                        "top_equipment_tags": None,
                        "key_contacts": None,
                    }
                ]
            )
        if "from mart.organization_master" in s and "select domain" in s:
            return _FakeCursor(
                [
                    {
                        "domain": "archive.cl",
                        "organization_name_guess": "Archive Org",
                        "organization_type_guess": "lab",
                        "first_seen_at": None,
                        "last_seen_at": None,
                        "total_emails": 100,
                        "total_contacts": 20,
                        "top_equipment_tags": None,
                        "key_contacts": None,
                    }
                ]
            )
        if "from mart.contact_master" in s and "select email" in s:
            return _FakeCursor(
                [
                    {
                        "email": "archive@example.cl",
                        "contact_name_best": "Lab",
                        "domain": "example.cl",
                        "organization_name_guess": "Example",
                        "organization_type_guess": "lab",
                        "first_seen_at": None,
                        "last_seen_at": None,
                        "total_emails": 1,
                        "confidence_score": 0.9,
                        "top_equipment_tags": "micro",
                    }
                ]
            )
        if "from outbound.contact_email_suppression" in s and "select email" in s:
            return _FakeCursor(
                [
                    {
                        "email": "bad@example.cl",
                        "suppression_reason_code": "manual",
                        "suppression_reason_text": None,
                        "suppression_source": None,
                        "last_bounced_at": None,
                        "updated_at": None,
                        "updated_by": None,
                    }
                ]
            )
        if "max(last_seen_at)" in s and "contact_master" in s:
            return _FakeCursor([{"m": None}])
        if "select 1" in s:
            return _FakeCursor([{"?": 1}])
        return _FakeCursor([{"n": 0}])

    def close(self) -> None:
        return None


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Generator[TestClient, None, None]:
    reset_api_settings_cache()
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@localhost:5432/scratch")
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setenv("ORIGENLAB_SQLITE_PATH", str(sqlite))

    fake = FakeConn()

    @contextmanager
    def _fake_pg(_url: str) -> Generator[FakeConn, None, None]:
        yield fake

    monkeypatch.setattr("origenlab_api.deps.postgres_connection", _fake_pg)
    monkeypatch.setattr("origenlab_api.routers.health.postgres_connection", _fake_pg)

    app = create_app()
    with TestClient(app) as tc:
        yield tc
    reset_api_settings_cache()


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["read_only"] is True


def test_health_dependencies(client: TestClient) -> None:
    r = client.get("/health/dependencies")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    names = {d["name"] for d in body["dependencies"]}
    assert "postgres" in names


def test_dashboard_summary_default_canonical_scope(client: TestClient) -> None:
    r = client.get("/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert body["scope_available"] is True
    assert body["scope_note"] == CANONICAL_SCOPE_NOTE
    assert CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE in body["scope_note"]
    assert body["contact_count"] == _SCRATCH_CANONICAL["mart.contact_master_canonical"]
    assert body["organization_count"] == _SCRATCH_CANONICAL["mart.organization_master_canonical"]
    assert body["opportunity_signal_count"] == _SCRATCH_CANONICAL["mart.opportunity_signals_canonical"]
    assert body["archive_mirror_counts"]["contact_count"] == _SCRATCH_ARCHIVE["mart.contact_master"]
    assert body["contact_count"] < body["archive_mirror_counts"]["contact_count"]
    assert body["eventually_consistent"] is True
    assert body["data_source"] == "postgres_mirror"


def test_dashboard_summary_archive_scope_explicit(client: TestClient) -> None:
    r = client.get("/dashboard/summary", params={"scope": "archive"})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "archive"
    assert body["scope_note"] == ARCHIVE_SCOPE_NOTE
    assert body["contact_count"] == _SCRATCH_ARCHIVE["mart.contact_master"]
    assert body["organization_count"] == _SCRATCH_ARCHIVE["mart.organization_master"]
    assert body["opportunity_signal_count"] == _SCRATCH_ARCHIVE["mart.opportunity_signals"]
    assert body["contact_count"] > _SCRATCH_CANONICAL["mart.contact_master_canonical"]


def test_api_default_scope_not_archive_mart_counts(client: TestClient) -> None:
    """Regression: omitting ?scope= must not return full-archive mart totals."""
    summary = client.get("/dashboard/summary").json()
    assert summary["contact_count"] != _SCRATCH_ARCHIVE["mart.contact_master"]
    assert summary["organization_count"] != _SCRATCH_ARCHIVE["mart.organization_master"]
    assert summary["opportunity_signal_count"] != _SCRATCH_ARCHIVE["mart.opportunity_signals"]


def test_contacts_pagination_default_canonical(client: TestClient) -> None:
    r = client.get("/contacts", params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert body["scope_available"] is True
    assert body["scope_note"] == CANONICAL_SCOPE_NOTE
    assert body["table_available"] is True
    assert body["items"][0]["email"] == "lab@example.cl"
    assert body["total"] == _SCRATCH_CANONICAL["mart.contact_master_canonical"]


def test_contacts_archive_scope(client: TestClient) -> None:
    r = client.get("/contacts", params={"scope": "archive", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "archive"
    assert body["scope_note"] == ARCHIVE_SCOPE_NOTE
    assert body["items"][0]["email"] == "archive@example.cl"
    assert body["total"] == _SCRATCH_ARCHIVE["mart.contact_master"]


def test_organizations_default_canonical_scope(client: TestClient) -> None:
    r = client.get("/organizations", params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert body["scope_available"] is True
    assert body["scope_note"] == CANONICAL_SCOPE_NOTE
    assert body["table_available"] is True
    assert body["items"][0]["domain"] == "lab.cl"
    assert body["total"] == _SCRATCH_CANONICAL["mart.organization_master_canonical"]


def test_organizations_archive_scope_explicit(client: TestClient) -> None:
    r = client.get("/organizations", params={"scope": "archive", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "archive"
    assert body["scope_note"] == ARCHIVE_SCOPE_NOTE
    assert body["items"][0]["domain"] == "archive.cl"
    assert body["total"] == _SCRATCH_ARCHIVE["mart.organization_master"]


def test_outbound_readiness_eventually_consistent(client: TestClient) -> None:
    r = client.get("/outbound/readiness")
    assert r.status_code == 200
    body = r.json()
    assert body["eventually_consistent"] is True
    assert body["data_source"] == "postgres_mirror"
    assert "disclaimer" in body
    assert body["verdict"] in ("ready", "ready_with_warnings", "not_ready")


def test_suppressions_emails(client: TestClient) -> None:
    r = client.get("/outbound/suppressions/emails")
    assert r.status_code == 200
    assert r.json()["table_available"] is True


def test_missing_postgres_url_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_api_settings_cache()
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/dashboard/summary")
    assert r.status_code == 503
    reset_api_settings_cache()
