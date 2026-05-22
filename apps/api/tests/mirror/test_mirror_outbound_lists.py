"""Tests for GET /mirror/outbound/suppressions/emails and /mirror/outbound/contact-state."""

from __future__ import annotations

from fastapi.testclient import TestClient

from origenlab_email_pipeline.postgres_dashboard_api.outbound_lists import (
    list_email_suppressions,
    list_outreach_contact_state,
)

from fake_conn import MirrorFakeConn


def test_mirror_suppressions_emails(summary_mirror_client: TestClient) -> None:
    r = summary_mirror_client.get("/mirror/outbound/suppressions/emails")
    assert r.status_code == 200
    body = r.json()
    assert body["table_available"] is True
    assert len(body["items"]) >= 1
    assert body["items"][0]["email"] == "bad@example.cl"


def test_mirror_suppressions_emails_q_filter(summary_mirror_client: TestClient) -> None:
    r = summary_mirror_client.get(
        "/mirror/outbound/suppressions/emails", params={"q": "bad@", "limit": 10}
    )
    assert r.status_code == 200


def test_mirror_contact_state(summary_mirror_client: TestClient) -> None:
    r = summary_mirror_client.get("/mirror/outbound/contact-state")
    assert r.status_code == 200
    body = r.json()
    assert body["table_available"] is True
    assert len(body["items"]) >= 1
    assert body["items"][0]["contact_email_norm"] == "lead@example.cl"
    assert body["items"][0]["state"] == "contacted"


def test_mirror_contact_state_state_filter(summary_mirror_client: TestClient) -> None:
    r = summary_mirror_client.get(
        "/mirror/outbound/contact-state", params={"state": "contacted", "limit": 5}
    )
    assert r.status_code == 200


def test_shared_suppressions_matches_mirror_http(
    summary_mirror_client: TestClient,
) -> None:
    fake = MirrorFakeConn()
    direct = list_email_suppressions(fake, limit=50, offset=0, q=None).model_dump(
        mode="json"
    )
    http = summary_mirror_client.get("/mirror/outbound/suppressions/emails").json()
    assert set(http.keys()) == set(direct.keys())
    assert http["table_available"] is True
    assert http["items"][0]["email"] == direct["items"][0]["email"]


def test_shared_contact_state_matches_mirror_http(
    summary_mirror_client: TestClient,
) -> None:
    fake = MirrorFakeConn()
    direct = list_outreach_contact_state(
        fake, limit=50, offset=0, state=None, q=None
    ).model_dump(mode="json")
    http = summary_mirror_client.get("/mirror/outbound/contact-state").json()
    assert set(http.keys()) == set(direct.keys())
    assert http["items"][0]["state"] == direct["items"][0]["state"]


def test_mirror_outbound_list_openapi_paths(summary_mirror_client: TestClient) -> None:
    paths = summary_mirror_client.get("/openapi.json").json()["paths"]
    assert "/mirror/outbound/suppressions/emails" in paths
    assert "/mirror/outbound/contact-state" in paths
