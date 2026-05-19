"""API-0 must not invoke mutation paths (ingest, refresh, sync, send)."""

from __future__ import annotations

from pathlib import Path

import pytest

from origenlab_api.main import create_app

_API_SRC = Path(__file__).resolve().parents[1] / "src" / "origenlab_api"

_FORBIDDEN_SUBSTRINGS = (
    "refresh_outbound_safety_memory",
    "05_workspace_gmail_imap_to_sqlite",
    "sync_dashboard_postgres_mirror",
    "alembic",
    "gmail_send",
    "send_inline_html",
    "subprocess",
    "build_equipment_first_operator_queue",
    "mark_outreach_state",
)


def test_app_exposes_get_only_routes() -> None:
    app = create_app()
    unsafe: list[str] = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        mutating = methods - {"GET", "HEAD", "OPTIONS"}
        if mutating:
            unsafe.append(f"{route.path} {sorted(mutating)}")
    assert unsafe == [], f"mutating routes found: {unsafe}"


def test_origenlab_api_source_has_no_mutation_script_imports() -> None:
    hits: list[str] = []
    for path in _API_SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_SUBSTRINGS:
            if needle in text:
                hits.append(f"{path.relative_to(_API_SRC)}: {needle}")
    assert hits == [], "forbidden references in apps/api:\n" + "\n".join(hits)


def test_openapi_documents_read_only_app() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    r = client.get("/openapi.json")
    assert r.status_code == 200
    info = r.json()["info"]
    assert "read-only" in info["description"].lower()
