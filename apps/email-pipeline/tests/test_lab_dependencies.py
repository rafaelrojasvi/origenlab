"""Lab (OpenAI) dependencies must stay optional — not default daily/operator install."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = REPO / "pyproject.toml"


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_openai_not_in_default_project_dependencies() -> None:
    deps = _pyproject()["project"]["dependencies"]
    assert not any(str(d).startswith("openai") for d in deps)


def test_pyproject_declares_lab_group_with_openai() -> None:
    lab = _pyproject()["dependency-groups"]["lab"]
    assert any("openai>=" in str(d) for d in lab)


def test_operator_cli_importable_without_openai_in_default_deps() -> None:
    """Operator CLI graph must not require OpenAI as a default dependency."""
    import origenlab_email_pipeline.cli as cli

    assert callable(cli.main)
