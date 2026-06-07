from __future__ import annotations

import csv
from pathlib import Path


def read_dict_rows(path: Path, *, encoding: str = "utf-8") -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding=encoding) as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def write_dict_rows(
    path: Path,
    headers: list[str],
    rows: list[dict[str, str]],
    *,
    encoding: str = "utf-8",
    extrasaction: str = "ignore",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction=extrasaction)
        writer.writeheader()
        writer.writerows(rows)
