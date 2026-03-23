#!/usr/bin/env python3
"""Build a static Spanish client pack from SQLite (lead_master + matches + enrichment).

Writes to ``reports/out/client_pack_latest/`` (overwrites previous pack files):

- index.html — resumen visual sobrio
- resumen_ejecutivo_es.md — narrativa ejecutiva
- anexo_leads.csv — tabla anexa con id_lead
- summary.json — métricas para tooling

SQLite es la fuente de verdad; este paquete es solo proyección.

Usage::

    uv run python scripts/reports/build_leads_client_pack.py
    uv run python scripts/reports/build_leads_client_pack.py --db /path/to/emails.sqlite --limit 400
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.leads_schema import ensure_leads_tables

# Align with operational_trust.db_lead_totals / publish_gate (blank fit → low_fit).
_LM_FIT = "COALESCE(NULLIF(TRIM(lm.fit_bucket), ''), 'low_fit')"
_FIT_GROUP = "COALESCE(NULLIF(TRIM(fit_bucket), ''), 'low_fit')"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def _enrichment_with_contact_count(conn: sqlite3.Connection) -> tuple[int, int]:
    if not _table_exists(conn, "lead_outreach_enrichment"):
        return 0, 0
    total = conn.execute("SELECT COUNT(*) FROM lead_outreach_enrichment").fetchone()[0]
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
    with_any = 0
    for (j,) in conn.execute("SELECT enrichment_json FROM lead_outreach_enrichment"):
        try:
            d = json.loads(j or "{}")
        except (TypeError, json.JSONDecodeError):
            d = {}
        if any(isinstance(d.get(k), str) and d[k].strip() for k in keys):
            with_any += 1
    return int(total), with_any


def _archive_split_counts(conn: sqlite3.Connection) -> tuple[int, int]:
    """Leads with best match already_in_archive_flag=1 vs net-new (0 or no match)."""
    row = conn.execute(
        """
        SELECT
          SUM(CASE WHEN COALESCE(m.already_in_archive_flag, 0) = 1 THEN 1 ELSE 0 END),
          SUM(CASE WHEN COALESCE(m.already_in_archive_flag, 0) = 0 THEN 1 ELSE 0 END)
        FROM lead_master lm
        LEFT JOIN (
          SELECT m1.lead_id, m1.already_in_archive_flag
          FROM lead_matches_existing_orgs m1
          WHERE m1.id = (
            SELECT MIN(m2.id) FROM lead_matches_existing_orgs m2 WHERE m2.lead_id = m1.lead_id
          )
        ) m ON m.lead_id = lm.id
        """
    ).fetchone()
    in_a = int(row[0] or 0)
    net = int(row[1] or 0)
    return in_a, net


def main() -> int:
    ap = argparse.ArgumentParser(description="Build leads client pack (HTML + MD + CSV + JSON).")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "client_pack_latest",
        help="Output directory (default: reports/out/client_pack_latest)",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=400,
        help="Max rows in anexo_leads.csv (default: 400)",
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.iterdir():
        if p.is_file():
            p.unlink()

    conn = connect(db_path)
    ensure_leads_tables(conn)

    total_leads = conn.execute("SELECT COUNT(*) FROM lead_master").fetchone()[0]
    fit_rows = conn.execute(
        f"""
        SELECT {_FIT_GROUP} AS fb, COUNT(*)
        FROM lead_master GROUP BY fb
        """
    ).fetchall()
    fit_counts = {str(r[0]): int(r[1]) for r in fit_rows}

    in_archive, net_new = _archive_split_counts(conn)
    enrich_total, enrich_contacts = _enrichment_with_contact_count(conn)

    src_rows = conn.execute(
        "SELECT source_name, COUNT(*) FROM lead_master GROUP BY source_name ORDER BY COUNT(*) DESC"
    ).fetchall()
    sources = {str(r[0]): int(r[1]) for r in src_rows}

    buyer_rows = conn.execute(
        """
        SELECT buyer_kind, COUNT(*) FROM lead_master
        WHERE buyer_kind IS NOT NULL AND length(trim(buyer_kind)) > 0
        GROUP BY buyer_kind ORDER BY COUNT(*) DESC LIMIT 12
        """
    ).fetchall()
    buyers = [(str(r[0]), int(r[1])) for r in buyer_rows]

    region_rows = conn.execute(
        """
        SELECT region, COUNT(*) FROM lead_master
        WHERE region IS NOT NULL AND length(trim(region)) > 0
        GROUP BY region ORDER BY COUNT(*) DESC LIMIT 12
        """
    ).fetchall()
    regions = [(str(r[0]), int(r[1])) for r in region_rows]

    top_orgs = conn.execute(
        f"""
        SELECT lm.id, lm.org_name, {_LM_FIT},
               COALESCE(lm.priority_score, 0), lm.buyer_kind,
               COALESCE(m.already_in_archive_flag, 0)
        FROM lead_master lm
        LEFT JOIN (
          SELECT m1.lead_id, m1.already_in_archive_flag
          FROM lead_matches_existing_orgs m1
          WHERE m1.id = (
            SELECT MIN(m2.id) FROM lead_matches_existing_orgs m2 WHERE m2.lead_id = m1.lead_id
          )
        ) m ON m.lead_id = lm.id
        ORDER BY COALESCE(lm.priority_score, 0) DESC, lm.last_seen_at DESC
        LIMIT 15
        """
    ).fetchall()

    annex_sql = f"""
    SELECT
      lm.id AS id_lead,
      lm.org_name AS organizacion,
      lm.priority_score,
      {_LM_FIT} AS fit_bucket,
      COALESCE(m.already_in_archive_flag, 0) AS already_in_archive_flag,
      lm.source_url,
      lm.evidence_summary,
      lm.buyer_kind,
      lm.region,
      lm.city,
      lm.contact_name,
      lm.email,
      lm.phone,
      lm.status,
      lm.next_action,
      m.matched_org_name
    FROM lead_master lm
    LEFT JOIN (
      SELECT m1.lead_id, m1.matched_org_name, m1.already_in_archive_flag
      FROM lead_matches_existing_orgs m1
      WHERE m1.id = (
        SELECT MIN(m2.id) FROM lead_matches_existing_orgs m2 WHERE m2.lead_id = m1.lead_id
      )
    ) m ON m.lead_id = lm.id
    ORDER BY
      CASE {_LM_FIT}
        WHEN 'high_fit' THEN 0 WHEN 'medium_fit' THEN 1 ELSE 2 END,
      COALESCE(m.already_in_archive_flag, 0) ASC,
      COALESCE(lm.priority_score, 0) DESC,
      lm.last_seen_at DESC
    LIMIT ?
    """
    annex_rows = conn.execute(annex_sql, (args.limit,)).fetchall()
    annex_cols = [
        "id_lead",
        "organizacion",
        "priority_score",
        "fit_bucket",
        "already_in_archive_flag",
        "source_url",
        "evidence_summary",
        "buyer_kind",
        "region",
        "city",
        "contact_name",
        "email",
        "phone",
        "status",
        "next_action",
        "matched_org_name",
    ]
    annex_path = out_dir / "anexo_leads.csv"
    with annex_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(annex_cols)
        w.writerows(annex_rows)
    conn.close()

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = {
        "generated_at_utc": generated_at,
        "sqlite_path_note": "Cifras calculadas sobre el inventario unificado de oportunidades de este análisis.",
        "totals": {
            "lead_master_rows": int(total_leads),
            "fit_bucket": fit_counts,
            "leads_matched_in_archive": in_archive,
            "leads_net_new_vs_archive": net_new,
            "enrichment_rows": enrich_total,
            "enrichment_rows_with_public_contact_fields": enrich_contacts,
        },
        "sources": sources,
        "top_buyer_kinds": [{"buyer_kind": b, "count": c} for b, c in buyers],
        "top_regions": [{"region": r, "count": c} for r, c in regions],
        "top_organizations_sample": [
            {
                "id_lead": tid,
                "organizacion": org,
                "fit_bucket": fb,
                "priority_score": float(ps) if ps is not None else None,
                "buyer_kind": bk,
                "already_in_archive_flag": int(arch),
            }
            for tid, org, fb, ps, bk, arch in top_orgs
        ],
        "anexo_csv_rows_written": len(annex_rows),
        "anexo_limit": args.limit,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- resumen_ejecutivo_es.md ---
    high_n = fit_counts.get("high_fit", 0)
    med_n = fit_counts.get("medium_fit", 0)
    low_n = fit_counts.get("low_fit", 0)
    src_lines = "\n".join(f"- **{k}:** {v} oportunidades consolidadas" for k, v in sorted(sources.items(), key=lambda x: -x[1]))
    if enrich_contacts < enrich_total:
        enrich_sentence = (
            f"Hay **{enrich_total}** oportunidades con seguimiento de enriquecimiento registrado; "
            f"en **{enrich_contacts}** de ellas ya constan datos de contacto público verificados en el sistema. "
            "El resto puede corresponder a trabajo en curso, validación pendiente o fuentes aún no consolidadas."
        )
    else:
        enrich_sentence = (
            f"Hay **{enrich_total}** oportunidades con seguimiento de enriquecimiento; "
            f"en **{enrich_contacts}** constan datos de contacto público verificados en el sistema."
        )
    md = f"""# Resumen ejecutivo — Oportunidades externas

**OrigenLab · Generado (UTC):** {generated_at}

## Objetivo del análisis

Priorizar oportunidades detectadas en **fuentes públicas** (licitaciones, laboratorios acreditados, centros de I+D, entre otras) y contrastarlas con el **historial comercial** ya acumulado, para orientar el esfuerzo de prospección con criterio y trazabilidad.

## Fuentes usadas

Integración de descargas y ficheros públicos (por ejemplo Mercado Público / ChileCompra, INN, CORFO), unificados en un solo inventario para este informe.

{src_lines if src_lines else "- (sin desglose por fuente disponible)"}

## Historial comercial frente a oportunidades nuevas

- **Historial comercial:** relación previa con organizaciones y contactos, reconstruida a partir del correo y documentación histórica; sirve de contexto y no sustituye el análisis de nuevas licitaciones u oportunidades.
- **Oportunidades de este informe:** iniciativas identificadas en fuentes externas; cuando hay **antecedente en historial comercial** (~{in_archive} casos), conviene cruzar con equipos que ya conocen la cuenta. El grueso del universo (**{net_new}**) se clasifica como **nuevas para prospección** a efectos de priorización comercial.

## Principales hallazgos

- **Oportunidades analizadas:** {total_leads}
- **Clasificación de ajuste (alto / medio / bajo):** {high_n} / {med_n} / {low_n}
- **Antecedente en historial comercial:** ~{in_archive} · **Nuevas para prospección:** ~{net_new}
- **Enriquecimiento de contactos:** {enrich_sentence}

## Dónde enfocar primero

Conviene revisar en detalle las oportunidades de **ajuste alto y medio** entre las **nuevas para prospección**, en el orden de prioridad que muestra el informe en pantalla. El **anexo** (`anexo_leads.csv`) complementa con el detalle tabular para equipos que requieran trabajar fila a fila.

## Limitaciones

- Las prioridades y etiquetas son **orientativas**; la decisión final comercial debe validarlas caso a caso.
- La vinculación con el historial depende de dominios y nombres de organización; puede haber desalineaciones puntuales.
- Los contactos públicos reflejan lo consolidado en el proceso de investigación; calidad y vigencia deben confirmarse antes de outreach.

## Próximos pasos recomendados

1. Revisar el informe HTML de esta carpeta y el resumen ejecutivo en `resumen_ejecutivo_es.md`.
2. Asignar ownership sobre el anexo para contacto y seguimiento; usar el identificador de cada fila como referencia estable entre equipos.
3. Tras actualizar el inventario o el enriquecimiento, **regenerar este paquete** para mantener alineación entre lo presentado al cliente y el trabajo operativo.

---
*Detalle tabular:* `anexo_leads.csv` · *Métricas estructuradas:* `summary.json`
"""
    (out_dir / "resumen_ejecutivo_es.md").write_text(md, encoding="utf-8")

    # --- index.html ---
    def esc(x: object) -> str:
        return html.escape("" if x is None else str(x), quote=True)

    buyer_lis = "".join(f"<li>{esc(b)}: <strong>{c}</strong></li>" for b, c in buyers[:8])
    region_lis = "".join(f"<li>{esc(r)}: <strong>{c}</strong></li>" for r, c in regions[:8])

    def _hist_si_no(arch: object) -> str:
        try:
            return "Sí" if int(arch or 0) == 1 else "No"
        except (TypeError, ValueError):
            return "No"

    if enrich_contacts < enrich_total:
        enrich_html = (
            f"<strong>{enrich_contacts}</strong> de <strong>{enrich_total}</strong> expedientes con enriquecimiento "
            "ya incluyen contacto público verificado; el resto puede estar en curso o pendiente de consolidar."
        )
    else:
        enrich_html = (
            f"<strong>{enrich_contacts}</strong> de <strong>{enrich_total}</strong> expedientes con contacto público verificado."
        )

    org_rows_html = "".join(
        "<tr>"
        f"<td>{esc(tid)}</td><td>{esc(org)}</td><td>{esc(fb)}</td>"
        f"<td>{esc(ps)}</td><td>{esc(bk)}</td><td>{esc(_hist_si_no(arch))}</td>"
        "</tr>"
        for tid, org, fb, ps, bk, arch in top_orgs
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>OrigenLab — Informe de oportunidades externas</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 52rem; color: #1a1a1a; line-height: 1.5; }}
    .brand {{ border-bottom: 1px solid #ccc; padding-bottom: 1rem; margin-bottom: 1.25rem; }}
    .brand-name {{ font-weight: 700; letter-spacing: 0.02em; font-size: 0.95rem; color: #333; }}
    h1 {{ font-size: 1.35rem; margin: 0.35rem 0 0.25rem 0; }}
    .subtitle {{ margin: 0; color: #444; font-size: 0.95rem; max-width: 40rem; }}
    h2 {{ font-size: 1.05rem; margin-top: 1.5rem; }}
    ul.cols {{ columns: 2; padding-left: 1.2rem; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; margin-top: 0.5rem; }}
    th, td {{ border: 1px solid #ddd; padding: 0.35rem 0.5rem; text-align: left; }}
    th {{ background: #f4f4f4; }}
    .muted {{ color: #555; font-size: 0.88rem; }}
    .box {{ background: #fafafa; padding: 0.75rem 1rem; border-radius: 6px; margin: 1rem 0; }}
  </style>
</head>
<body>
  <header class="brand">
    <div class="brand-name">OrigenLab</div>
    <h1>Informe de oportunidades externas</h1>
    <p class="subtitle">Oportunidades identificadas en fuentes públicas, contrastadas con el historial comercial acumulado.</p>
  </header>
  <p class="muted">Documento generado el {esc(generated_at)} (UTC). Los archivos de datos en esta carpeta complementan este informe.</p>

  <div class="box">
    <strong>Resumen cuantitativo</strong>
    <ul>
      <li>Oportunidades en inventario: <strong>{total_leads}</strong></li>
      <li>Clasificación de ajuste (alto / medio / bajo): <strong>{high_n}</strong> / <strong>{med_n}</strong> / <strong>{low_n}</strong></li>
      <li>Con <strong>antecedente en historial comercial</strong>: <strong>{in_archive}</strong> · <strong>Nuevas para prospección</strong>: <strong>{net_new}</strong></li>
      <li>Estado del enriquecimiento de contactos: {enrich_html}</li>
    </ul>
  </div>

  <h2>Tipos de comprador más frecuentes</h2>
  <ul class="cols">{buyer_lis or "<li>(sin datos)</li>"}</ul>

  <h2>Regiones más frecuentes</h2>
  <ul class="cols">{region_lis or "<li>(sin datos)</li>"}</ul>

  <h2>Muestra de organizaciones priorizadas</h2>
  <table>
    <thead><tr><th>ID</th><th>Organización</th><th>Ajuste</th><th>Prioridad (score)</th><th>Tipo de comprador</th><th>Antecedente en historial</th></tr></thead>
    <tbody>{org_rows_html or "<tr><td colspan='6'>Sin datos</td></tr>"}</tbody>
  </table>

  <h2>Próximos pasos</h2>
  <ol>
    <li>Leer el resumen ejecutivo en <code>resumen_ejecutivo_es.md</code> para contexto y matices.</li>
    <li>Usar <code>anexo_leads.csv</code> como soporte detallado; la columna de identificador permite alinear conversaciones internas.</li>
    <li>Actualizar el trabajo de prospección y enriquecimiento en operaciones, y volver a generar este paquete cuando cambie el inventario.</li>
  </ol>
</body>
</html>
"""
    (out_dir / "index.html").write_text(html_doc, encoding="utf-8")

    print(f"Wrote client pack to {out_dir}")
    print("  - index.html")
    print("  - resumen_ejecutivo_es.md")
    print("  - anexo_leads.csv")
    print("  - summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
