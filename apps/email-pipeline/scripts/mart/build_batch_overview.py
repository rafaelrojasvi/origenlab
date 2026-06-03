#!/usr/bin/env python3
"""
Generate a single overview.html in the batch folder: what ran, key numbers, links to all outputs.

HDBSCAN numbers in `ml_explore.json` require `uv sync --group ml` when running `email_ml_explore.py`.

  uv run python scripts/mart/build_batch_overview.py --batch /path/to/run_NAME

Usually called at the end of run_all.sh so you have one page showing everything.
"""
from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Build overview.html in batch folder")
    ap.add_argument("--batch", type=Path, required=True, help="Batch folder (e.g. .../run_NAME)")
    args = ap.parse_args()

    batch = args.batch.resolve()
    if not batch.is_dir():
        raise SystemExit(f"Not a directory: {batch}")

    report_dir = batch / "client_report"
    summary_path = report_dir / "summary.json"
    ml_path = batch / "ml_explore.json"

    summary: dict | None = None
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            summary = None

    ml: dict | None = None
    if ml_path.is_file():
        try:
            ml = json.loads(ml_path.read_text(encoding="utf-8"))
        except Exception:
            ml = None

    has_index = (report_dir / "index.html").is_file()
    has_clusters = (report_dir / "clusters.json").is_file()
    has_no_bounce = (report_dir / "clusters_no_bounce.json").is_file()
    has_cotiz = (report_dir / "clusters_cotiz.json").is_file()
    has_embeddings = bool(summary and summary.get("embeddings_note"))
    has_cluster_summary = bool(summary and (summary.get("cluster_summary") or []))

    # Key numbers
    total_msgs = summary.get("totals", {}).get("total") if summary else None
    with_body = summary.get("totals", {}).get("with_body") if summary else None
    bounce = summary.get("totals", {}).get("bounce_like") if summary else None
    gen_at = summary.get("generated_at") if summary else None
    run_id = summary.get("run_id") if summary else batch.name

    kmeans_k = ml.get("kmeans_k") if ml else None
    agg_k = ml.get("agglomerative_k") if ml else None
    ml_sample = ml.get("n_sample") if ml else None
    hdb = ml.get("hdbscan") if ml else None
    hdb_clusters = hdb.get("clusters") if isinstance(hdb, dict) and "clusters" in hdb else None
    hdb_noise = hdb.get("noise_points") if isinstance(hdb, dict) and "noise_points" in hdb else None
    hdb_skipped = hdb.get("skipped") if isinstance(hdb, dict) else None
    equipment_count = len(ml.get("equipment_model_mentions") or []) if ml else None

    # Build HTML
    def row(what: str, done: bool) -> str:
        status = "✓" if done else "—"
        cls = "done" if done else "skip"
        return f"<tr class=\"{cls}\"><td>{escape(what)}</td><td>{status}</td></tr>"

    checklist = [
        ("Client report (SQL + dominios)", has_index),
        ("Embeddings + cluster table in report", has_embeddings or has_cluster_summary),
        ("clusters.json (embedding clusters)", has_clusters),
        ("clusters_no_bounce.json", has_no_bounce),
        ("clusters_cotiz.json", has_cotiz),
        ("ml_explore.json (KMeans + Agglomerative + equipment regex)", ml_path.is_file()),
        ("HDBSCAN in ml_explore", hdb_clusters is not None),
    ]
    checklist_html = "".join(row(w, d) for w, d in checklist)

    nums = []
    if total_msgs is not None:
        nums.append(f"<span>Total mensajes: <strong>{total_msgs:,}</strong></span>")
    if with_body is not None:
        nums.append(f"<span>Con cuerpo: <strong>{with_body:,}</strong></span>")
    if bounce is not None:
        nums.append(f"<span>Estilo rebote/NDR (heur.): <strong>{bounce:,}</strong></span>")
    if ml_sample is not None:
        nums.append(f"<span>ML sample: <strong>{ml_sample:,}</strong></span>")
    if kmeans_k is not None:
        nums.append(f"<span>KMeans k: <strong>{kmeans_k}</strong></span>")
    if agg_k is not None:
        nums.append(f"<span>Agglomerative k: <strong>{agg_k}</strong></span>")
    if hdb_clusters is not None and hdb_noise is not None:
        nums.append(f"<span>HDBSCAN: <strong>{hdb_clusters} clusters</strong>, <strong>{hdb_noise:,} noise</strong></span>")
    elif hdb_skipped:
        nums.append(f"<span>HDBSCAN: <em>skipped</em> ({escape(str(hdb_skipped))})</span>")
    if equipment_count is not None:
        nums.append(f"<span>Equipment mentions (regex): <strong>{equipment_count}</strong></span>")
    kpi_html = "<div class=\"kpi\">" + "".join(nums) + "</div>" if nums else ""

    links = [
        ("client_report/index.html", "Informe principal (gráficos, tablas, clusters)"),
        ("ml_report.html", "ML con gráficos (KMeans, equipos, HDBSCAN)"),
        ("client_report/summary.json", "Todos los números del informe (JSON)"),
        ("client_report/clusters.json", "Clusters por embedding (si se generó)"),
        ("client_report/clusters_no_bounce.json", "Clusters muestra no_bounce"),
        ("client_report/clusters_cotiz.json", "Clusters muestra cotiz"),
        ("ml_explore.json", "KMeans, Agglomerative, HDBSCAN, menciones de equipos (JSON)"),
    ]
    link_rows = []
    for path, desc in links:
        full = batch / path
        if full.is_file():
            link_rows.append(f"<tr><td><a href=\"{escape(path)}\">{escape(path)}</a></td><td>{escape(desc)}</td></tr>")
        else:
            link_rows.append(f"<tr class=\"skip\"><td>{escape(path)}</td><td>{escape(desc)} (no generado)</td></tr>")
    links_html = "".join(link_rows)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>OrigenLab — Resumen del run</title>
  <style>
    :root {{
      --bg: #0f1419;
      --card: #1a2332;
      --text: #e7ecf3;
      --muted: #8b9cb3;
      --accent: #3d9cf0;
      --green: #3dd68c;
    }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 1.5rem 2rem 4rem; line-height: 1.5; }}
    h1 {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 0.25rem; }}
    .sub {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }}
    section {{ margin-bottom: 2.5rem; }}
    h2 {{ font-size: 1.1rem; color: var(--accent); border-bottom: 1px solid #2a3544; padding-bottom: 0.5rem; }}
    .card {{ background: var(--card); border-radius: 10px; padding: 1rem 1.25rem; border: 1px solid #2a3544; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th, td {{ text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid #2a3544; }}
    th {{ color: var(--muted); font-weight: 600; }}
    tr.done td {{ color: var(--green); }}
    tr.skip td {{ color: var(--muted); }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .kpi {{ display: flex; flex-wrap: wrap; gap: 1rem; margin: 1rem 0; }}
    .kpi span {{ background: var(--card); padding: 0.6rem 1rem; border-radius: 8px; border: 1px solid #2a3544; }}
    .kpi strong {{ color: var(--green); }}
  </style>
</head>
<body>
  <h1>OrigenLab — Resumen del run</h1>
  <p class="sub">Carpeta: <strong>{escape(run_id)}</strong>{f' · Generado: {escape(gen_at)}' if gen_at else ''}</p>

  <section class="card">
    <h2>Qué se ejecutó</h2>
    <table>
      <thead><tr><th>Componente</th><th>Estado</th></tr></thead>
      <tbody>{checklist_html}</tbody>
    </table>
  </section>

  <section class="card">
    <h2>Números principales</h2>
    {kpi_html}
  </section>

  <section class="card">
    <h2>Enlaces a todos los resultados</h2>
    <table>
      <thead><tr><th>Archivo</th><th>Contenido</th></tr></thead>
      <tbody>{links_html}</tbody>
    </table>
  </section>

  <p class="sub">Documentación: <code>docs/reporting/OUTPUTS_OVERVIEW.md</code> — mapa de scripts, salidas y qué es cada cosa.</p>
</body>
</html>
"""

    out = batch / "overview.html"
    out.write_text(html, encoding="utf-8")
    print("Wrote:", out)


if __name__ == "__main__":
    main()
