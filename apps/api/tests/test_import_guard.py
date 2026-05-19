"""Ensure ``origenlab_api`` resolves to apps/api, not email-pipeline legacy mirror."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_origenlab_api_main_resolves_under_apps_api_src() -> None:
    main = importlib.import_module("origenlab_api.main")
    path = Path(main.__file__).resolve()
    posix = path.as_posix()
    assert "/apps/api/src/origenlab_api/" in posix, f"unexpected main module path: {path}"
    assert "/apps/email-pipeline/src/origenlab_api/" not in posix


def test_origenlab_api_package_root_under_apps_api() -> None:
    pkg = importlib.import_module("origenlab_api")
    root = Path(pkg.__file__).resolve().parent
    assert root.name == "origenlab_api"
    assert root.parent.name == "src"
    assert root.parent.parent.name == "api"
