#!/usr/bin/env python3
"""Build equipment-first tender queue from Licitacion_Publicada.csv."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from origenlab_email_pipeline.equipment_first_licitacion_queue import (
    build_from_csv,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = (
    ROOT / "reports/out/active/current/equipment_first_opportunity_queue_20260518.csv"
)


def resolve_csv_path(raw: Path) -> Path:
    if raw.suffix.lower() == ".zip":
        with zipfile.ZipFile(raw) as zf:
            name = next(n for n in zf.namelist() if n.endswith("Licitacion_Publicada.csv"))
            extract_to = ROOT / "reports/out/active/current/_cache_licitacion_publicada.csv"
            extract_to.write_bytes(zf.read(name))
            return extract_to
    return raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("/mnt/c/Users/Rafael/Downloads/Licitacion_Publicada (4).zip"),
        help="Licitacion_Publicada.csv or .zip export",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    csv_path = resolve_csv_path(args.source)
    stats = build_from_csv(csv_path, args.out)
    print(f"Wrote {args.out}")
    print(stats)


if __name__ == "__main__":
    main()
