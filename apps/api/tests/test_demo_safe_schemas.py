"""Portfolio/demo-safe response schema guards."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import pytest

from origenlab_api.schemas.operator import OperatorStatusResponse
from origenlab_api.schemas.operator_automation import OperatorAutomationStatusResponse
from origenlab_email_pipeline.postgres_dashboard_api.health import (
    build_health_dependencies_response,
)


class _FakeConn:
    def execute(self, sql: str):
        return None


@contextmanager
def _fake_pg(_url: str) -> Generator[_FakeConn, None, None]:
    yield _FakeConn()


def test_operator_status_response_uses_typed_nested_models() -> None:
    response = OperatorStatusResponse.model_validate(
        {
            "verdict": "READY",
            "sqlite_path": "emails.sqlite",
            "sqlite_path_info": {
                "redacted": True,
                "basename": "emails.sqlite",
                "kind": "file",
            },
            "outbound_readiness": "ready",
            "daily_core_run": {
                "path": "daily_core_run_manifest.json",
                "exists": True,
                "loaded": True,
                "schema_version": 1,
                "workflow": "daily-core",
                "generated_at_utc": "2026-06-24T18:25:17+00:00",
                "status": "success",
                "returncode": 0,
                "step_count": 8,
                "last_step": "status",
                "send_approval": False,
                "postgres_mirror": "not included",
                "future_extra_key": "kept for compatibility",
            },
        }
    )

    dumped = response.model_dump()
    assert dumped["sqlite_path_info"]["basename"] == "emails.sqlite"
    assert dumped["daily_core_run"]["workflow"] == "daily-core"
    assert dumped["daily_core_run"]["future_extra_key"] == "kept for compatibility"


def test_operator_automation_response_uses_typed_active_current_path_info() -> None:
    response = OperatorAutomationStatusResponse.model_validate(
        {
            "generated_at_utc": "2026-06-24T18:25:17+00:00",
            "active_current_dir": "current",
            "active_current_dir_info": {
                "redacted": True,
                "basename": "current",
                "kind": "directory",
            },
            "verdict": "healthy",
            "recommended_action": "none",
        }
    )

    dumped = response.model_dump()
    assert dumped["active_current_dir_info"] == {
        "redacted": True,
        "basename": "current",
        "kind": "directory",
    }


def test_health_dependencies_redacts_postgres_url_to_configured_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    sqlite = tmp_path / "emails.sqlite"
    sqlite.write_bytes(b"")
    monkeypatch.setattr(
        "origenlab_email_pipeline.postgres_dashboard_api.health.postgres_connection",
        _fake_pg,
    )

    response = build_health_dependencies_response(
        postgres_url="postgresql://user:password@db.example.com:5432/origenlab_dashboard_prod",
        postgres_url_redacted="postgresql://user:***@db.example.com:5432/origenlab_dashboard_prod",
        sqlite_path=sqlite,
    ).model_dump(mode="json")

    assert response["postgres_url_redacted"] == "<configured>"
    assert "://" not in response["postgres_url_redacted"]
    assert "db.example.com" not in response["postgres_url_redacted"]
    assert response["status"] == "ok"


def test_health_dependencies_missing_sqlite_detail_does_not_leak_local_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    missing = tmp_path / "nested" / "emails.sqlite"
    monkeypatch.setattr(
        "origenlab_email_pipeline.postgres_dashboard_api.health.postgres_connection",
        _fake_pg,
    )

    response = build_health_dependencies_response(
        postgres_url="postgresql://user:password@db.example.com:5432/origenlab_dashboard_prod",
        postgres_url_redacted="postgresql://user:***@db.example.com:5432/origenlab_dashboard_prod",
        sqlite_path=missing,
    ).model_dump(mode="json")

    sqlite_dep = next(dep for dep in response["dependencies"] if dep["name"] == "sqlite")
    assert sqlite_dep["status"] == "skipped"
    assert str(tmp_path) not in sqlite_dep["detail"]
    assert "emails.sqlite" not in sqlite_dep["detail"]
