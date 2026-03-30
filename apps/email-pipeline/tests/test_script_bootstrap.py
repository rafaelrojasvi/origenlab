"""``scripts/_bootstrap.py`` resolves the email-pipeline app root deterministically."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_bootstrap():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "_bootstrap.py"
    spec = importlib.util.spec_from_file_location("_script_bootstrap_test", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[call-arg]
    return mod


def test_bootstrap_app_root_contains_pyproject() -> None:
    bootstrap = _load_bootstrap()
    assert (bootstrap.APP_ROOT / "pyproject.toml").is_file()


def test_bootstrap_scripts_dir_is_scripts() -> None:
    bootstrap = _load_bootstrap()
    assert bootstrap.SCRIPTS_DIR.name == "scripts"
    assert bootstrap.SCRIPTS_DIR == bootstrap.APP_ROOT / "scripts"


def test_two_level_scripts_dir_parents2_is_app_root() -> None:
    """``scripts/<pkg>/file.py`` → ``parents[2]`` must be apps/email-pipeline (not ``scripts/``)."""
    root = Path(__file__).resolve().parents[1]
    mart_script = root / "scripts" / "mart" / "build_business_mart.py"
    assert mart_script.is_file()
    assert Path(mart_script).resolve().parents[2] == root
