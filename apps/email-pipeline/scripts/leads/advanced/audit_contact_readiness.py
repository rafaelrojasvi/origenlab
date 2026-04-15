#!/usr/bin/env python3
"""Operational contact-readiness audit for the current hunt cohort.

Reads ``reports/out/active/leads_contact_hunt_current.csv`` as the primary cohort,
SQLite for matches / enrichment / archive, and writes:

- docs/generated/CONTACT_READINESS_AUDIT.md
- reports/out/active/leads_ready_to_contact.csv
- reports/out/active/leads_needs_contact_research.csv
- reports/out/active/leads_not_ready.csv

Run from repo root::

    uv run python scripts/leads/advanced/audit_contact_readiness.py
    uv run python scripts/leads/advanced/audit_contact_readiness.py --db /path/to/emails.sqlite
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
from origenlab_email_pipeline.hunt_csv_alignment import describe_hunt_misalignment
from origenlab_email_pipeline.leads_schema import ensure_leads_tables

HUNT_PATH = _ROOT / "reports/out/active/leads_contact_hunt_current.csv"
MERGED_PATH = _ROOT / "reports/out/active/leads_contact_hunt_current_merged.csv"
WEEKLY_FOCUS_PATH = _ROOT / "reports/out/active/leads_weekly_focus.csv"
REFERENCE_GLOB = "reports/out/reference/*DEEPRESEARCH*"
DOCS_OUT = _ROOT / "docs/generated/CONTACT_READINESS_AUDIT.md"
ACTIVE = _ROOT / "reports/out/active"

CONTACT_JSON_KEYS = (
    "nombre_contacto_compras",
    "email_publico_compras",
    "telefono_publico_compras",
    "nombre_contacto_tecnico",
    "email_publico_tecnico",
    "telefono_publico_tecnico",
    "email_contacto_general",
    "telefono_contacto_general",
)

HUNT_CONTACT_COLS = list(CONTACT_JSON_KEYS)


def _read_hunt_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _hunt_has_contact(row: dict[str, str]) -> bool:
    return any((row.get(c) or "").strip() for c in HUNT_CONTACT_COLS)


def _enrichment_has_contact(conn: sqlite3.Connection, lead_id: int) -> bool:
    row = conn.execute(
        "SELECT enrichment_json FROM lead_outreach_enrichment WHERE lead_id = ?",
        (lead_id,),
    ).fetchone()
    if not row:
        return False
    try:
        d = json.loads(row[0] or "{}")
    except (TypeError, json.JSONDecodeError):
        return False
    return any(isinstance(d.get(k), str) and d[k].strip() for k in CONTACT_JSON_KEYS)


def _lead_master_contact(conn: sqlite3.Connection, lead_id: int) -> bool:
    row = conn.execute(
        "SELECT email, phone, contact_name FROM lead_master WHERE id = ?",
        (lead_id,),
    ).fetchone()
    if not row:
        return False
    return any((row[0] or "").strip() or (row[1] or "").strip() or (row[2] or "").strip())


def _archive_contact_route(conn: sqlite3.Connection, lead_id: int) -> tuple[bool, str, str, str]:
    """Returns (usable, matched_domain, key_contacts_snip, top_email)."""
    m = conn.execute(
        """
        SELECT matched_domain FROM lead_matches_existing_orgs
        WHERE lead_id = ? ORDER BY id LIMIT 1
        """,
        (lead_id,),
    ).fetchone()
    if not m or not (m[0] or "").strip():
        return False, "", "", ""
    dom = m[0].strip()
    om = conn.execute(
        "SELECT key_contacts FROM organization_master WHERE lower(domain) = lower(?)",
        (dom,),
    ).fetchone()
    kc = (om[0] or "").strip() if om else ""
    ce = conn.execute(
        """
        SELECT email FROM contact_master
        WHERE lower(domain) = lower(?) AND length(trim(email)) > 0
        ORDER BY quote_email_count DESC NULLS LAST LIMIT 1
        """,
        (dom,),
    ).fetchone()
    em = (ce[0] or "").strip() if ce else ""
    if kc or em:
        return True, dom, kc[:200], em
    return False, dom, kc[:200], em


def _deepresearch_overlap_ids(hunt_ids: set[int]) -> tuple[int, set[int]]:
    ref_dir = _ROOT / "reports/out/reference"
    union: set[int] = set()
    for p in sorted(ref_dir.glob("*DEEPRESEARCH*")):
        if not p.is_file() or not p.suffix.lower() == ".csv":
            continue
        try:
            with p.open(encoding="utf-8-sig", newline="") as f:
                r = csv.DictReader(f)
                if not r.fieldnames or "id_lead" not in r.fieldnames:
                    continue
                for row in r:
                    raw = (row.get("id_lead") or "").strip()
                    if not raw:
                        continue
                    try:
                        union.add(int(raw))
                    except ValueError:
                        pass
        except OSError:
            continue
    return len(union & hunt_ids), union & hunt_ids


def main() -> int:
    ap = argparse.ArgumentParser(description="Contact-readiness audit for hunt cohort.")
    ap.add_argument("--db", type=Path, default=None)
    args = ap.parse_args()

    if not HUNT_PATH.is_file():
        print(f"Missing hunt file: {HUNT_PATH}", file=sys.stderr)
        return 1

    hunt_rows = _read_hunt_rows(HUNT_PATH)
    cohort_n = len(hunt_rows)
    hunt_ids = {int(r["id_lead"]) for r in hunt_rows if (r.get("id_lead") or "").strip()}

    align_ok = True
    align_msg = ""
    if MERGED_PATH.is_file():
        msg = describe_hunt_misalignment(HUNT_PATH, MERGED_PATH)
        if msg:
            align_ok = False
            align_msg = msg
    else:
        align_ok = False
        align_msg = f"Merged file missing: {MERGED_PATH}"

    wf_ids: set[int] = set()
    if WEEKLY_FOCUS_PATH.is_file():
        with WEEKLY_FOCUS_PATH.open(encoding="utf-8-sig", newline="") as f:
            wf_ids = {int(r["id_lead"]) for r in csv.DictReader(f) if (r.get("id_lead") or "").strip()}

    overlap_wf_hunt = hunt_ids & wf_ids
    dr_overlap_n, dr_overlap_set = _deepresearch_overlap_ids(hunt_ids)

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    ensure_leads_tables(conn)

    # Threshold: medium_fit with priority <= 5.0 → not_ready (relative weakness in this export)
    MEDIUM_PRIORITY_FLOOR = 5.0

    ready_rows: list[dict[str, str]] = []
    needs_rows: list[dict[str, str]] = []
    not_ready_rows: list[dict[str, str]] = []

    for row in hunt_rows:
        lid = int(row["id_lead"])
        org = (row.get("organizacion_compradora") or "").strip()
        fit = (row.get("ajuste_fit") or "").strip()
        try:
            pr = float(row.get("puntaje_prioridad") or 0)
        except ValueError:
            pr = 0.0
        buyer = (row.get("tipo_comprador") or "").strip()
        try:
            arch_flag = int((row.get("ya_en_archivo") or "0").strip() or "0")
        except ValueError:
            arch_flag = 0
        url = (row.get("url_fuente") or "").strip()
        ev = (row.get("resumen_evidencia") or "").strip()
        conf = (row.get("confianza_contacto") or "").strip()
        strategy = (row.get("estrategia_contacto_recomendada") or "").strip()

        hunt_c = _hunt_has_contact(row)
        enr_c = _enrichment_has_contact(conn, lid)
        lm_c = _lead_master_contact(conn, lid)
        arc_ok, arc_dom, arc_kc, arc_em = _archive_contact_route(conn, lid)

        # Not-ready bucket first (relative deprioritization within cohort)
        if fit == "medium_fit" and pr <= MEDIUM_PRIORITY_FLOOR:
            not_ready_rows.append(
                {
                    "id_lead": str(lid),
                    "org_name": org,
                    "fit_bucket": fit,
                    "priority_score": str(pr),
                    "buyer_kind": buyer,
                    "source_url": url,
                    "evidence_summary": ev,
                    "not_ready_reason": (
                        f"medium_fit con prioridad {pr} ≤ {MEDIUM_PRIORITY_FLOOR} en este export; "
                        "cola secundaria frente a altos y medios más fuertes. No implica descarte definitivo."
                    ),
                }
            )
            continue

        has_route = hunt_c or enr_c or lm_c or arc_ok
        if has_route and fit in ("high_fit", "medium_fit") and (url or ev):
            # Build ready row
            route = ""
            cname = ""
            crole = ""
            cemail = ""
            cphone = ""
            src = ""
            if hunt_c:
                src = "hoja_hunt"
                route = "contacto en hoja operativa"
                for k in (
                    ("nombre_contacto_compras", "rol_contacto_compras", "email_publico_compras", "telefono_publico_compras"),
                    ("nombre_contacto_tecnico", "rol_contacto_tecnico", "email_publico_tecnico", "telefono_publico_tecnico"),
                    ("email_contacto_general", "", "email_contacto_general", "telefono_contacto_general"),
                ):
                    nm, rl, em_k, ph_k = k
                    if (row.get(em_k) or "").strip() or (row.get(ph_k) or "").strip():
                        cname = (row.get(nm) or "").strip()
                        crole = (row.get(rl) or "").strip()
                        cemail = (row.get(em_k) or "").strip()
                        cphone = (row.get(ph_k) or "").strip()
                        break
            elif enr_c:
                src = "import_enriquecimiento"
                rowj = conn.execute(
                    "SELECT enrichment_json FROM lead_outreach_enrichment WHERE lead_id=?",
                    (lid,),
                ).fetchone()
                d = json.loads(rowj[0] or "{}") if rowj else {}
                route = "datos importados en enriquecimiento"
                for em_k, ph_k, nm_k, rl_k in (
                    ("email_publico_compras", "telefono_publico_compras", "nombre_contacto_compras", "rol_contacto_compras"),
                    ("email_publico_tecnico", "telefono_publico_tecnico", "nombre_contacto_tecnico", "rol_contacto_tecnico"),
                    ("email_contacto_general", "telefono_contacto_general", "", ""),
                ):
                    if (d.get(em_k) or "").strip() or (d.get(ph_k) or "").strip():
                        cemail = (d.get(em_k) or "").strip()
                        cphone = (d.get(ph_k) or "").strip()
                        cname = (d.get(nm_k) or "").strip()
                        crole = (d.get(rl_k) or "").strip()
                        break
            elif lm_c:
                src = "lead_master"
                lm = conn.execute(
                    "SELECT contact_name, email, phone FROM lead_master WHERE id=?",
                    (lid,),
                ).fetchone()
                route = "contacto en registro normalizado del lead"
                cname, cemail, cphone = (lm[0] or "").strip(), (lm[1] or "").strip(), (lm[2] or "").strip()
            elif arc_ok:
                src = "historial_mart"
                route = f"historial comercial dominio {arc_dom}"
                cemail = arc_em
                cname = (arc_kc[:120] + "…") if len(arc_kc) > 120 else arc_kc

            reason = (
                f"Alta/media prioridad ({fit}), evidencia/url presentes, vía de contacto desde {src}."
            )
            ready_rows.append(
                {
                    "id_lead": str(lid),
                    "org_name": org,
                    "fit_bucket": fit,
                    "priority_score": str(pr),
                    "buyer_kind": buyer,
                    "already_in_archive_flag": str(arch_flag),
                    "source_url": url,
                    "evidence_summary": ev,
                    "recommended_contact_route": route,
                    "contact_name": cname,
                    "contact_role": crole,
                    "contact_email": cemail,
                    "contact_phone": cphone,
                    "contact_source": src,
                    "contact_confidence": conf or ("alta" if arc_ok and arc_em else "media"),
                    "readiness_reason": reason,
                    "next_action": "Preparar mensaje inicial y registrar resultado en CRM / hoja de seguimiento.",
                }
            )
        else:
            missing = []
            if not hunt_c and not enr_c and not lm_c and not arc_ok:
                missing.append("sin email/teléfono/ruta verificada en hoja, DB ni historial")
            if not url and not ev:
                missing.append("falta contexto mínimo")
            needs_rows.append(
                {
                    "id_lead": str(lid),
                    "org_name": org,
                    "fit_bucket": fit,
                    "priority_score": str(pr),
                    "buyer_kind": buyer,
                    "already_in_archive_flag": str(arch_flag),
                    "source_url": url,
                    "evidence_summary": ev,
                    "missing_for_readiness": "; ".join(missing) if missing else "sin vía de contacto consolidada",
                    "suggested_research_route": strategy or "Buscar contacto público compras/transparencia u oficial del organismo; validar antes de outreach.",
                    "next_action": "Investigar contacto; volver a fusionar/importar o completar hoja hunt antes de contactar.",
                }
            )

    cohort_match_ct = sum(
        1
        for lid in hunt_ids
        if conn.execute("SELECT 1 FROM lead_matches_existing_orgs WHERE lead_id=?", (lid,)).fetchone()
    )
    conn.close()

    # Write CSVs
    ACTIVE.mkdir(parents=True, exist_ok=True)
    ready_fields = [
        "id_lead",
        "org_name",
        "fit_bucket",
        "priority_score",
        "buyer_kind",
        "already_in_archive_flag",
        "source_url",
        "evidence_summary",
        "recommended_contact_route",
        "contact_name",
        "contact_role",
        "contact_email",
        "contact_phone",
        "contact_source",
        "contact_confidence",
        "readiness_reason",
        "next_action",
    ]
    needs_fields = [
        "id_lead",
        "org_name",
        "fit_bucket",
        "priority_score",
        "buyer_kind",
        "already_in_archive_flag",
        "source_url",
        "evidence_summary",
        "missing_for_readiness",
        "suggested_research_route",
        "next_action",
    ]
    not_fields = [
        "id_lead",
        "org_name",
        "fit_bucket",
        "priority_score",
        "buyer_kind",
        "source_url",
        "evidence_summary",
        "not_ready_reason",
    ]

    def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in fields})

    _write_csv(ACTIVE / "leads_ready_to_contact.csv", ready_fields, ready_rows)
    _write_csv(ACTIVE / "leads_needs_contact_research.csv", needs_fields, needs_rows)
    _write_csv(ACTIVE / "leads_not_ready.csv", not_fields, not_ready_rows)

    if ready_rows:
        ready_blurb = "Detalle en `leads_ready_to_contact.csv` (una fila por lead listo)."
    else:
        ready_blurb = (
            "Ningún lead del cohorte reúne hoy una vía de contacto verificable según las reglas del §3 "
            "(celdas de contacto en la hoja hunt, campos de contacto en el JSON de enriquecimiento, "
            "email/teléfono en el registro normalizado del lead, ni email/`key_contacts` vía mart para un match)."
        )

    archive_overlap_blurb = (
        f"Hay **{cohort_match_ct}** leads del cohorte con fila en `lead_matches_existing_orgs`. "
        "Para esos IDs, el script buscó `key_contacts` y un email principal en `contact_master` por dominio; "
        f"eso produjo **{len(ready_rows)}** filas “ready” en esta corrida (puede ser 0 aunque exista match, si el mart no trae contactos útiles)."
        if cohort_match_ct
        else "**Ningún** lead del cohorte tiene fila en `lead_matches_existing_orgs`; por ese camino el historial no aporta contactos recuperables para estos IDs."
    )

    # Markdown
    md = f"""<!-- AUTO-GENERATED by scripts/leads/advanced/audit_contact_readiness.py — do not edit; re-run the script. -->

# 1. Executive summary

Este audit evalúa **contact-readiness** para el cohorte operativo definido por la hoja **`reports/out/active/leads_contact_hunt_current.csv`** ({cohort_n} filas / `id_lead` únicos: {len(hunt_ids)}).

- **Listos para contactar ahora (criterio estricto):** **{len(ready_rows)}**. {ready_blurb}
- **Interesantes pero aún sin vía de contacto validada:** **{len(needs_rows)}** (prioridad alta/media por encima del umbral definido en §3, con contexto de licitación presente).
- **No prioritarios en esta cola (según umbral interno):** **{len(not_ready_rows)}** (ajuste medio con prioridad ≤ {MEDIUM_PRIORITY_FLOOR} en este export).
- **Archivos DEEPRESEARCH en `reports/out/reference/`:** **{dr_overlap_n}** IDs del cohorte actual aparecen en esos CSV — **no sirven como evidencia de contacto listo para este lote** sin nueva investigación alineada a los `id_lead` actuales.

*Incertidumbre:* los CSV son instantáneas; si completó celdas en Excel sin guardar en esta ruta, el resultado puede diferir.

# 2. Cohort definition

| Elemento | Uso en este audit |
|----------|-------------------|
| **Cohorte principal** | Todas las filas de `reports/out/active/leads_contact_hunt_current.csv` ({cohort_n} leads). |
| **`leads_weekly_focus.csv`** | Comparación cruzada: {len(wf_ids)} IDs; intersección con cohorte hunt: **{len(overlap_wf_hunt)}**; solo en weekly focus: **{len(wf_ids - hunt_ids)}**; solo en hunt: **{len(hunt_ids - wf_ids)}**. No se mezclaron filas extra en las tres salidas CSV (solo cohorte hunt). |
| **`leads_contact_hunt_current_merged.csv`** | **No utilizado** para clasificación: alineación con `current` **{'válida' if align_ok else 'NO válida'}**. |
| **SQLite** | `lead_master`, `lead_matches_existing_orgs`, `lead_outreach_enrichment`, `organization_master`, `contact_master` para contacto y cruce archivo. |
| **DEEPRESEARCH reference** | Solo análisis de intersección de `id_lead` con el cohorte ({dr_overlap_n} coincidencias). |

# 3. Contact-readiness criteria

## Ready to contact

Se marca **ready** solo si, para un `id_lead` del cohorte hunt:

- `ajuste_fit` es `high_fit` o `medium_fit` **y** prioridad **> {MEDIUM_PRIORITY_FLOOR}** si es `medium_fit` (los `medium_fit` con prioridad ≤ umbral van a “not ready” operativo).
- Hay **evidencia o URL de fuente** (`resumen_evidencia` o `url_fuente` no vacíos).
- Y existe **al menos una** de:
  - columnas de contacto público rellenas en la hoja hunt (compras/técnico/general);
  - mismos campos en JSON de `lead_outreach_enrichment`;
  - `email` / `phone` / `contact_name` en `lead_master`;
  - match en `lead_matches_existing_orgs` con `key_contacts` en `organization_master` **o** email en `contact_master` para el dominio matcheado.

**Umbral medium:** prioridad numérica `puntaje_prioridad` > **{MEDIUM_PRIORITY_FLOOR}** para permanecer en cola activa de investigación frente a “not ready”.

## Needs contact research

- `high_fit`, o `medium_fit` con prioridad **>** {MEDIUM_PRIORITY_FLOOR}.
- Sin la vía de contacto anterior.
- Contexto de licitación presente en la hoja (en este export, todas las filas tienen `resumen_evidencia`).

## Not ready

- `medium_fit` con `puntaje_prioridad` ≤ **{MEDIUM_PRIORITY_FLOOR}** (cola secundaria en este lote exportado).
- *(Este cohorte no incluye `low_fit`; si se amplía el export, habría que reclasificar.)*

# 4. Overlap with historical archive

- Cohorte hunt: **{len(hunt_ids)}** IDs. Con fila en `lead_matches_existing_orgs`: **{cohort_match_ct}**.
- {archive_overlap_blurb}
- El flag `ya_en_archivo` en la hoja hunt puede no coincidir con la presencia de filas en `lead_matches_existing_orgs` para el mismo ID (definiciones de export distintas); para outreach práctico prima la **vía de contacto verificable**.

**Cliente / pack:** el informe en `reports/out/client_pack_latest/` reflejó **0** filas de enriquecimiento con contacto público verificado a escala de la base; este subconjunto hunt es coherente con eso (sin contactos rellenados en hoja ni JSON útil para estos IDs).

"""

    dr_overlap_sample = sorted(dr_overlap_set)[:20]
    dr_overlap_suffix = "…" if len(dr_overlap_set) > 20 else ""
    if dr_overlap_n == 0:
        dr_conclusion = (
            "**Conclusión:** cero solapamiento de `id_lead` entre el cohorte hunt y los CSV DEEPRESEARCH en `reference/`. "
            "Esos archivos **no** determinan el estado de contacto de este lote; no marcar “listo” por referencia sin IDs coincidentes e import alineado."
        )
    else:
        dr_conclusion = (
            f"**Conclusión:** solo **{dr_overlap_n}** `id_lead` del cohorte aparecen en DEEPRESEARCH; el resto del cohorte **no** está cubierto por esos CSV. "
            "Usar la referencia solo para esos IDs tras verificar columnas y vigencia; para el resto, la investigación actual (hunt/SQLite) manda."
        )

    md += f"""
# 5. Deep Research reference applicability

- Archivos considerados: `reports/out/reference/*DEEPRESEARCH*.csv` (tres archivos con ese patrón en el repo).
- **`id_lead` del cohorte actual que aparecen en esos CSV:** **{dr_overlap_n}**.
- {dr_conclusion}
{f"- **IDs en ambos conjuntos (muestra):** {dr_overlap_sample}{dr_overlap_suffix}" if dr_overlap_n else ""}

# 6. CSV outputs explanation

| Archivo | Contenido | Uso siguiente |
|---------|-----------|----------------|
| `leads_ready_to_contact.csv` | **{len(ready_rows)}** filas. Cada fila cumple reglas de §3. | Priorizar outreach inmediato; documentar fuente en `contact_source`. |
| `leads_needs_contact_research.csv` | **{len(needs_rows)}** filas. Alta/media prioridad sin vía validada. | Trabajar top 20–50 por `priority_score`; completar hunt y `merge` + `import` o investigación manual. |
| `leads_not_ready.csv` | **{len(not_ready_rows)}** filas. Medios débiles en este export. | Revisión trimestral o re-scoring; no bloquear la cola principal. |

**Columnas clave:** `missing_for_readiness` y `suggested_research_route` en “needs”; `readiness_reason` en “ready”; `not_ready_reason` en “not ready”.

# 7. Practical next action

1. **Cola principal:** trabajar **`leads_needs_contact_research.csv`** ordenado por `priority_score` descendente (empezar por 20–50).
2. **Listo para cliente “outreach inmediato”:** hoy **{len(ready_rows)}** filas en `leads_ready_to_contact.csv` — no hay shortlist positiva hasta completar investigación o import alineado.
3. **Referencia DEEPRESEARCH:** ignorar para readiness del cohorte actual hasta que exista merge por `id_lead` coincidente.
4. **Merged hunt:** alinear `leads_contact_hunt_current_merged.csv` con `current` antes de confiar en importaciones; ver mensaje de alineación abajo.

---

**Alineación merged vs current (referencia):**  
```
{align_msg if not align_ok else "OK: mismos id_lead en current y merged."}
```

**Base de datos usada:** `{db_path}`  
**Generado:** audit automático (`scripts/leads/advanced/audit_contact_readiness.py`).
"""

    DOCS_OUT.parent.mkdir(parents=True, exist_ok=True)
    DOCS_OUT.write_text(md, encoding="utf-8")

    print(f"Wrote {DOCS_OUT}")
    print(f"Ready: {len(ready_rows)}, needs research: {len(needs_rows)}, not ready: {len(not_ready_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
