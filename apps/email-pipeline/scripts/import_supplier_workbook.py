#!/usr/bin/env python3
"""Import DeepSearch supplier workbook (structured sourcing) into SQLite.

Expects sheets: Oportunidades_50, Contacto_15, Evidencias, Prioridades, Exclusiones,
Anexo_CSV_NoRepetido, Resumen (see ``supplier_workbook.EXPECTED_SHEETS``).

Usage::

    uv run python scripts/import_supplier_workbook.py \\
        --xlsx /path/to/OrigenLab_DeepSearch_Proveedores_Internacionales_actualizado.xlsx

Optional: ``--validate-only`` to run structural checks without writing (exit code non-zero on errors).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.supplier_workbook import (
    collect_workbook_validation_issues,
    import_supplier_workbook,
    partition_supplier_validation_issues,
)
from origenlab_email_pipeline.supplier_schema import ensure_supplier_tables


def main() -> int:
    ap = argparse.ArgumentParser(description="Import supplier DeepSearch workbook into SQLite.")
    ap.add_argument("--xlsx", "-x", type=Path, required=True, help="Path to .xlsx workbook.")
    ap.add_argument(
        "--informe-docx",
        type=Path,
        default=None,
        help="Optional Spanish narrative .docx; first paragraphs appended to batch resumen_note.",
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config).")
    ap.add_argument(
        "--strict-validate",
        action="store_true",
        help="Abort import if validation errors exist (default: import anyway).",
    )
    ap.add_argument(
        "--validate-only",
        action="store_true",
        help="Run validation checks only; exit 1 on errors.",
    )
    args = ap.parse_args()
    xlsx = args.xlsx.resolve()
    if not xlsx.is_file():
        print(f"File not found: {xlsx}", file=sys.stderr)
        return 1

    issues = collect_workbook_validation_issues(xlsx)
    err, warn = partition_supplier_validation_issues(issues)
    for w in warn:
        print(f"WARN {w}", file=sys.stderr)
    for e in err:
        print(f"ERROR {e}", file=sys.stderr)

    if args.validate_only:
        return 1 if err else 0

    if err and args.strict_validate:
        print("Validation errors; not importing.", file=sys.stderr)
        return 1

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    conn.execute("PRAGMA busy_timeout=30000")
    ensure_supplier_tables(conn)
    docx = args.informe_docx.resolve() if args.informe_docx else None
    batch_id = import_supplier_workbook(conn, xlsx, informe_docx=docx)
    print(f"Imported batch_id={batch_id} into {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
