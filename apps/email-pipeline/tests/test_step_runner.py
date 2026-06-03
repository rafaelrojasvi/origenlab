"""Unit tests for core.step_runner (mocked runners only)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from origenlab_email_pipeline.core.step_runner import StepResult, run_step_sequence


@dataclass(frozen=True)
class _FakeStep:
    label: str
    token: str


def test_run_step_sequence_success(capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[str] = []

    def runner(step: _FakeStep) -> int:
        calls.append(step.token)
        return 0

    steps = [_FakeStep(label="alpha", token="a"), _FakeStep(label="beta", token="b")]
    assert run_step_sequence(steps, runner, prefix="[test]") == 0
    assert calls == ["a", "b"]
    out = capsys.readouterr().out
    assert "[test] 1/2 alpha" in out
    assert "[test] 2/2 beta" in out


def test_run_step_sequence_stops_on_first_failure(capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[str] = []

    def runner(step: _FakeStep) -> int:
        calls.append(step.token)
        return 7 if step.token == "b" else 0

    steps = [
        _FakeStep(label="first", token="a"),
        _FakeStep(label="second", token="b"),
        _FakeStep(label="third", token="c"),
    ]
    assert run_step_sequence(steps, runner, prefix="[workflow]") == 7
    assert calls == ["a", "b"]
    err = capsys.readouterr().err
    assert "[workflow] failed at step 2/3: second (exit 7)" in err


def test_run_step_sequence_failure_message_includes_step_index_name_and_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def runner(_step: _FakeStep) -> int:
        return 42

    steps = [_FakeStep(label="build-mart -- --rebuild", token="mart")]
    assert run_step_sequence(steps, runner, prefix="[refresh-dashboard]") == 42
    err = capsys.readouterr().err
    assert "[refresh-dashboard] failed at step 1/1: build-mart -- --rebuild (exit 42)" in err


def test_step_result_dataclass() -> None:
    result = StepResult(label="status", returncode=0)
    assert result.label == "status"
    assert result.returncode == 0
