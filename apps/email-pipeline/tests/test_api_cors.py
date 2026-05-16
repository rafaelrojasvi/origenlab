"""CORS for local React dashboard (read-only GET)."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.main import DEFAULT_CORS_ORIGINS, cors_origins, create_app


@pytest.mark.parametrize(
    "origin",
    [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
)
def test_cors_preflight_allows_dashboard_dev_origins(origin: str) -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.options(
            "/dashboard/summary",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "accept",
            },
        )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == origin
    assert "GET" in (r.headers.get("access-control-allow-methods") or "")


@pytest.mark.parametrize(
    "origin",
    ["http://127.0.0.1:5173", "http://localhost:5173"],
)
def test_cors_get_includes_allow_origin(origin: str) -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.get(
            "/health",
            headers={"Origin": origin},
        )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == origin


def test_cors_origins_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ORIGENLAB_API_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    )
    assert cors_origins() == [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]


def test_cors_default_origins_include_vite_hosts() -> None:
    assert "http://127.0.0.1:5173" in DEFAULT_CORS_ORIGINS
    assert "http://localhost:5173" in DEFAULT_CORS_ORIGINS


def test_cors_disallowed_origin_not_reflected() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.options(
            "/dashboard/summary",
            headers={
                "Origin": "http://evil.example:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert r.status_code == 400
    assert r.headers.get("access-control-allow-origin") != "http://evil.example:5173"


def test_cors_middleware_registered_before_routes() -> None:
    app = create_app()
    names = [m.cls.__name__ for m in app.user_middleware]
    assert "CORSMiddleware" in names


def test_cors_private_network_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chrome local-dev may send Access-Control-Request-Private-Network."""
    monkeypatch.delenv("ORIGENLAB_API_CORS_ORIGINS", raising=False)
    app = create_app()
    with TestClient(app) as client:
        r = client.options(
            "/health",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Private-Network": "true",
            },
        )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-private-network") == "true"
