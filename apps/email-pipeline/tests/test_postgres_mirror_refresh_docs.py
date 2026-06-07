"""Guardrails for Postgres mirror refresh operator workflow (docs-only)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_MIRROR_REFRESH = _REPO / "docs" / "pipeline" / "POSTGRES_MIRROR_REFRESH.md"
_DAILY_CORE = _REPO / "docs" / "pipeline" / "DAILY_CORE.md"
_RUNBOOK = _REPO / "docs" / "RUNBOOK.md"


def test_postgres_mirror_refresh_md_exists() -> None:
    assert _MIRROR_REFRESH.is_file(), f"missing canonical doc: {_MIRROR_REFRESH}"


def test_postgres_mirror_refresh_daily_core_before_mirror_apply() -> None:
    text = _MIRROR_REFRESH.read_text(encoding="utf-8")
    assert "daily-core --apply" in text
    assert "mirror-dashboard --apply" in text
    daily_idx = text.index("daily-core --apply")
    mirror_idx = text.index("mirror-dashboard --apply")
    assert daily_idx < mirror_idx, "doc must present daily-core before mirror apply"


def test_postgres_mirror_refresh_documents_dry_run_and_apply() -> None:
    text = _MIRROR_REFRESH.read_text(encoding="utf-8")
    assert "uv run origenlab mirror-dashboard" in text
    assert "mirror-dashboard --apply" in text
    lower = text.lower()
    assert "dry-run" in lower or "dry run" in lower


def test_postgres_mirror_refresh_documents_postgres_url_env_vars() -> None:
    text = _MIRROR_REFRESH.read_text(encoding="utf-8")
    for var in (
        "ORIGENLAB_POSTGRES_URL",
        "ALEMBIC_DATABASE_URL",
        "ORIGENLAB_CLOUD_POSTGRES_URL",
    ):
        assert var in text, f"POSTGRES_MIRROR_REFRESH.md must mention {var!r}"


def test_postgres_mirror_refresh_documents_source_env_pattern() -> None:
    text = _MIRROR_REFRESH.read_text(encoding="utf-8")
    assert "set -a" in text
    assert "source .env" in text
    assert "set +a" in text


def test_postgres_mirror_refresh_documents_ol_mirror_zshrc_helper() -> None:
    text = _MIRROR_REFRESH.read_text(encoding="utf-8")
    assert "ol-mirror" in text
    assert "~/.zshrc" in text


def test_postgres_mirror_refresh_mirror_not_send_approval() -> None:
    text = _MIRROR_REFRESH.read_text(encoding="utf-8")
    lower = text.lower()
    assert "not send approval" in lower


def test_postgres_mirror_refresh_daily_core_never_includes_mirror() -> None:
    text = _MIRROR_REFRESH.read_text(encoding="utf-8")
    lower = text.lower()
    assert "never includes mirror" in lower or "intentionally never includes mirror" in lower


def test_postgres_mirror_refresh_alembic_apply_explicit_schema_only() -> None:
    text = _MIRROR_REFRESH.read_text(encoding="utf-8")
    assert "--alembic --apply" in text
    lower = text.lower()
    assert "schema" in lower
    assert "explicit" in lower or "only when" in lower


def test_daily_core_links_postgres_mirror_refresh() -> None:
    text = _DAILY_CORE.read_text(encoding="utf-8")
    assert "POSTGRES_MIRROR_REFRESH.md" in text


def test_runbook_links_postgres_mirror_refresh() -> None:
    text = _RUNBOOK.read_text(encoding="utf-8")
    assert "POSTGRES_MIRROR_REFRESH.md" in text


def test_postgres_mirror_refresh_documents_live_dashboard_preset() -> None:
    text = _MIRROR_REFRESH.read_text(encoding="utf-8")
    assert "mirror-dashboard --live" in text
    assert "--operator" in text
    assert "--reason" in text
    lower = text.lower()
    assert "warm cases" in lower or "warm case" in lower
    assert "equipment opportunit" in lower
    assert "commercial deal" in lower
    assert "never includes mirror" in lower or "intentionally never includes mirror" in lower


def test_postgres_mirror_refresh_documents_warm_case_parity_audit() -> None:
    text = _MIRROR_REFRESH.read_text(encoding="utf-8")
    assert "audit_warm_case_parity.py" in text
    assert "/cases/warm" in text
    lower = text.lower()
    assert "diagnostic" in lower
    assert "not send approval" in lower or "does not approve sends" in lower
