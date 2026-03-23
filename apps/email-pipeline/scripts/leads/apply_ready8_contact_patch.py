#!/usr/bin/env python3
"""Apply DR50 ready-8 contacts into leads_contact_hunt_current.csv (operational path).

Also writes:
  reports/out/active/leads_contact_hunt_current_ready8_patch.csv — the 8 full hunt rows after patch
  reports/out/active/leads_top20_for_client_report.csv
  docs/generated/READY8_AND_TOP20_REPORTING_PLAN.md

Does not touch legacy reference/*DEEPRESEARCH* files.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

REPO = _ROOT
HUNT = REPO / "reports/out/active/leads_contact_hunt_current.csv"
READY8 = REPO / "reports/out/active/leads_dr50_ready_candidates.csv"
NEEDS = REPO / "reports/out/active/leads_dr50_needs_research.csv"
PATCH_OUT = REPO / "reports/out/active/leads_contact_hunt_current_ready8_patch.csv"
TOP20_OUT = REPO / "reports/out/active/leads_top20_for_client_report.csv"
PLAN_MD = REPO / "docs/generated/READY8_AND_TOP20_REPORTING_PLAN.md"

READY_IDS = {608694, 622998, 608621, 617311, 619403, 608386, 609442, 610539}

NOTE = "Contacto público MP (DR50 ready8). Validar en ficha antes de outreach."
CONF = "alta"
ESTADO = "listo_dr50"


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        h = list(r.fieldnames or [])
        rows = [dict(row) for row in r]
    return h, rows


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _clear_contact_slots(row: dict[str, str]) -> None:
    keys = [
        "nombre_contacto_compras",
        "rol_contacto_compras",
        "email_publico_compras",
        "telefono_publico_compras",
        "nombre_contacto_tecnico",
        "rol_contacto_tecnico",
        "email_publico_tecnico",
        "telefono_publico_tecnico",
        "email_contacto_general",
        "telefono_contacto_general",
        "url_evidencia_compras",
        "url_evidencia_tecnico",
        "url_evidencia_general",
    ]
    for k in keys:
        if k in row:
            row[k] = ""


def apply_ready8_patch(row: dict[str, str], ready: dict[str, str]) -> None:
    """Mutate hunt row from one line of leads_dr50_ready_candidates.csv."""
    lid = int(ready["id_lead"])
    ev = (ready.get("evidence_url_dr") or "").strip()
    email = (ready.get("primary_contact_email") or "").strip()
    name = (ready.get("contact_name") or "").strip()
    role = (ready.get("contact_role") or "").strip()
    phone = (ready.get("contact_phone") or "").strip()

    _clear_contact_slots(row)

    if lid == 608694:
        row["nombre_contacto_tecnico"] = name
        row["rol_contacto_tecnico"] = role
        row["email_publico_tecnico"] = email
        row["url_evidencia_tecnico"] = ev
    elif lid == 608621:
        row["nombre_contacto_compras"] = ""
        row["rol_contacto_compras"] = "Buzón institucional de proveedores (UOH)"
        row["email_publico_compras"] = email
        row["url_evidencia_compras"] = ev
    else:
        row["nombre_contacto_compras"] = name
        row["rol_contacto_compras"] = role
        row["email_publico_compras"] = email
        if phone:
            row["telefono_publico_compras"] = phone
        row["url_evidencia_compras"] = ev

    row["confianza_contacto"] = CONF
    row["estado_seguimiento"] = ESTADO
    prev = (row.get("notas_manuales") or "").strip()
    if "DR50 ready8" not in prev:
        row["notas_manuales"] = f"{prev} | {NOTE}".strip(" |") if prev else NOTE


def sort_key_needs(r: dict[str, str]) -> tuple:
    try:
        pri = -float((r.get("priority_score") or "0").strip())
    except ValueError:
        pri = 0.0
    email = (r.get("primary_contact_email") or "").strip()
    has_em = -1 if email else 0
    alta = -1 if (r.get("dr_confidence") or "").strip().lower() == "alta" else 0
    return (pri, has_em, alta, int(r["id_lead"]))


def build_top20(
    hunt_by_id: dict[int, dict[str, str]],
    ready_rows: list[dict[str, str]],
    needs_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    needs_sorted = sorted(needs_rows, key=sort_key_needs)
    pick12 = needs_sorted[:12]
    out: list[dict[str, str]] = []
    order = 0

    for r in ready_rows:
        order += 1
        lid = int(r["id_lead"])
        h = hunt_by_id[lid]
        out.append(
            {
                "id_lead": str(lid),
                "org_name": h.get("organizacion_compradora", ""),
                "readiness_status": "ready_now",
                "fit_bucket": h.get("ajuste_fit", ""),
                "priority_score": h.get("puntaje_prioridad", ""),
                "buyer_kind": h.get("tipo_comprador", ""),
                "source_url": h.get("url_fuente", ""),
                "evidence_summary": h.get("resumen_evidencia", ""),
                "recommended_contact_route": r.get("recommended_contact_route", ""),
                "contact_name": r.get("contact_name", ""),
                "contact_role": r.get("contact_role", ""),
                "contact_email": r.get("primary_contact_email", ""),
                "contact_phone": r.get("contact_phone", ""),
                "contact_confidence": CONF,
                "report_section_order": str(order),
                "report_reason": "Cumple reglas conservadoras DR50 + evidencia MP DetailsAcquisition; volcado a hunt.",
            }
        )

    for r in pick12:
        order += 1
        lid = int(r["id_lead"])
        h = hunt_by_id[lid]
        ce = (r.get("primary_contact_email") or "").strip()
        cn = (r.get("contact_name") or "").strip()
        cr = (r.get("contact_role") or "").strip()
        cp = (r.get("contact_phone") or "").strip()
        cconf = "media" if ce else "baja"
        reason = (r.get("reconciliation_reason") or "").strip()
        out.append(
            {
                "id_lead": str(lid),
                "org_name": h.get("organizacion_compradora", ""),
                "readiness_status": "needs_validation",
                "fit_bucket": h.get("ajuste_fit", ""),
                "priority_score": h.get("puntaje_prioridad", ""),
                "buyer_kind": h.get("tipo_comprador", ""),
                "source_url": h.get("url_fuente", ""),
                "evidence_summary": h.get("resumen_evidencia", ""),
                "recommended_contact_route": r.get("recommended_contact_route", ""),
                "contact_name": cn,
                "contact_role": cr,
                "contact_email": ce,
                "contact_phone": cp,
                "contact_confidence": cconf,
                "report_section_order": str(order),
                "report_reason": reason[:500] if reason else "Alta prioridad o señal DR parcial; validar compras/técnico antes de cliente.",
            }
        )

    return out


def write_plan_md(
    ready_meta: list[tuple[int, str]],
    needs12: list[tuple[int, str, str]],
    audit_cmd: str,
    import_cmd: str,
    pack_cmd: str,
) -> None:
    body = f"""# Ready-8 hunt patch and top-20 reporting base

## Context

- **Operational hunt:** `reports/out/active/leads_contact_hunt_current.csv` was updated only for the **8** `id_lead` values in `leads_dr50_ready_candidates.csv` (current-cohort Deep Research, not legacy `reference/*DEEPRESEARCH*`).
- **Patch artifact:** `reports/out/active/leads_contact_hunt_current_ready8_patch.csv` contains those **8** rows **after** the patch (full hunt schema), for diff review.
- **Top 20 for reporting:** `reports/out/active/leads_top20_for_client_report.csv` = 8 ready + 12 next-best from `leads_dr50_needs_research.csv` (sort: `priority_score` desc, then filas con email DR, luego `dr_confidence=alta`).

## 1. Las 8 listas **ahora** (ready_now) y por qué

| `id_lead` | Por qué |
|-----------|---------|
"""
    for lid, why in ready_meta:
        body += f"| {lid} | {why} |\n"

    body += """
## 2. Las 12 siguientes (needs_validation)

Alta prioridad o pistas DR útiles, pero **no** pasan el umbral conservador de “listo” (sin email, baja DR, Gmail, buzón financiero, o solo central/derivación).

| `id_lead` | `priority_score` | Nota breve |
|-----------|------------------|------------|
"""
    for lid, pri, note in needs12:
        body += f"| {lid} | {pri} | {note} |\n"

    body += f"""
## 3. Orden sugerido para el informe al cliente

Usar `report_section_order` en `leads_top20_for_client_report.csv` (**1–20**): primero las **8** con `readiness_status=ready_now`, luego las **12** con `needs_validation` en el orden del CSV.

## 4. Redacción cliente: “listas para contacto”

Mostrar como **listas para contacto** (tras validación spot-check en Mercado Público) solo las filas con **`readiness_status=ready_now`** — hoy son los **8** IDs: **{", ".join(str(x[0]) for x in ready_meta)}**.

## 5. Redacción cliente: “priorizadas para validación comercial”

Las filas con **`readiness_status=needs_validation`**: prioridad/licitación fuerte o contacto parcial; el mensaje debe ser **pipeline / investigación en curso**, no “contacto verificado”.

## 6. Resultado esperado tras import + audit

Con la hoja `leads_contact_hunt_current.csv` ya parcheada y **reimportada** a SQLite, `audit_contact_readiness.py` debe listar **8** leads en `reports/out/active/leads_ready_to_contact.csv` (los mismos ocho `id_lead` que §4). `import_contact_hunt_to_sqlite.py --promote-procurement` promueve a `lead_master` las filas con **compras** rellena; el lead **608694** (solo técnico) suele quedar sin promoción de compras — es normal.

---

## Comandos para alinear SQLite y regenerar auditoría / cliente

```bash
{import_cmd}
{audit_cmd}
{pack_cmd}
```

- **Import:** vuelca la hoja hunt actualizada a `lead_outreach_enrichment` y opcionalmente promueve compras a `lead_master` (`--promote-procurement`).
- **Audit:** regenera `docs/generated/CONTACT_READINESS_AUDIT.md` y los tres CSV de readiness en `reports/out/active/`.
- **Client pack:** regenera `reports/out/client_pack_latest/`.

---
Generado por `scripts/leads/apply_ready8_contact_patch.py`.
"""
    PLAN_MD.write_text(body, encoding="utf-8")


def main() -> int:
    headers, hunt_rows = _read_csv(HUNT)
    _, ready_rows = _read_csv(READY8)
    _, needs_rows = _read_csv(NEEDS)

    ready_by_id = {int(r["id_lead"]): r for r in ready_rows}
    if set(ready_by_id) != READY_IDS:
        print("Ready8 CSV id set mismatch", file=sys.stderr)
        return 1

    patched_rows: list[dict[str, str]] = []
    for row in hunt_rows:
        lid_raw = (row.get("id_lead") or "").strip()
        if not lid_raw:
            continue
        lid = int(lid_raw)
        if lid in ready_by_id:
            apply_ready8_patch(row, ready_by_id[lid])
            patched_rows.append(dict(row))

    if len(patched_rows) != 8:
        print(f"Expected 8 patched rows, got {len(patched_rows)}", file=sys.stderr)
        return 1

    _write_csv(HUNT, headers, hunt_rows)
    _write_csv(PATCH_OUT, headers, patched_rows)

    hunt_by_id = {int(r["id_lead"]): r for r in hunt_rows}
    top20 = build_top20(hunt_by_id, ready_rows, needs_rows)
    top_fields = [
        "id_lead",
        "org_name",
        "readiness_status",
        "fit_bucket",
        "priority_score",
        "buyer_kind",
        "source_url",
        "evidence_summary",
        "recommended_contact_route",
        "contact_name",
        "contact_role",
        "contact_email",
        "contact_phone",
        "contact_confidence",
        "report_section_order",
        "report_reason",
    ]
    _write_csv(TOP20_OUT, top_fields, top20)

    ready_meta = [
        (
            int(r["id_lead"]),
            (ready_by_id[int(r["id_lead"])].get("reconciliation_reason") or "").strip(),
        )
        for r in ready_rows
    ]
    needs_sorted = sorted(needs_rows, key=sort_key_needs)[:12]
    needs12 = []
    for r in needs_sorted:
        lid = int(r["id_lead"])
        needs12.append(
            (
                lid,
                r.get("priority_score", ""),
                (r.get("reconciliation_reason") or "")[:200],
            )
        )

    import_cmd = (
        "uv run python scripts/leads/import_contact_hunt_to_sqlite.py \\\n"
        "  --csv reports/out/active/leads_contact_hunt_current.csv \\\n"
        "  --promote-procurement"
    )
    audit_cmd = "uv run python scripts/leads/audit_contact_readiness.py"
    pack_cmd = "uv run python scripts/reports/build_leads_client_pack.py"

    write_plan_md(ready_meta, needs12, audit_cmd, import_cmd, pack_cmd)

    print(f"Updated {HUNT}")
    print(f"Wrote {PATCH_OUT}")
    print(f"Wrote {TOP20_OUT}")
    print(f"Wrote {PLAN_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
