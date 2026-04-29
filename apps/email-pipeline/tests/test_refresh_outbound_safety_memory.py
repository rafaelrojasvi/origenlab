from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "refresh_outbound_safety_memory.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("refresh_outbound_safety_memory", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cp(rc: int, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)


def test_success_all_steps_ready_with_warnings_allowed() -> None:
    mod = _load_module()
    side_effects = [_cp(0, "{}\n")] * 5 + [_cp(0, "Verdict: ready_with_warnings\n")]
    with patch.object(mod.subprocess, "run", side_effect=side_effects) as mocked:
        rc = mod.main([])
    assert rc == 0
    assert mocked.call_count == 6


def test_fail_on_first_hard_failure_stops_early() -> None:
    mod = _load_module()
    side_effects = [_cp(0, "{}\n"), _cp(1, "", "boom\n")]
    with patch.object(mod.subprocess, "run", side_effect=side_effects) as mocked:
        rc = mod.main([])
    assert rc == 1
    assert mocked.call_count == 2


def test_fail_on_ready_with_warnings_flag() -> None:
    mod = _load_module()
    side_effects = [_cp(0, "{}\n")] * 5 + [_cp(0, "Verdict: ready_with_warnings\n")]
    with patch.object(mod.subprocess, "run", side_effect=side_effects):
        rc = mod.main(["--fail-on-ready-with-warnings"])
    assert rc == 1
