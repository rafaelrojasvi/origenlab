#!/usr/bin/env python3
"""Export a contact-hunt sheet (v1.2) for Chile leads.

The goal is to produce a Spanish CSV that is easy to use for manual + semi-assisted
contact hunting and outreach planning.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.leads_enrich import (
    derive_outreach_strategy,
    derive_product_angle,
    guess_official_site_and_domain,
)
from origenlab_email_pipeline.lead_export_queries import (
    sql_left_join_best_org_match,
    sql_upstream_active_lead_master,
)
from origenlab_email_pipeline.leads_schema import ensure_leads_tables

_LM_UPSTREAM_ACTIVE = sql_upstream_active_lead_master("lm")
_JOIN_BEST_ORG = sql_left_join_best_org_match(variant="org_domain_archive")


HEADERS = [
    # Identidad / scoring
    "id_lead",
    "fuente",
    "organizacion_compradora",
    "contacto_existente",
    "region",
    "ciudad",
    "tipo_lead",
    "tipo_organizacion",
    "tipo_comprador",
    "tags_equipamiento",
    "tags_contexto_laboratorio",
    "puntaje_prioridad",
    "motivo_puntaje",
    "ajuste_fit",
    "ya_en_archivo",
    "organizacion_match",
    # Fuente / contexto licitacion
    "url_fuente",
    "resumen_evidencia",
    "titulo_o_resumen_licitacion",
    "referencia_licitacion_o_buyer",
    "unidad_compradora_si_disponible",
    # Angulo de producto / ventas
    "angulo_producto_probable",
    "interes_equipamiento_probable",
    "estrategia_contacto_recomendada",
    "por_que_importa_este_lead",
    # Campos de workflow de hunting de contacto
    "sitio_oficial_estimado",
    "dominio_oficial_estimado",
    "url_contacto_compras",
    "url_transparencia_oirs",
    "url_pagina_laboratorio",
    "url_perfil_comprador",
    "notas_busqueda_contacto",
    # Captura de contactos verificados (para que el humano los llene)
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
    "confianza_contacto",
    # Workflow comercial
    "estado_seguimiento",
    "responsable_revision",
    "proximo_paso",
    "notas_manuales",
]


def _fit_rank(fit_bucket: str | None) -> int:
    fb = (fit_bucket or "").lower()
    if fb == "high_fit":
        return 0
    if fb == "medium_fit":
        return 1
    return 2


def _has_value(s: str | None) -> bool:
    return bool(s and s.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description="Export Spanish contact-hunt CSV for Chile leads (v1.2).")
    ap.add_argument("--out", "-o", type=Path, required=True, help="Ruta del CSV de salida.")
    ap.add_argument("--db", type=Path, default=None, help="Ruta SQLite (por defecto: desde config).")
    ap.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Máximo de filas en la hoja de hunting (por defecto: 200).",
    )
    ap.add_argument(
        "--buyer-kinds",
        type=str,
        default="",
        help="Lista separada por comas de buyer_kind a incluir (ej: 'hospital,universidad'). Por defecto: todos.",
    )
    ap.add_argument(
        "--net-new-only",
        action="store_true",
        help="Excluye leads que ya están en el archivo (ya_en_archivo=1).",
    )
    ap.add_argument(
        "--dedupe-by-org",
        action="store_true",
        help="Deduplica por organizacion_compradora, conservando el lead mejor rankeado por institución.",
    )
    ap.add_argument(
        "--include-low",
        action="store_true",
        help="Incluir low_fit (por defecto se excluyen para priorizar trabajo comercial).",
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    ensure_leads_tables(conn)

    buyer_kinds = [k.strip().lower() for k in args.buyer_kinds.split(",") if k.strip()]

    sql = f"""
        SELECT
          lm.id AS lead_id,
          lm.source_name,
          lm.org_name,
          lm.contact_name,
          lm.region,
          lm.city,
          lm.lead_type,
          lm.organization_type_guess,
          lm.buyer_kind,
          lm.equipment_match_tags,
          lm.lab_context_tags,
          lm.priority_score,
          lm.priority_reason,
          COALESCE(lm.fit_bucket, 'low_fit') AS fit_bucket,
          lm.evidence_summary,
          lm.source_record_id,
          lm.website,
          lm.domain,
          lm.status,
          lm.review_owner,
          lm.next_action,
          lm.notes,
          lm.source_url,
          m.matched_org_name,
          m.matched_domain,
          COALESCE(m.already_in_archive_flag, 0) AS already_in_archive_flag
        FROM lead_master lm
        {_JOIN_BEST_ORG}
        WHERE {_LM_UPSTREAM_ACTIVE}
          AND ((? = 1) OR (COALESCE(lm.fit_bucket, 'low_fit') != 'low_fit'))
          AND ((? = 0) OR (COALESCE(m.already_in_archive_flag, 0) = 0))
    """

    params: list[object] = [1 if args.include_low else 0, 1 if args.net_new_only else 0]
    if buyer_kinds:
        placeholders = ", ".join(["?"] * len(buyer_kinds))
        sql += f" AND LOWER(COALESCE(lm.buyer_kind,'')) IN ({placeholders})"
        params.extend(buyer_kinds)

    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()

    # Enrich in Python and sort according to business rules.
    enriched: list[dict[str, str]] = []
    for (
        lead_id,
        source_name,
        org_name,
        contact_name,
        region,
        city,
        lead_type,
        org_type_guess,
        buyer_kind,
        equipment_match_tags,
        lab_context_tags,
        priority_score,
        priority_reason,
        fit_bucket,
        evidence_summary,
        source_record_id,
        website,
        domain,
        status,
        review_owner,
        next_action,
        notes,
        source_url,
        matched_org_name,
        matched_domain,
        already_in_archive_flag,
    ) in rows:
        product_angle, equipment_interest, why_matters = derive_product_angle(
            source_name=source_name,
            buyer_kind=buyer_kind,
            organization_type_guess=org_type_guess,
            equipment_match_tags=equipment_match_tags,
            lab_context_tags=lab_context_tags,
            evidence_summary=evidence_summary,
        )
        outreach = derive_outreach_strategy(
            source_name=source_name,
            buyer_kind=buyer_kind,
            lead_type=lead_type,
            equipment_match_tags=equipment_match_tags,
            lab_context_tags=lab_context_tags,
        )
        site_guess, domain_guess = guess_official_site_and_domain(
            lead_website=website,
            lead_domain=domain,
            match_domain=matched_domain,
        )

        # Tender/title helpers
        titulo_resumen = (evidence_summary or "")[:200] if evidence_summary else ""
        referencia = source_record_id or ""

        row_out: dict[str, str] = {
            "id_lead": str(lead_id),
            "fuente": source_name or "",
            "organizacion_compradora": org_name or "",
            "contacto_existente": contact_name or "",
            "region": region or "",
            "ciudad": city or "",
            "tipo_lead": lead_type or "",
            "tipo_organizacion": org_type_guess or "",
            "tipo_comprador": buyer_kind or "",
            "tags_equipamiento": equipment_match_tags or "",
            "tags_contexto_laboratorio": lab_context_tags or "",
            "puntaje_prioridad": "" if priority_score is None else f"{priority_score:.2f}",
            "motivo_puntaje": priority_reason or "",
            "ajuste_fit": fit_bucket or "",
            "ya_en_archivo": "1" if already_in_archive_flag else "0",
            "organizacion_match": matched_org_name or "",
            "url_fuente": source_url or "",
            "resumen_evidencia": evidence_summary or "",
            "titulo_o_resumen_licitacion": titulo_resumen,
            "referencia_licitacion_o_buyer": referencia,
            "unidad_compradora_si_disponible": "",
            "angulo_producto_probable": product_angle,
            "interes_equipamiento_probable": equipment_interest,
            "estrategia_contacto_recomendada": outreach,
            "por_que_importa_este_lead": why_matters,
            "sitio_oficial_estimado": site_guess or "",
            "dominio_oficial_estimado": domain_guess or "",
            "url_contacto_compras": "",
            "url_transparencia_oirs": "",
            "url_pagina_laboratorio": "",
            "url_perfil_comprador": "",
            "notas_busqueda_contacto": "",
            "nombre_contacto_compras": "",
            "rol_contacto_compras": "",
            "email_publico_compras": "",
            "telefono_publico_compras": "",
            "nombre_contacto_tecnico": "",
            "rol_contacto_tecnico": "",
            "email_publico_tecnico": "",
            "telefono_publico_tecnico": "",
            "email_contacto_general": "",
            "telefono_contacto_general": "",
            "url_evidencia_compras": "",
            "url_evidencia_tecnico": "",
            "url_evidencia_general": "",
            "confianza_contacto": "",
            "estado_seguimiento": status or "",
            "responsable_revision": review_owner or "",
            "proximo_paso": next_action or "",
            "notas_manuales": notes or "",
        }
        enriched.append(row_out)

    # Sort for usefulness: fit, net-new, equipment, score, URL, product angle clarity.
    def sort_key(r: dict[str, str]) -> tuple:
        fit = _fit_rank(r.get("ajuste_fit"))
        already_flag = 1 if r.get("ya_en_archivo") == "1" else 0
        has_eq = 0 if _has_value(r.get("tags_equipamiento")) else 1
        try:
            score = float(r.get("puntaje_prioridad") or "0")
        except ValueError:
            score = 0.0
        has_url = 0 if _has_value(r.get("url_fuente")) else 1
        has_angle = 0 if _has_value(r.get("angulo_producto_probable")) else 1
        # For priority_score we want DESC, so use negative in sort key.
        return (fit, already_flag, has_eq, -score, has_url, has_angle)

    enriched.sort(key=sort_key)

    if args.dedupe_by_org:
        deduped: list[dict[str, str]] = []
        seen_org: set[str] = set()
        for r in enriched:
            org = (r.get("organizacion_compradora") or "").strip()
            key = org.lower()
            if key and key in seen_org:
                continue
            if key:
                seen_org.add(key)
            deduped.append(r)
            if args.limit and args.limit > 0 and len(deduped) >= args.limit:
                break
        enriched = deduped
    elif args.limit and args.limit > 0:
        enriched = enriched[: args.limit]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Use UTF-8 with BOM so Excel opens accents correctly.
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        for r in enriched:
            writer.writerow(r)

    print(f"Exported contact-hunt sheet ({len(enriched)} rows) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

