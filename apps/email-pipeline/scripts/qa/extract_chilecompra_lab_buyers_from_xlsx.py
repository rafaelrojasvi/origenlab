#!/usr/bin/env python3
"""Extract likely lab/clinical/QC-related buyer organizations from ChileCompra 'Licitación Publicada' XLSX."""

from __future__ import annotations

import argparse
from pathlib import Path

from origenlab_email_pipeline.chilecompra_licitacion_lab_buyers import extract_lab_buyers_to_csv


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--xlsx",
        type=Path,
        required=True,
        help="Path to Licitacion_Publicada.xlsx (unzipped from ChileCompra export).",
    )
    ap.add_argument(
        "--out-csv",
        type=Path,
        required=True,
        help="Output CSV path (unique compradores with sample tender ids).",
    )
    args = ap.parse_args()
    stats = extract_lab_buyers_to_csv(xlsx_path=args.xlsx, out_csv=args.out_csv)
    print(stats)


if __name__ == "__main__":
    main()
