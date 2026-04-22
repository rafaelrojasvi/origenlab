"""Pure helpers for redacted env reporting and future CRUD / break-glass messaging.

No DB, Gmail, filesystem writes, or environment mutation. Optional ``environ`` is read-only.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping


def redact_secret_value(value: str | None) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "<unset>"
    return "<set>"


def env_presence(
    name: str, environ: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    """Return ``(name, "<set>" | "<unset>")`` without leaking the variable value."""
    m: Mapping[str, str] = os.environ if environ is None else environ
    v = m.get(name)
    return (name, redact_secret_value(v if isinstance(v, str) else None))


def env_presence_report(
    names: Iterable[str], environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    return {n: env_presence(n, environ)[1] for n in names}


def require_apply_for_mutation(apply: bool, operation: str) -> None:
    if not apply:
        raise RuntimeError(
            f"Refusing {operation!r}: mutation was not requested (use --apply or equivalent).",
        )


def format_break_glass_warning(tool: str, risk: str) -> str:
    return f"Break-glass: {tool} — {risk}"
