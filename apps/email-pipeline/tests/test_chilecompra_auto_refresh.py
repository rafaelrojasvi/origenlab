"""Tests for ChileCompra equipment auto-refresh operator command (mocked build/publish)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from origenlab_email_pipeline.chilecompra_api import TICKET_ENV_VAR
from origenlab_email_pipeline.operator_cli.chilecompra_auto_refresh import (
    DEFAULT_COOLDOWN_SECONDS,
    ChilecompraEquipmentAutoRefreshOptions,
    ChilecompraEquipmentAutoRefreshState,
    evaluate_chilecompra_equipment_auto_refresh,
    load_state,
    run_chilecompra_equipment_auto_refresh,
    state_path,
)
from origenlab_email_pipeline.operator_cli.mail_auto_refresh import acquire_lock

_SECRET_TICKET = "00000000-0000-0000-0000-000000000099"
_T0 = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)


def _opts(**kwargs: object) -> ChilecompraEquipmentAutoRefreshOptions:
    return ChilecompraEquipmentAutoRefreshOptions(once=True, **kwargs)


def _parse_output(out: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in out.strip().splitlines():
        if "=" in line and line != "chilecompra_equipment_auto_refresh":
            key, value = line.split("=", 1)
            result[key] = value
    return result


def _mock_build_result() -> tuple[list[dict[str, str]], dict[str, object], list[dict[str, str]]]:
    rows = [
        {
            "codigo_licitacion": "1051-1-LP26",
            "buyer": "Hospital Demo",
            "region": "RM",
            "close_date": "2026-06-17T19:00:00",
            "title": "Centrifuga",
            "item_description": "Centrifuga refrigerada",
            "equipment_category": "centrifuge",
            "fit_score": "85",
            "reason": "source:chilecompra_api; equipment:centrifuge",
            "next_action": "quote_now",
            "validity_status": "open",
            "chilecompra_status_code": "5",
            "chilecompra_status": "Publicada",
            "api_checked_at_utc": _T0.isoformat(),
            "source": "chilecompra_api",
        }
    ]
    manifest = {
        "fetched_summaries": 10,
        "candidate_summaries": 3,
        "detail_requests": 2,
        "detail_cache_hits": 1,
        "detail_error_count": 0,
        "output_rows": 1,
    }
    audit_rows = [{"codigo": "1051-1-LP26", "prefilter_match": "true"}]
    return rows, manifest, audit_rows


@pytest.fixture
def reports_dir(tmp_path: Path) -> Path:
    return tmp_path


def test_dry_run_does_not_write_publish_output(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = MagicMock()
    publish = MagicMock()
    monkeypatch.setenv(TICKET_ENV_VAR, _SECRET_TICKET)

    run_chilecompra_equipment_auto_refresh(
        _opts(apply=False),
        reports_dir=reports_dir,
        build_fn=build,
        publish_fn=publish,
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert out["apply"] == "false"
    assert out["reason"] == "dry_run"
    assert out["ran_refresh"] == "false"
    assert out["published"] == "false"
    build.assert_not_called()
    publish.assert_not_called()
    assert not list((reports_dir / "active" / "current").glob("equipment_first_operator_queue_*.csv"))


def test_apply_writes_state_and_calls_mocked_build_publish(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TICKET_ENV_VAR, _SECRET_TICKET)
    publish = MagicMock(
        return_value={
            "out_csv": str(reports_dir / "active/current/equipment_first_operator_queue_20260614.csv"),
            "output_rows": 1,
            "coalesced_duplicate_rows": 0,
            "unique_codigo_count": 1,
        }
    )

    rc = run_chilecompra_equipment_auto_refresh(
        _opts(apply=True),
        reports_dir=reports_dir,
        build_fn=lambda **kwargs: _mock_build_result(),
        publish_fn=publish,
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert rc == 0
    assert out["reason"] == "refreshed"
    assert out["ran_refresh"] == "true"
    assert out["published"] == "true"
    assert out["output_rows"] == "1"
    assert out["published_rows"] == "1"
    assert out["detail_requests"] == "2"
    assert out["detail_cache_hits"] == "1"
    publish.assert_called_once()

    state = load_state(state_path(reports_dir))
    assert state.last_result == "refreshed"
    assert state.fetched_summaries == 10
    assert state.candidate_summaries == 3
    assert state.output_rows == 1
    assert state.published_rows == 1
    assert state.next_recommended_run_at is not None
    assert _SECRET_TICKET not in json.dumps(state.to_dict())


def test_missing_ticket_gives_clean_failure(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TICKET_ENV_VAR, raising=False)
    rc = run_chilecompra_equipment_auto_refresh(
        _opts(apply=True),
        reports_dir=reports_dir,
        build_fn=MagicMock(),
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert rc == 2
    assert out["reason"] == "ticket_missing"
    state = load_state(state_path(reports_dir))
    assert state.consecutive_failures == 1
    assert _SECRET_TICKET not in (state.last_error or "")


def test_lock_live_skips(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "origenlab_email_pipeline.operator_cli.chilecompra_auto_refresh._lock_is_live",
        lambda _lock: True,
    )
    run_chilecompra_equipment_auto_refresh(
        _opts(apply=True),
        reports_dir=reports_dir,
        build_fn=MagicMock(side_effect=AssertionError("build must not run")),
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert out["reason"] == "lock_live"
    assert out["ran_refresh"] == "false"


def test_cooldown_skips_when_recent_success_and_no_force() -> None:
    state = ChilecompraEquipmentAutoRefreshState(
        last_successful_refresh_at=(_T0 - timedelta(seconds=60)).isoformat(),
    )
    result = evaluate_chilecompra_equipment_auto_refresh(
        options=_opts(apply=True, cooldown_seconds=DEFAULT_COOLDOWN_SECONDS),
        state=state,
        now=_T0,
    )
    assert result.reason == "cooldown"
    assert result.should_run is False


def test_force_bypasses_cooldown() -> None:
    state = ChilecompraEquipmentAutoRefreshState(
        last_successful_refresh_at=(_T0 - timedelta(seconds=60)).isoformat(),
    )
    result = evaluate_chilecompra_equipment_auto_refresh(
        options=_opts(apply=True, force=True),
        state=state,
        now=_T0,
    )
    assert result.reason == "ready"
    assert result.should_run is True


def test_build_failure_increments_failures_and_redacts_ticket(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TICKET_ENV_VAR, _SECRET_TICKET)

    def _fail(**_kwargs: object) -> tuple[list[dict[str, str]], dict[str, object], list[dict[str, str]]]:
        raise RuntimeError(f"boom ticket={_SECRET_TICKET}")

    rc = run_chilecompra_equipment_auto_refresh(
        _opts(apply=True),
        reports_dir=reports_dir,
        build_fn=_fail,
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert rc == 1
    assert out["reason"] == "build_failed"
    state = load_state(state_path(reports_dir))
    assert state.consecutive_failures == 1
    assert _SECRET_TICKET not in (state.last_error or "")
    assert "<redacted>" in (state.last_error or "")


def test_apply_without_publish_skips_publish_call(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TICKET_ENV_VAR, _SECRET_TICKET)
    publish = MagicMock()

    run_chilecompra_equipment_auto_refresh(
        _opts(apply=True, publish=False),
        reports_dir=reports_dir,
        build_fn=lambda **kwargs: _mock_build_result(),
        publish_fn=publish,
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert out["published"] == "false"
    publish.assert_not_called()


def test_live_lock_prevents_overlap(
    reports_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TICKET_ENV_VAR, _SECRET_TICKET)
    monkeypatch.setattr(
        "origenlab_email_pipeline.operator_cli.chilecompra_auto_refresh._lock_is_live",
        lambda _lock: False,
    )
    monkeypatch.setattr(
        "origenlab_email_pipeline.operator_cli.mail_auto_refresh._process_alive",
        lambda pid: True,
    )
    active = reports_dir / "active" / "current"
    active.mkdir(parents=True)
    acquire_lock(active / "chilecompra_equipment_auto_refresh.lock", now=_T0)

    run_chilecompra_equipment_auto_refresh(
        _opts(apply=True),
        reports_dir=reports_dir,
        build_fn=MagicMock(side_effect=AssertionError("build must not run")),
        now_fn=lambda: _T0,
    )
    out = _parse_output(capsys.readouterr().out)
    assert out["reason"] == "lock_live"
