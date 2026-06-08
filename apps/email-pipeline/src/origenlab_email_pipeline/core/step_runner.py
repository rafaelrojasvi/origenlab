"""Minimal sequential step runner for operator CLI workflows."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

StepRunner = Callable[[Any], int]


@dataclass(frozen=True)
class StepResult:
    """Outcome of one step in a sequence."""

    label: str
    returncode: int
    elapsed_seconds: float | None = None


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
    step_results: list[StepResult] | None = None,
) -> int:
    """Run steps in order via ``runner(step)``; stop on first non-zero exit."""
    total = len(steps)
    for i, step in enumerate(steps, 1):
        label = _step_label(step)
        t0 = time.perf_counter()
        rc = int(runner(step))
        elapsed = round(time.perf_counter() - t0, 2)
        status = "OK" if rc == 0 else "FAIL"
        print(f"{prefix} {i}/{total} {label} -> {status} rc={rc} elapsed={elapsed:.2f}s")
        if step_results is not None:
            step_results.append(
                StepResult(label=label, returncode=rc, elapsed_seconds=elapsed)
            )
        if rc != 0:
            print(
                f"{prefix} failed at step {i}/{total}: {label} (exit {rc})",
                file=sys.stderr,
            )
            return rc
    return 0
