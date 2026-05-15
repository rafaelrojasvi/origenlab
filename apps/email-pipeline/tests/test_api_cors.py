"""CORS for local React dashboard (read-only GET)."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from origenlab_api.main import create_app


def test_cors_allows_dashboard_dev_origin() -> None:
    app = create_app()
    with TestClient(app) as client:
        r = client.options(
            "/dashboard/summary",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
