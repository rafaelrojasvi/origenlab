"""Minimal sequential step runner for operator CLI workflows."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

StepRunner = Callable[[Any], int]


@dataclass(frozen=True)
class StepResult:
    """Outcome of one step in a sequence."""

    label: str
    returncode: int


def _step_label(step: Any) -> str:
    label = getattr(step, "label", None)
    if label is not None:
        return str(label)
    return str(step)


def run_step_sequence(
    steps: Sequence[Any],
    runner: StepRunner,
    *,
    prefix: str = "[step]",
) -> int:
    """Run steps in order via ``runner(step)``; stop on first non-zero exit."""
    total = len(steps)
    for i, step in enumerate(steps, 1):
        label = _step_label(step)
        print(f"{prefix} {i}/{total} {label}")
        rc = int(runner(step))
        if rc != 0:
            print(
                f"{prefix} failed at step {i}/{total}: {label} (exit {rc})",
                file=sys.stderr,
            )
            return rc
    return 0
