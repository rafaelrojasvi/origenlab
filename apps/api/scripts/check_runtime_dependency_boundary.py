#!/usr/bin/env python3
"""Fail if ML-heavy packages appear in apps/api effective uv dependency trees."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PACKAGES: frozenset[str] = frozenset(
    {
        "torch",
        "torchvision",
        "torchaudio",
        "transformers",
        "sentence-transformers",
        "faiss-cpu",
        "hdbscan",
        "scikit-learn",
        "sklearn",
    }
)

# uv tree package nodes: "├── torch v2.1.0" or "origenlab-api v0.1.0"
_PACKAGE_NODE_RE = re.compile(
    r"^(?:[│├└─\s]*)"
    r"(?P<name>[a-zA-Z0-9][a-zA-Z0-9._-]*(?:\[[^\]]+\])?)"
    r"\s+v[^\s(]",
)


def normalize_package_name(raw_name: str) -> str:
    """Strip uv extras suffix, e.g. psycopg[binary] -> psycopg."""
    return raw_name.split("[", 1)[0]


def parse_uv_tree_package_names(tree_output: str) -> set[str]:
    """Extract package names from `uv tree` stdout (package nodes only)."""
    names: set[str] = set()
    for line in tree_output.splitlines():
        match = _PACKAGE_NODE_RE.match(line)
        if not match:
            continue
        names.add(normalize_package_name(match.group("name")))
    return names


def find_forbidden_packages(
    tree_output: str,
    forbidden: frozenset[str] = FORBIDDEN_PACKAGES,
) -> set[str]:
    """Return forbidden package names present as uv tree package nodes."""
    present = parse_uv_tree_package_names(tree_output)
    return present & forbidden


def run_uv_tree(*args: str) -> str:
    result = subprocess.run(
        ["uv", "tree", *args],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return result.stdout


def check_runtime_dependency_boundary() -> list[tuple[str, str]]:
    """Run uv tree checks; return (tree_label, forbidden_package) violations."""
    violations: list[tuple[str, str]] = []
    checks = (
        ("runtime (--no-dev)", ("--no-dev",)),
        ("dev (--group dev)", ("--group", "dev")),
    )
    for label, tree_args in checks:
        output = run_uv_tree(*tree_args)
        for package in sorted(find_forbidden_packages(output)):
            violations.append((label, package))
    return violations


def main() -> int:
    violations = check_runtime_dependency_boundary()
    if not violations:
        print("ok: apps/api runtime and dev dependency trees are ML-free")
        return 0

    for label, package in violations:
        print(
            f"error: forbidden package {package!r} found in {label} uv tree",
            file=sys.stderr,
        )
    print(
        "error: apps/api must not depend on ML-heavy packages in effective runtime/dev trees",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
