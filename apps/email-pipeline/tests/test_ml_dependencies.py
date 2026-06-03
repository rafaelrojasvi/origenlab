"""ML (hdbscan) dependencies must stay optional — not default daily/operator install."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = REPO / "pyproject.toml"


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_hdbscan_not_in_default_project_dependencies() -> None:
    deps = _pyproject()["project"]["dependencies"]
    assert not any(str(d).startswith("hdbscan") for d in deps)


def test_pyproject_declares_ml_group_with_hdbscan() -> None:
    ml = _pyproject()["dependency-groups"]["ml"]
    assert any("hdbscan>=" in str(d) for d in ml)


def test_openai_still_in_lab_not_default() -> None:
    deps = _pyproject()["project"]["dependencies"]
    lab = _pyproject()["dependency-groups"]["lab"]
    assert not any(str(d).startswith("openai") for d in deps)
    assert any("openai>=" in str(d) for d in lab)
