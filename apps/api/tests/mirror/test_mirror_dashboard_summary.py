"""Tests for GET /mirror/dashboard/summary (legacy /dashboard/summary parity)."""

from __future__ import annotations

from typing import Any

import pytest

from fastapi.testclient import TestClient

from origenlab_email_pipeline.contacto_gmail_source import CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE
from origenlab_email_pipeline.operational_scope import ARCHIVE_SCOPE_NOTE, CANONICAL_SCOPE_NOTE
from origenlab_email_pipeline.postgres_dashboard_api.summary import dashboard_summary

from fake_conn import (
    SCRATCH_ARCHIVE as _SCRATCH_ARCHIVE,
    SCRATCH_CANONICAL as _SCRATCH_CANONICAL,
    SummaryFakeConn,
)


def test_mirror_dashboard_summary_default_canonical(
    summary_mirror_client: TestClient,
) -> None:
    r = summary_mirror_client.get("/mirror/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "canonical"
    assert body["scope_available"] is True
    assert body["scope_note"] == CANONICAL_SCOPE_NOTE
    assert CONTACTO_GMAIL_SOURCE_SQL_LIKE_VALUE in body["scope_note"]
    assert body["contact_count"] == _SCRATCH_CANONICAL["mart.contact_master_canonical"]
    assert body["organization_count"] == _SCRATCH_CANONICAL["mart.organization_master_canonical"]
    assert body["opportunity_signal_count"] == _SCRATCH_CANONICAL[
        "mart.opportunity_signals_canonical"
    ]
    assert body["archive_mirror_counts"]["contact_count"] == _SCRATCH_ARCHIVE["mart.contact_master"]
    assert body["contact_count"] < body["archive_mirror_counts"]["contact_count"]
    assert body["eventually_consistent"] is True
    assert body["data_source"] == "postgres_mirror"


def test_mirror_dashboard_summary_archive_scope(
    summary_mirror_client: TestClient,
) -> None:
    r = summary_mirror_client.get(
        "/mirror/dashboard/summary", params={"scope": "archive"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "archive"
    assert body["scope_note"] == ARCHIVE_SCOPE_NOTE
    assert body["contact_count"] == _SCRATCH_ARCHIVE["mart.contact_master"]
    assert body["contact_count"] > _SCRATCH_CANONICAL["mart.contact_master_canonical"]


def test_mirror_dashboard_summary_default_not_archive_totals(
    summary_mirror_client: TestClient,
) -> None:
    summary = summary_mirror_client.get("/mirror/dashboard/summary").json()
    assert summary["contact_count"] != _SCRATCH_ARCHIVE["mart.contact_master"]


def test_shared_dashboard_summary_matches_mirror_http(
    summary_mirror_client: TestClient,
) -> None:
    fake = SummaryFakeConn()
    direct = dashboard_summary(fake, scope="canonical").model_dump(mode="json")
    http = summary_mirror_client.get("/mirror/dashboard/summary").json()
    assert set(http.keys()) == set(direct.keys())
    assert http["scope"] == direct["scope"] == "canonical"
    assert http["contact_count"] == direct["contact_count"]


def test_mirror_dashboard_summary_openapi_path(
    summary_mirror_client: TestClient,
) -> None:
    paths = summary_mirror_client.get("/openapi.json").json()["paths"]
    assert "/mirror/dashboard/summary" in paths
    assert "get" in paths["/mirror/dashboard/summary"]
    get_params = paths["/mirror/dashboard/summary"]["get"]["parameters"]
    scope_param = next(p for p in get_params if p.get("name") == "scope")
    assert "canonical" in str(scope_param.get("schema", {}))
