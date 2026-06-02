from __future__ import annotations

import pytest

from origenlab_email_pipeline.core.safety import (
    env_presence,
    env_presence_report,
    format_break_glass_warning,
    format_script_deprecation_warning,
    print_script_deprecation_warning,
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


def test_format_script_deprecation_warning_includes_replacement() -> None:
    s = format_script_deprecation_warning(
        "scripts/qa/example.py",
        replacement="scripts/qa/canonical.py",
        note="optional note",
    )
    assert "DEPRECATED" in s
    assert "scripts/qa/example.py" in s
    assert "scripts/qa/canonical.py" in s
    assert "optional note" in s
    assert "not for new operator work" in s.lower()


def test_print_script_deprecation_warning_writes_stderr(capsys) -> None:
    print_script_deprecation_warning(
        "scripts/tools/legacy.py",
        replacement="scripts/tools/canonical.py",
    )
    err = capsys.readouterr().err
    assert "DEPRECATED" in err
    assert "legacy.py" in err
    assert "canonical.py" in err


def test_core_imports_safety() -> None:
    from origenlab_email_pipeline.core import safety  # noqa: PLC0415

    assert safety.__name__ == "origenlab_email_pipeline.core.safety"
