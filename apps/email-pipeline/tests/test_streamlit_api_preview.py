"""Tests for optional Streamlit API preview helpers."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock

import pytest

from origenlab_email_pipeline.streamlit_api_preview import (
    DEFAULT_API_BASE_URL,
    api_preview_enabled,
    api_preview_paths,
    build_api_url,
    fetch_json,
    normalize_api_base_url,
    primary_sidebar_pages,
    readiness_needs_warning,
    resolve_api_base_url,
    summary_count_cards,
)
from origenlab_email_pipeline.streamlit_page_status import PAGE_STATUS_PRESETS


def test_api_preview_disabled_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_API_BASE_URL", raising=False)
    assert api_preview_enabled() is False
    assert "API preview" not in primary_sidebar_pages(["Inicio", "Contactos"])


def test_api_preview_enabled_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8000")
    assert api_preview_enabled() is True
    pages = primary_sidebar_pages(["Inicio"])
    assert pages[-1] == "API preview"


def test_normalize_and_build_api_url() -> None:
    assert normalize_api_base_url("127.0.0.1:8000/") == "http://127.0.0.1:8000"
    assert build_api_url("http://127.0.0.1:8000", "/health") == "http://127.0.0.1:8000/health"


def test_resolve_api_base_url_prefers_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORIGENLAB_API_BASE_URL", "http://env:9000")
    assert resolve_api_base_url("http://override:8000") == "http://override:8000"
    assert resolve_api_base_url() == "http://env:9000"


def test_resolve_api_base_url_default_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_API_BASE_URL", raising=False)
    assert resolve_api_base_url() == DEFAULT_API_BASE_URL
    assert DEFAULT_API_BASE_URL.endswith(":8001")


def test_api_preview_paths_mirror_on_8001() -> None:
    paths = api_preview_paths("http://127.0.0.1:8001")
    assert paths["summary"].startswith("/mirror/")
    assert paths["readiness"] == "/mirror/outbound/readiness"


def test_api_preview_paths_legacy_on_8000() -> None:
    paths = api_preview_paths("http://127.0.0.1:8000")
    assert paths["summary"] == "/dashboard/summary?scope=canonical"
    assert paths["readiness"] == "/outbound/readiness"


def test_fetch_json_success() -> None:
    payload = {"status": "ok", "read_only": True}

    def fake_open(req, timeout=10.0):
        assert req.full_url.endswith("/health")
        resp = MagicMock()
        resp.read.return_value = json.dumps(payload).encode("utf-8")
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    data, err = fetch_json("http://127.0.0.1:8000", "/health", opener=fake_open)
    assert err is None
    assert data == payload


def test_fetch_json_http_error() -> None:
    from urllib.error import HTTPError

    def fake_open(req, timeout=10.0):
        raise HTTPError(req.full_url, 503, "Service Unavailable", hdrs=None, fp=BytesIO(b""))

    data, err = fetch_json("http://127.0.0.1:8000", "/health", opener=fake_open)
    assert data is None
    assert err is not None and "503" in err


def test_summary_count_cards() -> None:
    cards = summary_count_cards(
        {
            "contact_count": 10,
            "organization_count": 3,
            "eventually_consistent": True,
        }
    )
    labels = [c[0] for c in cards]
    assert "Contactos" in labels
    assert "Organizaciones" in labels
    assert all(c[1] in (10, 3) for c in cards)


def test_readiness_needs_warning() -> None:
    assert readiness_needs_warning({"verdict": "ready_with_warnings"}) is True
    assert readiness_needs_warning({"verdict": "ready"}) is False


def test_page_status_preset_for_api_preview() -> None:
    assert "API preview" in PAGE_STATUS_PRESETS
    assert "Postgres mirror" in PAGE_STATUS_PRESETS["API preview"]["source"]
