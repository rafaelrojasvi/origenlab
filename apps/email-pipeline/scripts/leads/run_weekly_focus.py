#!/usr/bin/env python3
"""Build a canonical weekly focus package for lead outreach.

Outputs:
- CSV operativo: leads_weekly_focus.csv
- Resumen markdown (ES): leads_weekly_focus_summary_es.md

Safe mode:
- No mueve ni borra archivos existentes.
- Solo clasifica archivos (USAR / REFERENCIA / NO OPERATIVO) en el resumen.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_export_queries import (
    sql_left_join_best_org_match,
    sql_upstream_active_lead_master,
)
from origenlab_email_pipeline.leads_schema import ensure_leads_tables

_LM_UPSTREAM_ACTIVE = sql_upstream_active_lead_master("lm")
_JOIN_BEST_ORG = sql_left_join_best_org_match(variant="archive_only")


FOCUS_COLS = [
    "id_lead",
    "fit_bucket",
    "priority_score",
    "org_name",
    "buyer_kind",
    "equipment_match_tags",
    "lab_context_score",
    "already_in_archive_flag",
    "source_url",
    "evidence_summary",
    "status",
    "next_action",
]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def _count_any_contact_rows(rows: list[dict[str, str]]) -> int:
    keys = (
        "nombre_contacto_compras",
        "email_publico_compras",
        "telefono_publico_compras",
        "nombre_contacto_tecnico",
        "email_publico_tecnico",
        "telefono_publico_tecnico",
        "email_contacto_general",
        "telefono_contacto_general",
    )
    n = 0
    for row in rows:
        if any((row.get(k) or "").strip() for k in keys):
            n += 1
    return n


def _source_count(conn: sqlite3.Connection, source_name: str) -> int:
    return conn.execute(
        f"""
        SELECT COUNT(*) FROM lead_master lm
        WHERE lm.source_name = ? AND {_LM_UPSTREAM_ACTIVE}
        """,
        (source_name,),
    ).fetchone()[0]


def _build_focus_rows(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        f"""
        SELECT
          lm.id AS id_lead,
          COALESCE(lm.fit_bucket, 'low_fit') AS fit_bucket,
          COALESCE(lm.priority_score, 0) AS priority_score,
          lm.org_name,
          lm.buyer_kind,
          lm.equipment_match_tags,
          COALESCE(lm.lab_context_score, 0) AS lab_context_score,
          COALESCE(m.already_in_archive_flag, 0) AS already_in_archive_flag,
          lm.source_url,
          lm.evidence_summary,
          lm.status,
          lm.next_action
        FROM lead_master lm
        {_JOIN_BEST_ORG}
        WHERE {_LM_UPSTREAM_ACTIVE}
          AND COALESCE(lm.fit_bucket, 'low_fit') IN ('high_fit', 'medium_fit')
        ORDER BY
          CASE COALESCE(lm.fit_bucket, 'low_fit')
            WHEN 'high_fit' THEN 0
            WHEN 'medium_fit' THEN 1
            ELSE 2
          END,
          COALESCE(m.already_in_archive_flag, 0) ASC,
          COALESCE(lm.priority_score, 0) DESC,
          CASE WHEN lm.equipment_match_tags IS NOT NULL AND length(trim(lm.equipment_match_tags)) > 0 THEN 0 ELSE 1 END,
          COALESCE(lm.lab_context_score, 0) DESC,
          lm.last_seen_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def _write_focus_csv(path: Path, rows: list[sqlite3.Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(FOCUS_COLS)
        for row in rows:
            w.writerow([row[c] for c in FOCUS_COLS])


def _classify_files(files: list[Path]) -> dict[str, list[str]]:
    out = {"USAR": [], "REFERENCIA": [], "NO OPERATIVO": []}
    for p in files:
        name = p.name
        if name in {
            "leads_contact_hunt_current.csv",
            "leads_contact_hunt_for_deepsearch.csv",
            "leads_weekly_focus.csv",
            "leads_weekly_focus_summary_es.md",
        }:
            out["USAR"].append(name)
        elif name in {
            "leads_shortlist_es.csv",
            "leads_client_review_es.csv",
            "leads_contact_hunt_current_merged.csv",
            "leads_active_unified.csv",
            "leads_shortlist.csv",
            "leads_client_review.csv",
        }:
            out["REFERENCIA"].append(name)
        elif "DEEPRESEARCH" in name or "top_hosp_univ_netnew" in name:
            out["REFERENCIA"].append(name)
        elif name in {"leads_export.csv", "leads_export_es.csv"}:
            out["NO OPERATIVO"].append(name)
    return out


def _count_enrichment_contacts(conn: sqlite3.Connection) -> tuple[int, dict[str, int]]:
    rows = conn.execute("SELECT enrichment_json FROM lead_outreach_enrichment").fetchall()
    stats = {
        "nombre_contacto_compras": 0,
        "email_publico_compras": 0,
        "telefono_publico_compras": 0,
        "nombre_contacto_tecnico": 0,
        "email_publico_tecnico": 0,
        "telefono_publico_tecnico": 0,
    }
    with_any = 0
    for (j,) in rows:
        try:
            d = json.loads(j or "{}")
        except (TypeError, json.JSONDecodeError):
            d = {}
        row_has = False
        for k in stats:
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                stats[k] += 1
                row_has = True
        if row_has:
            with_any += 1
    return with_any, stats


def _build_summary(
    *,
    summary_path: Path,
    csv_focus_path: Path,
    focus_rows: list[sqlite3.Row],
    total_leads: int,
    chilecompra_leads: int,
    scored_rows: int,
    enrichment_total: int,
    enrichment_with_contact: int,
    enrichment_stats: dict[str, int],
    current_rows: int,
    current_with_contact: int,
    merged_rows: int,
    merged_with_contact: int,
    file_groups: dict[str, list[str]],
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    if current_rows > 0 and current_with_contact == 0:
        warnings.append(
            "- `leads_contact_hunt_current.csv` no tiene campos de contacto llenos (normal si todavía no hubo research)."
        )
    if merged_rows > 0 and merged_with_contact == 0:
        warnings.append(
            "- `leads_contact_hunt_current_merged.csv` tiene 0 filas con contacto; revisar si el enrichment usado corresponde a IDs actuales."
        )
    if enrichment_total > 0 and enrichment_with_contact == 0:
        warnings.append(
            "- `lead_outreach_enrichment` tiene filas, pero 0 con campos de contacto; hubo import sin datos de contacto útiles."
        )
    if scored_rows == 0 and chilecompra_leads > 0:
        warnings.append("- ChileCompra no está scoreado (`priority_score` en 0 filas). Ejecutar `scripts/leads/leads_score.py`.")

    top_lines = []
    for i, row in enumerate(focus_rows[:15], start=1):
        top_lines.append(
            f"{i}. `id_lead={row['id_lead']}` **{row['org_name'] or 'Sin nombre'}** | fit={row['fit_bucket']} | "
            f"score={row['priority_score']} | buyer={row['buyer_kind'] or '-'} | "
            f"equip={row['equipment_match_tags'] or '-'} | in_archive={row['already_in_archive_flag']}"
        )

    lines: list[str] = []
    lines.append("# Resumen semanal de foco comercial (ES)")
    lines.append("")
    lines.append("## Salidas canónicas")
    lines.append(f"- CSV operativo: `{csv_focus_path}`")
    lines.append(f"- Este resumen: `{summary_path}`")
    lines.append(
        "- El CSV incluye **`id_lead`** para cruzar con `leads_contact_hunt_current.csv`. "
        "Paquete para cliente: `uv run python scripts/reports/build_leads_client_pack.py` → `reports/out/client_pack_latest/`."
    )
    lines.append("")
    lines.append("## Estado DB")
    lines.append(f"- `lead_master` total: **{total_leads}**")
    lines.append(f"- `lead_master` ChileCompra: **{chilecompra_leads}**")
    lines.append(f"- ChileCompra con `priority_score` no nulo: **{scored_rows}**")
    lines.append(f"- `lead_outreach_enrichment` filas: **{enrichment_total}**")
    lines.append(f"- `lead_outreach_enrichment` con algún contacto: **{enrichment_with_contact}**")
    lines.append("")
    lines.append("## Contact-hunt actual")
    lines.append(f"- `leads_contact_hunt_current.csv`: filas={current_rows}, con contacto={current_with_contact}")
    lines.append(f"- `leads_contact_hunt_current_merged.csv`: filas={merged_rows}, con contacto={merged_with_contact}")
    lines.append("")
    lines.append("## Métricas de contacto en enrichment")
    lines.append("- " + ", ".join(f"{k}={v}" for k, v in enrichment_stats.items()))
    lines.append("")
    lines.append("## Clasificación de archivos")
    for k in ("USAR", "REFERENCIA", "NO OPERATIVO"):
        items = file_groups.get(k, [])
        if items:
            lines.append(f"- **{k}**: " + ", ".join(f"`{x}`" for x in sorted(items)))
    lines.append("")
    lines.append("## Top leads accionables (semanal)")
    if top_lines:
        lines.extend(f"- {t}" for t in top_lines)
    else:
        lines.append("- No hay filas high_fit/medium_fit para el criterio actual.")
    lines.append("")
    lines.append("## Alertas")
    if warnings:
        lines.extend(warnings)
    else:
        lines.append("- Sin alertas críticas.")
    lines.append("")
    lines.append("## Próximo ciclo recomendado")
    lines.append("1. Trabajar solo `leads_contact_hunt_current.csv` (top 50).")
    lines.append("2. Enriquecer contactos y generar merged.")
    lines.append("3. Importar con `import_contact_hunt_to_sqlite.py --promote-procurement`.")
    lines.append("4. Re-ejecutar este script y validar que suban contactos.")
    lines.append("")
    summary_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run weekly safe canonical focus workflow for leads.")
    ap.add_argument(
        "--out-csv",
        type=Path,
        default=Path("reports/out/active/leads_weekly_focus.csv"),
        help="Output CSV path (default: reports/out/active/leads_weekly_focus.csv)",
    )
    ap.add_argument(
        "--out-summary",
        type=Path,
        default=Path("reports/out/active/leads_weekly_focus_summary_es.md"),
        help="Output markdown summary path (default: reports/out/active/leads_weekly_focus_summary_es.md)",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=150,
        help="How many high/medium-fit rows in weekly focus CSV (default: 150).",
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    ensure_leads_tables(conn)

    total_leads = conn.execute(
        f"SELECT COUNT(*) FROM lead_master lm WHERE {_LM_UPSTREAM_ACTIVE}"
    ).fetchone()[0]
    chilecompra_leads = _source_count(conn, "chilecompra")
    scored_rows = conn.execute(
        f"""
        SELECT COUNT(*) FROM lead_master lm
        WHERE lm.source_name = 'chilecompra'
          AND lm.priority_score IS NOT NULL
          AND {_LM_UPSTREAM_ACTIVE}
        """
    ).fetchone()[0]

    if _table_exists(conn, "lead_outreach_enrichment"):
        enrichment_total = conn.execute("SELECT COUNT(*) FROM lead_outreach_enrichment").fetchone()[0]
        enrichment_with_contact, enrichment_stats = _count_enrichment_contacts(conn)
    else:
        enrichment_total = 0
        enrichment_with_contact = 0
        enrichment_stats = {
            "nombre_contacto_compras": 0,
            "email_publico_compras": 0,
            "telefono_publico_compras": 0,
            "nombre_contacto_tecnico": 0,
            "email_publico_tecnico": 0,
            "telefono_publico_tecnico": 0,
        }

    focus_rows = _build_focus_rows(conn, args.top)
    conn.close()
    _write_focus_csv(args.out_csv, focus_rows)

    reports_dir = args.out_csv.parent
    reports_out_root = reports_dir.parent if reports_dir.name == "active" else reports_dir
    current_headers, current_rows = _read_csv(reports_out_root / "active" / "leads_contact_hunt_current.csv")
    merged_headers, merged_rows = _read_csv(reports_out_root / "active" / "leads_contact_hunt_current_merged.csv")
    _ = (current_headers, merged_headers)
    current_with_contact = _count_any_contact_rows(current_rows)
    merged_with_contact = _count_any_contact_rows(merged_rows)

    # No incluir archive/ (evita listar duplicados ya movidos por prepare_active_workspace).
    files = [p for p in reports_out_root.glob("*") if p.is_file()]
    files.extend([p for p in (reports_out_root / "active").glob("*") if p.is_file()])
    files.extend([p for p in (reports_out_root / "reference").glob("*") if p.is_file()])
    file_groups = _classify_files(files)

    _build_summary(
        summary_path=args.out_summary,
        csv_focus_path=args.out_csv,
        focus_rows=focus_rows,
        total_leads=total_leads,
        chilecompra_leads=chilecompra_leads,
        scored_rows=scored_rows,
        enrichment_total=enrichment_total,
        enrichment_with_contact=enrichment_with_contact,
        enrichment_stats=enrichment_stats,
        current_rows=len(current_rows),
        current_with_contact=current_with_contact,
        merged_rows=len(merged_rows),
        merged_with_contact=merged_with_contact,
        file_groups=file_groups,
    )

    print(f"Wrote weekly focus CSV: {args.out_csv}")
    print(f"Wrote weekly summary (ES): {args.out_summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
