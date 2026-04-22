from __future__ import annotations

import pytest

from origenlab_email_pipeline.core.safety import (
    env_presence,
    env_presence_report,
    format_break_glass_warning,
    redact_secret_value,
    require_apply_for_mutation,
)


def test_redact_never_leaks_value() -> None:
    assert redact_secret_value("secret") == "<set>"
    assert redact_secret_value("  x  ") == "<set>"
    assert redact_secret_value("") == "<unset>"
    assert redact_secret_value(None) == "<unset>"
    assert "secret" not in redact_secret_value("secret")


def test_env_presence_report_only_set_or_unset() -> None:
    r = env_presence_report(
        ("A", "B"),
        {"A": "x", "B": ""},
    )
    assert r == {"A": "<set>", "B": "<unset>"}
    n, s = env_presence("K", {"K": "hidden"})
    assert n == "K" and s == "<set>"
    assert "hidden" not in repr((n, s))


def test_require_apply_for_mutation() -> None:
    require_apply_for_mutation(True, "reset")
    with pytest.raises(RuntimeError, match="Refusing 'wipe'"):
        require_apply_for_mutation(False, "wipe")


def test_format_break_glass_warning() -> None:
    s = format_break_glass_warning("tools/purge_x.py", "deletes rows")
    assert "tools/purge_x.py" in s
    assert "deletes" in s


def test_core_imports_safety() -> None:
    from origenlab_email_pipeline.core import safety  # noqa: PLC0415

    assert safety.__name__ == "origenlab_email_pipeline.core.safety"
