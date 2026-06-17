"""Tests for apps/api runtime dependency boundary parsing."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_runtime_dependency_boundary.py"
_SPEC = importlib.util.spec_from_file_location(
    "check_runtime_dependency_boundary",
    _MODULE_PATH,
)
assert _SPEC and _SPEC.loader
_boundary = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_boundary)

find_forbidden_packages = _boundary.find_forbidden_packages
parse_uv_tree_package_names = _boundary.parse_uv_tree_package_names

_SAMPLE_CLEAN_TREE = """\
Resolved 12 packages in 1ms
origenlab-api v0.1.0
├── fastapi v0.137.1
│   ├── pydantic v2.13.4
├── origenlab-email-pipeline v0.1.0
│   ├── tqdm v4.67.3
"""

_SAMPLE_ML_TREE = """\
Resolved 20 packages in 1ms
origenlab-api v0.1.0
├── origenlab-email-pipeline v0.1.0
│   ├── torch v2.9.1
│   │   ├── sympy v1.14.0
│   ├── sentence-transformers v5.2.3
"""


def test_parse_uv_tree_package_names_ignores_non_package_lines() -> None:
    names = parse_uv_tree_package_names(_SAMPLE_CLEAN_TREE)
    assert names == {
        "origenlab-api",
        "fastapi",
        "pydantic",
        "origenlab-email-pipeline",
        "tqdm",
    }


def test_find_forbidden_packages_detects_torch_node() -> None:
    found = find_forbidden_packages(_SAMPLE_ML_TREE)
    assert found == {"torch", "sentence-transformers"}


def test_find_forbidden_packages_ignores_torch_in_comments() -> None:
    output = """\
Resolved 1 packages in 1ms
# note: torch is optional for email-pipeline ml group only
origenlab-api v0.1.0
├── fastapi v0.137.1
"""
    assert find_forbidden_packages(output) == set()


def test_find_forbidden_packages_passes_clean_tree() -> None:
    assert find_forbidden_packages(_SAMPLE_CLEAN_TREE) == set()
