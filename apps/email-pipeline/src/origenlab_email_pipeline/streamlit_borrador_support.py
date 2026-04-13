"""Utilidades compartidas del flujo «Borrador comercial» / batches pilot (solo Streamlit UI)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from origenlab_email_pipeline.tatiana_copilot.marketing_outreach import (
    MARKETING_VARIANT_FOLLOWUP,
    MARKETING_VARIANT_GENERAL,
    MARKETING_VARIANT_HOSPITALES,
    MARKETING_VARIANT_INDUSTRIA,
    MARKETING_VARIANT_PUBLICO,
    MARKETING_VARIANT_UNIVERSIDADES,
)


def fmt_marketing_variant(v: str) -> str:
    return {
        MARKETING_VARIANT_GENERAL: "Presentacion general",
        MARKETING_VARIANT_UNIVERSIDADES: "Universidades / investigacion",
        MARKETING_VARIANT_HOSPITALES: "Hospitales / laboratorio clinico",
        MARKETING_VARIANT_INDUSTRIA: "Industria / QA / alimentos",
        MARKETING_VARIANT_PUBLICO: "Instituciones publicas / compras",
        MARKETING_VARIANT_FOLLOWUP: "Follow-up sin respuesta",
    }.get(v, v)


def load_existing_pilot_batch(batch_dir_raw: str) -> tuple[pd.DataFrame | None, list[dict[str, Any]] | None, str | None]:
    """Load an existing Tatiana pilot batch folder for read-only review in Streamlit."""
    raw = (batch_dir_raw or "").strip()
    if not raw:
        return None, None, "Ingrese una carpeta de batch."
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        return None, None, f"No existe la carpeta: {p}"
    if not p.is_dir():
        return None, None, f"La ruta no es carpeta: {p}"
    review_csv = p / "pilot_review.csv"
    if not review_csv.is_file():
        return None, None, f"No se encontró `pilot_review.csv` en: {p}"
    try:
        df = pd.read_csv(review_csv).fillna("")
    except Exception as exc:
        return None, None, f"No se pudo leer `pilot_review.csv`: {exc}"
    raw_cases: list[dict[str, Any]] = []
    for cf in sorted(p.glob("case_*.json")):
        try:
            obj = json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(obj, dict):
            obj["_case_path"] = str(cf)
            obj["_case_file"] = cf.name
            raw_cases.append(obj)
    case_by_id: dict[str, dict[str, Any]] = {}
    for obj in raw_cases:
        case = dict(obj.get("case") or {})
        cid = str(case.get("case_id") or "").strip()
        if cid:
            case_by_id[cid] = obj
    cases: list[dict[str, Any]] = []
    used: set[str] = set()
    if "case_id" in df.columns:
        for cid_raw in df["case_id"].astype(str).tolist():
            cid = str(cid_raw).strip()
            if cid and cid in case_by_id and cid not in used:
                cases.append(case_by_id[cid])
                used.add(cid)
    for cid in sorted(case_by_id.keys()):
        if cid not in used:
            cases.append(case_by_id[cid])
    return df, cases, None


def pilot_batch_signature(batch_dir_raw: str) -> str | None:
    raw = (batch_dir_raw or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    review_csv = p / "pilot_review.csv"
    if not review_csv.is_file():
        return None
    case_files = sorted(p.glob("case_*.json"))
    try:
        review_mtime = review_csv.stat().st_mtime_ns
        case_sig = ",".join(f"{cf.name}:{cf.stat().st_mtime_ns}" for cf in case_files)
    except OSError:
        return None
    return f"{review_mtime}|{len(case_files)}|{case_sig}"


def contact_suppression_reason_label(code: str | None) -> str:
    return {
        "bounce_no_such_user": "Rebote: no existe la casilla",
        "bounce_access_denied": "Rebote: acceso denegado",
        "bounce_other": "Rebote: otro motivo",
        "manual_do_not_contact": "No contactar",
        "reported_non_delivery": "Informa no recibir correo (heurística)",
    }.get(code or "", code or "—")


__all__ = [
    "fmt_marketing_variant",
    "load_existing_pilot_batch",
    "pilot_batch_signature",
    "contact_suppression_reason_label",
]
