"""Tests for daily-core apply run manifest (fake runners + temp reports dir only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from origenlab_email_pipeline.cli import RefreshDashboardOptions, main
from origenlab_email_pipeline.core.step_runner import StepResult
from origenlab_email_pipeline.operator_cli.daily_core_manifest import (
    MANIFEST_FILENAME,
    build_daily_core_run_manifest_payload,
    daily_core_run_manifest_path,
    write_daily_core_run_manifest,
)
from origenlab_email_pipeline.operator_cli.refresh import run_daily_core

_CORE_STEP_LABELS = (
    "gmail-ingest",
    "build-email-mart-features --missing-only --apply",
    "build-mart -- --rebuild --use-email-mart-features",
    "build-commercial-intel",
    "refresh-safety",
    "ndr-review",
    "post-send-digest",
    "status",
)
_EQUIVALENT_APPLY = "uv run origenlab refresh-dashboard --apply --no-mirror"


@pytest.fixture
def reports_active_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    active_current = tmp_path / "active" / "current"
    active_current.mkdir(parents=True)
    monkeypatch.setenv("ORIGENLAB_REPORTS_DIR", str(tmp_path))
    return active_current


def _refresh_opts(**kwargs: object) -> RefreshDashboardOptions:
    return RefreshDashboardOptions(**kwargs)


def _read_manifest(active_current: Path) -> dict:
    path = active_current / MANIFEST_FILENAME
    assert path.is_file(), f"expected manifest at {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_daily_core_apply_console_shows_step_timings(
    reports_active_current: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        return 0

    assert run_daily_core(_refresh_opts(apply=True), runner=fake_runner) == 0
    out = capsys.readouterr().out
    assert "[daily-core] 3/8 build-mart -- --rebuild --use-email-mart-features -> OK rc=0 elapsed=" in out
    assert "[daily-core] 8/8 status -> OK rc=0 elapsed=" in out


def test_daily_core_plan_only_does_not_write_manifest(
    reports_active_current: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "origenlab_email_pipeline.operator_cli.runner.run_subcommand",
        lambda *a, **k: pytest.fail("run_subcommand must not run for plan-only"),
    )
    assert run_daily_core(_refresh_opts()) == 0
    assert not (reports_active_current / MANIFEST_FILENAME).exists()


def test_daily_core_help_does_not_write_manifest(
    reports_active_current: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "origenlab_email_pipeline.operator_cli.runner.run_subcommand",
        lambda *a, **k: pytest.fail("no subprocess"),
    )
    assert main(["daily-core", "--help"]) == 0
    assert not (reports_active_current / MANIFEST_FILENAME).exists()


def test_run_daily_core_apply_writes_manifest(reports_active_current: Path) -> None:
    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        return 0

    assert run_daily_core(_refresh_opts(apply=True), runner=fake_runner) == 0
    manifest = _read_manifest(reports_active_current)
    assert manifest["workflow"] == "daily-core"
    assert manifest["status"] == "success"
    assert manifest["returncode"] == 0


def test_manifest_path_under_active_current(reports_active_current: Path) -> None:
    path = daily_core_run_manifest_path(reports_active_current.parent.parent)
    assert path == reports_active_current / MANIFEST_FILENAME


def test_manifest_records_legacy_refresh_command_reference(reports_active_current: Path) -> None:
    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        return 0

    run_daily_core(_refresh_opts(apply=True), runner=fake_runner)
    manifest = _read_manifest(reports_active_current)
    assert manifest["equivalent_command"] == _EQUIVALENT_APPLY
    assert manifest["command"] == "uv run origenlab daily-core --apply"


def test_manifest_postgres_mirror_not_included(reports_active_current: Path) -> None:
    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        return 0

    run_daily_core(_refresh_opts(apply=True), runner=fake_runner)
    manifest = _read_manifest(reports_active_current)
    assert manifest["postgres_mirror"] == "not included"
    assert manifest["safety"]["runs_postgres_mirror"] is False


def test_manifest_send_approval_false(reports_active_current: Path) -> None:
    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        return 0

    run_daily_core(_refresh_opts(apply=True), runner=fake_runner)
    manifest = _read_manifest(reports_active_current)
    assert manifest["send_approval"] is False


def test_manifest_includes_eight_steps_no_mirror(reports_active_current: Path) -> None:
    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        return 0

    run_daily_core(_refresh_opts(apply=True), runner=fake_runner)
    manifest = _read_manifest(reports_active_current)
    step_labels = [step["label"] for step in manifest["steps"]]
    assert step_labels == list(_CORE_STEP_LABELS)
    assert "mirror-dashboard" not in step_labels
    assert all(step["returncode"] == 0 for step in manifest["steps"])
    assert all("elapsed_seconds" in step for step in manifest["steps"])
    assert manifest["elapsed_seconds_total"] >= 0


def test_manifest_failure_writes_failed_status_and_stops_at_failing_step(
    reports_active_current: Path,
) -> None:
    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        return 3 if cmd == "build-mart" else 0

    rc = run_daily_core(_refresh_opts(apply=True), runner=fake_runner)
    assert rc == 3
    manifest = _read_manifest(reports_active_current)
    assert manifest["status"] == "failed"
    assert manifest["returncode"] == 3
    step_labels = [step["label"] for step in manifest["steps"]]
    assert step_labels == [
        "gmail-ingest",
        "build-email-mart-features --missing-only --apply",
        "build-mart -- --rebuild --use-email-mart-features",
    ]
    assert manifest["steps"][0]["returncode"] == 0
    assert manifest["steps"][1]["returncode"] == 0
    assert manifest["steps"][2]["returncode"] == 3
    assert manifest["steps"][0]["elapsed_seconds"] >= 0
    assert manifest["steps"][2]["elapsed_seconds"] >= 0
    assert manifest["elapsed_seconds_total"] >= 0


def test_write_daily_core_run_manifest_does_not_touch_campaign_manifest(
    reports_active_current: Path,
) -> None:
    campaign_manifest = reports_active_current / "manifest.json"
    campaign_manifest.write_text('{"kind": "active-current"}\n', encoding="utf-8")

    write_daily_core_run_manifest(
        step_results=[],
        returncode=0,
        manifest_path=reports_active_current / MANIFEST_FILENAME,
    )

    assert campaign_manifest.read_text(encoding="utf-8") == '{"kind": "active-current"}\n'
    assert (reports_active_current / MANIFEST_FILENAME).is_file()


def test_manifest_payload_includes_step_timings_and_total() -> None:
    payload = build_daily_core_run_manifest_payload(
        step_results=[
            StepResult(label="gmail-ingest", returncode=0, elapsed_seconds=12.34),
            StepResult(label="build-mart -- --rebuild", returncode=0, elapsed_seconds=945.32),
        ],
        returncode=0,
    )
    assert payload["steps"] == [
        {"label": "gmail-ingest", "returncode": 0, "elapsed_seconds": 12.34},
        {"label": "build-mart -- --rebuild", "returncode": 0, "elapsed_seconds": 945.32},
    ]
    assert payload["elapsed_seconds_total"] == 957.66
    assert payload["safety"] == {
        "sends_email": False,
        "purges_data": False,
        "applies_ndr_suppressions": False,
        "runs_alembic": False,
        "runs_postgres_mirror": False,
    }
    assert payload["send_approval"] is False
    assert payload["postgres_mirror"] == "not included"


def test_manifest_payload_backwards_compatible_without_elapsed() -> None:
    payload = build_daily_core_run_manifest_payload(
        step_results=[StepResult(label="status", returncode=0)],
        returncode=0,
    )
    assert payload["steps"] == [{"label": "status", "returncode": 0}]
    assert payload["elapsed_seconds_total"] == 0.0
