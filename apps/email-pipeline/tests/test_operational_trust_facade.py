"""Facade re-exports stay stable; urlopen remains patchable on operational_trust."""

from __future__ import annotations

import origenlab_email_pipeline.operational_trust as ot


def test_facade_reexports_public_names() -> None:
    for name in ot.__all__:
        assert hasattr(ot, name), f"missing __all__ export: {name}"


def test_urlopen_is_stdlib_for_patch_target() -> None:
    from urllib.request import urlopen as std_urlopen

    assert ot.urlopen is std_urlopen
