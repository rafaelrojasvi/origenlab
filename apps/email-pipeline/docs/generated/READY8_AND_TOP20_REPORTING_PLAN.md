# Ready-8 hunt patch and top-20 reporting base

## Context

- **Operational hunt:** `reports/out/active/leads_contact_hunt_current.csv` was updated only for the **8** `id_lead` values in `leads_dr50_ready_candidates.csv` (current-cohort Deep Research, not legacy `reference/*DEEPRESEARCH*`).
- **Patch artifact:** `reports/out/active/leads_contact_hunt_current_ready8_patch.csv` contains those **8** rows **after** the patch (full hunt schema), for diff review.
- **Top 20 for reporting:** `reports/out/active/leads_top20_for_client_report.csv` = 8 ready + 12 next-best from `leads_dr50_needs_research.csv` (sort: `priority_score` desc, then filas con email DR, luego `dr_confidence=alta`).

## 1. Las 8 listas **ahora** (ready_now) y por qué

| `id_lead` | Por qué |
|-----------|---------|
| 608694 | Técnico nominado + email institucional + evidencia Mercado Público. |
| 622998 | Responsable de contrato / proyectos con nombre + email institucional (MP). |
| 608621 | Buzón oficial proveedores/compras + estrategia compras + MP. |
| 617311 | Responsable de contrato / proyectos con nombre + email institucional (MP). |
| 619403 | Responsable de contrato / proyectos con nombre + email institucional (MP). |
| 608386 | Responsable de contrato / proyectos con nombre + email institucional (MP). |
| 609442 | Responsable de contrato / proyectos con nombre + email institucional (MP). |
| 610539 | Responsable de contrato / proyectos con nombre + email institucional (MP). |

## 2. Las 12 siguientes (needs_validation)

Alta prioridad o pistas DR útiles, pero **no** pasan el umbral conservador de “listo” (sin email, baja DR, Gmail, buzón financiero, o solo central/derivación).

| `id_lead` | `priority_score` | Nota breve |
|-----------|------------------|------------|
| 610262 | 7.00 | DR marcó baja / sin emails en el informe de 50 filas. |
| 613478 | 6.90 | DR marcó baja / sin emails en el informe de 50 filas. |
| 622411 | 6.80 | Hallazgos no alcanzan umbral conservador (solo central/derivación, persona sin rol de contrato, o sin buzón de compras claro). |
| 617158 | 6.50 | Hallazgos no alcanzan umbral conservador (solo central/derivación, persona sin rol de contrato, o sin buzón de compras claro). |
| 607646 | 6.50 | DR marcó baja / sin emails en el informe de 50 filas. |
| 607728 | 6.50 | DR marcó baja / sin emails en el informe de 50 filas. |
| 609188 | 6.50 | DR marcó baja / sin emails en el informe de 50 filas. |
| 616351 | 6.50 | DR marcó baja / sin emails en el informe de 50 filas. |
| 617497 | 6.10 | Primer contacto es buzón financiero/tasas (pagos, egresos, garantías, etc.); no cuenta como ruta de compras lista para outreach. |
| 621458 | 6.10 | Hallazgos no alcanzan umbral conservador (solo central/derivación, persona sin rol de contrato, o sin buzón de compras claro). |
| 613244 | 5.90 | DR marcó baja / sin emails en el informe de 50 filas. |
| 618747 | 5.80 | Primer contacto es buzón financiero/tasas (pagos, egresos, garantías, etc.); no cuenta como ruta de compras lista para outreach. |

## 3. Orden sugerido para el informe al cliente

Usar `report_section_order` en `leads_top20_for_client_report.csv` (**1–20**): primero las **8** con `readiness_status=ready_now`, luego las **12** con `needs_validation` en el orden del CSV.

## 4. Redacción cliente: “listas para contacto”

Mostrar como **listas para contacto** (tras validación spot-check en Mercado Público) solo las filas con **`readiness_status=ready_now`** — hoy son los **8** IDs: **608694, 622998, 608621, 617311, 619403, 608386, 609442, 610539**.

## 5. Redacción cliente: “priorizadas para validación comercial”

Las filas con **`readiness_status=needs_validation`**: prioridad/licitación fuerte o contacto parcial; el mensaje debe ser **pipeline / investigación en curso**, no “contacto verificado”.

## 6. Resultado esperado tras import + audit

Con la hoja `leads_contact_hunt_current.csv` ya parcheada y **reimportada** a SQLite, `audit_contact_readiness.py` debe listar **8** leads en `reports/out/active/leads_ready_to_contact.csv` (los mismos ocho `id_lead` que §4). `import_contact_hunt_to_sqlite.py --promote-procurement` promueve a `lead_master` las filas con **compras** rellena; el lead **608694** (solo técnico) suele quedar sin promoción de compras — es normal.

---

## Comandos para alinear SQLite y regenerar auditoría / cliente

```bash
uv run python scripts/leads/advanced/import_contact_hunt_to_sqlite.py \
  --csv reports/out/active/leads_contact_hunt_current.csv \
  --promote-procurement
uv run python scripts/leads/advanced/audit_contact_readiness.py
uv run python scripts/reports/build_leads_client_pack.py
```

- **Import:** vuelca la hoja hunt actualizada a `lead_outreach_enrichment` y opcionalmente promueve compras a `lead_master` (`--promote-procurement`).
- **Audit:** regenera `docs/generated/CONTACT_READINESS_AUDIT.md` y los tres CSV de readiness en `reports/out/active/`.
- **Client pack:** regenera `reports/out/client_pack_latest/`.

---
Generado por `scripts/leads/campaigns/apply_ready8_contact_patch.py`.
