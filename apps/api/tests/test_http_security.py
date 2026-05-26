"""Production HTTP security: CORS, docs disabled, no wildcard origins."""

from __future__ import annotations

import pytest

from origenlab_api.backends.factory import validate_api_settings
from origenlab_api.http_security import (
    host_allowlist_enabled,
    normalize_host_header,
    openapi_docs_enabled,
)
from origenlab_api.main import create_app
from origenlab_api.settings import Settings, get_settings


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_production_mode_disables_openapi_docs() -> None:
    settings = Settings(env="production", api_disable_docs=False)
    assert openapi_docs_enabled(settings) is False


def test_api_disable_docs_flag_disables_openapi() -> None:
    settings = Settings(api_disable_docs=True)
    assert openapi_docs_enabled(settings) is False


def test_production_requires_postgres_backend_and_cors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORIGENLAB_ENV", "production")
    monkeypatch.setenv("ORIGENLAB_API_BACKEND", "sqlite")
    monkeypatch.delenv("ORIGENLAB_API_CORS_ORIGINS", raising=False)
    _clear_settings_cache()
    with pytest.raises(ValueError, match="ORIGENLAB_ENV=production requires ORIGENLAB_API_BACKEND=postgres"):
        create_app()


def test_production_rejects_wildcard_cors() -> None:
    settings = Settings(
        env="production",
        api_backend="postgres",
        postgres_url="postgresql://u:p@127.0.0.1:5432/db",
        api_cors_origins="*",
    )
    with pytest.raises(ValueError, match="must not include '\\*'"):
        validate_api_settings(settings)


def test_cors_allows_configured_dashboard_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ORIGENLAB_API_BACKEND", "postgres")
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("ORIGENLAB_API_CORS_ORIGINS", "https://dashboard.origenlab.cl")
    monkeypatch.delenv("ORIGENLAB_ENV", raising=False)
    _clear_settings_cache()
    client = TestClient(create_app())
    r = client.options(
        "/health",
        headers={
            "Origin": "https://dashboard.origenlab.cl",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "https://dashboard.origenlab.cl"


def test_operator_security_headers_on_json_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ORIGENLAB_API_BACKEND", "postgres")
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("ORIGENLAB_API_CORS_ORIGINS", "https://dashboard.origenlab.cl")
    _clear_settings_cache()
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert r.headers.get("x-frame-options") == "DENY"
    assert "no-store" in (r.headers.get("cache-control") or "")


def test_cors_preflight_does_not_allow_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ORIGENLAB_API_BACKEND", "postgres")
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("ORIGENLAB_API_CORS_ORIGINS", "https://dashboard.origenlab.cl")
    _clear_settings_cache()
    client = TestClient(create_app())
    r = client.options(
        "/health",
        headers={
            "Origin": "https://dashboard.origenlab.cl",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-credentials") is None


def test_normalize_host_strips_port() -> None:
    assert normalize_host_header("api.origenlab.cl:443") == "api.origenlab.cl"
    assert normalize_host_header("API.OrigenLab.CL") == "api.origenlab.cl"


def _production_client(monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ORIGENLAB_ENV", "production")
    monkeypatch.setenv("ORIGENLAB_API_BACKEND", "postgres")
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("ORIGENLAB_API_CORS_ORIGINS", "https://dashboard.origenlab.cl")
    monkeypatch.setenv("ORIGENLAB_API_ALLOWED_HOSTS", "api.origenlab.cl")
    _clear_settings_cache()
    return TestClient(create_app())


def test_production_allowed_host_permits_health(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _production_client(monkeypatch)
    r = client.get("/health", headers={"Host": "api.origenlab.cl"})
    assert r.status_code == 200


def test_production_render_host_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _production_client(monkeypatch)
    r = client.get("/health", headers={"Host": "origenlab.onrender.com"})
    assert r.status_code == 403
    assert r.json() == {"detail": "Forbidden"}


def test_production_missing_host_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _production_client(monkeypatch)
    r = client.get("/health", headers={"Host": ""})
    assert r.status_code == 403


def test_dev_mode_allows_render_host_without_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ORIGENLAB_API_BACKEND", "postgres")
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("ORIGENLAB_API_CORS_ORIGINS", "https://dashboard.origenlab.cl")
    monkeypatch.delenv("ORIGENLAB_ENV", raising=False)
    monkeypatch.delenv("ORIGENLAB_API_ALLOWED_HOSTS", raising=False)
    _clear_settings_cache()
    client = TestClient(create_app())
    r = client.get("/health", headers={"Host": "origenlab.onrender.com"})
    assert r.status_code == 200


def test_host_allowlist_disabled_without_env_hosts() -> None:
    settings = Settings(env="production", api_allowed_hosts=None)
    assert host_allowlist_enabled(settings) is False


def test_production_hides_docs_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ORIGENLAB_ENV", "production")
    monkeypatch.setenv("ORIGENLAB_API_BACKEND", "postgres")
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("ORIGENLAB_API_CORS_ORIGINS", "https://dashboard.origenlab.cl")
    monkeypatch.delenv("ORIGENLAB_API_ALLOWED_HOSTS", raising=False)
    _clear_settings_cache()
    client = TestClient(create_app())
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/health").status_code == 200
