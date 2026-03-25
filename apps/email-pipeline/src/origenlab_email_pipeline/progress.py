"""Small helpers for consistent CLI progress bars.

Uses tqdm when available, otherwise falls back to plain iteration.
"""
from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterator
from typing import Iterable, TypeVar

T = TypeVar("T")

try:  # pragma: no cover - trivial import guard
    from tqdm import tqdm  # type: ignore
except Exception:  # pragma: no cover - when tqdm is not installed
    tqdm = None  # type: ignore


def print_compute_banner(
    *,
    uses_gpu: bool,
    workload: str,
    extra_detail: str | None = None,
) -> None:
    """stderr lines: PyTorch/CUDA visibility + whether this script uses the GPU."""
    print(f"[compute] {workload}", file=sys.stderr, flush=True)
    try:
        import torch

        print(f"[compute] PyTorch {torch.__version__}", file=sys.stderr, flush=True)
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            print(f"[compute] CUDA: available — {name}", file=sys.stderr, flush=True)
        else:
            print(
                "[compute] CUDA: not available to PyTorch (CPU build, no driver, or no GPU)",
                file=sys.stderr,
                flush=True,
            )
    except ImportError:
        print(
            "[compute] PyTorch: not installed — cannot report CUDA (install ml group to enable GPU for embeddings)",
            file=sys.stderr,
            flush=True,
        )
    if uses_gpu:
        print(
            "[compute] This run may use GPU for model inference (e.g. sentence-transformers).",
            file=sys.stderr,
            flush=True,
        )
    else:
        print(
            "[compute] This step is CPU + SQLite only; GPU will stay idle.",
            file=sys.stderr,
            flush=True,
        )
    if extra_detail:
        print(f"[compute] {extra_detail}", file=sys.stderr, flush=True)


def tqdm_stderr(
    iterable: Iterable[T],
    *,
    total: int | None = None,
    desc: str = "",
    unit: str = "it",
    **kwargs: object,
) -> Iterable[T]:
    """tqdm on stderr with ``disable=False`` so bars still show in IDE / non-TTY pipes."""
    if tqdm is None:
        return iterable
    opts: dict[str, object] = {
        "file": sys.stderr,
        "disable": False,
        "dynamic_ncols": True,
        "mininterval": 0.08,
        "bar_format": "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
    }
    opts.update(kwargs)
    return tqdm(iterable, total=total, desc=desc, unit=unit, **opts)  # type: ignore[arg-type]


def iter_sqlite_email_batches_with_progress(
    conn: sqlite3.Connection,
    cur: sqlite3.Cursor,
    *,
    desc: str,
    batch_size: int = 8000,
) -> Iterator[list]:
    """Yield ``fetchmany`` batches over a cursor while tqdm tracks rows vs ``emails`` count."""
    row = conn.execute("SELECT COUNT(*) FROM emails").fetchone()
    total = int(row[0]) if row and row[0] is not None else 0
    print_compute_banner(
        uses_gpu=False,
        workload="SQLite scan (emails table)",
        extra_detail=f"Progress vs {total:,} rows in `emails`",
    )
    if tqdm is None or total <= 0:
        while True:
            batch = cur.fetchmany(batch_size)
            if not batch:
                break
            yield batch
        return
    with tqdm(
        total=total,
        desc=desc,
        unit="rows",
        dynamic_ncols=True,
        mininterval=0.12,
        file=sys.stderr,
        disable=False,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
    ) as pbar:
        while True:
            batch = cur.fetchmany(batch_size)
            if not batch:
                break
            yield batch
            pbar.update(len(batch))


def iter_with_progress(
    iterable: Iterable[T],
    *,
    total: int | None = None,
    desc: str = "",
    unit: str = "items",
) -> Iterator[T]:
    """Wrap an iterable with a tqdm progress bar when available.

    - If tqdm is installed, shows a bar with total/ETA.
    - If not, just returns the original iterable unchanged.
    """
    if tqdm is None or (total is not None and total <= 0):
        # Fallback: no tqdm or nothing to show
        return iter(iterable)
    return tqdm(
        iterable,
        total=total,
        desc=desc,
        unit=unit,
        dynamic_ncols=True,
        file=sys.stderr,
        disable=False,
        miniters=1,
        mininterval=0.08,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
    )

