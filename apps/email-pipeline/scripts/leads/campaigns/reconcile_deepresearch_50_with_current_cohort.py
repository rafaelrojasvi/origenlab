#!/usr/bin/env python3
"""
Reconcile the finished 50-row Deep Research batch (official contacts from Mercado Público)
with the current operational hunt cohort.

Legacy reference CSVs under reports/out/reference/*DEEPRESEARCH* use a different id_lead
space (e.g. 1, 294, 624) and are reported separately — they must not be mixed with
current-style ids (607xxx–622xxx) for readiness.

Outputs:
  docs/generated/DEEP_RESEARCH_RECONCILIATION.md
  reports/out/active/leads_dr50_ready_candidates.csv
  reports/out/active/leads_dr50_needs_research.csv

Source of truth for the 50-row DR payload: versioned JSON under ``scripts/leads/campaigns/data/``
(``dr50_manifest_v1.json`` + ``dr50_payload_v1.json``) verified with SHA256. Update those
files when the DR CSV is revised; refresh ``expected_sha256`` in the manifest after edits.
"""

from __future__ import annotations

import csv
import glob
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.dr50_payload_loader import (  # noqa: E402
    Dr50PayloadError,
    load_verified_dr50_rows,
)
DEFAULT_CURRENT = REPO / "reports/out/active/leads_contact_hunt_current.csv"
DEFAULT_DEEPSEARCH = REPO / "reports/out/active/leads_contact_hunt_for_deepsearch.csv"
DEFAULT_REFERENCE_GLOB = str(REPO / "reports/out/reference/*DEEPRESEARCH*.csv")
OUT_MD = REPO / "docs/generated/DEEP_RESEARCH_RECONCILIATION.md"
OUT_READY = REPO / "reports/out/active/leads_dr50_ready_candidates.csv"
OUT_NEEDS = REPO / "reports/out/active/leads_dr50_needs_research.csv"

MEDIUM_PRIORITY_FLOOR = 5.0
MP_DETAILS = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion="


def _load_dr50_rows() -> list[dict[str, Any]]:
    try:
        return load_verified_dr50_rows(repo_root=REPO)
    except Dr50PayloadError as e:
        raise SystemExit(f"DR50 payload load failed: {e}") from e


def _mp_url(id_lic: str) -> str:
    return MP_DETAILS + id_lic.strip()


def load_hunt_by_id(path: Path) -> dict[int, dict[str, str]]:
    by_id: dict[int, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not row.get("id_lead", "").strip():
                continue
            i = int(row["id_lead"])
            by_id[i] = row
    return by_id


def first_n_deepsearch_ids(path: Path, n: int) -> list[int]:
    out: list[int] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i >= n:
                break
            out.append(int(row["id_lead"]))
    return out


def commercially_eligible(fit: str, priority: float) -> bool:
    if fit == "high_fit":
        return True
    if fit == "medium_fit":
        return priority > MEDIUM_PRIORITY_FLOOR
    return False


def primary_outreach_email(dr: Mapping[str, Any]) -> str:
    for key in ("buyer_email", "technical_email", "general_contact_email"):
        v = (dr.get(key) or "").strip()
        if v:
            return v
    return ""


def is_institutional_email(email: str) -> bool:
    if not email:
        return False
    el = email.lower()
    return (
        "@gmail.com" not in el
        and "@yahoo." not in el
        and "@hotmail." not in el
        and "@outlook." not in el
    )


def is_weak_finance_local(email: str) -> bool:
    local = email.lower().split("@", 1)[0]
    return any(
        w in local
        for w in (
            "pagos",
            "egresos",
            "garantias",
            "tesoreria",
            "contabilidad",
            "cobranza",
        )
    )


def is_procurement_inbox(email: str) -> bool:
    el = email.lower()
    return el.startswith(
        ("proveedores@", "compras@", "abastecimiento@", "licitaciones@", "adquisiciones@")
    )


def classify_dr_row(
    dr: Mapping[str, Any],
    hunt: Mapping[str, str],
) -> tuple[str, str]:
    """Return (bucket, reason) with bucket in ready|needs."""
    fit = (hunt.get("ajuste_fit") or "").strip()
    try:
        pri = float((hunt.get("puntaje_prioridad") or "0").strip())
    except ValueError:
        pri = 0.0

    if not commercially_eligible(fit, pri):
        return (
            "needs",
            f"fit={fit!r} y prioridad {pri} no pasan umbral activo (medium > {MEDIUM_PRIORITY_FLOOR}).",
        )

    ev = ""
    if dr.get("id_licitacion"):
        ev = _mp_url(str(dr["id_licitacion"]))
    if not ev.strip():
        ev = (hunt.get("url_fuente") or "").strip()
    if not ev:
        return ("needs", "Sin URL de evidencia (ni MP Details ni url_fuente del hunt).")

    primary = primary_outreach_email(dr)
    if not primary:
        return ("needs", "DR marcó baja / sin emails en el informe de 50 filas.")

    if not is_institutional_email(primary):
        return (
            "needs",
            "Primer email de contacto es no institucional (p. ej. Gmail en fila de responsable); usar correo institucional alternativo o revalidar.",
        )

    if is_weak_finance_local(primary):
        return (
            "needs",
            "Primer contacto es buzón financiero/tasas (pagos, egresos, garantías, etc.); no cuenta como ruta de compras lista para outreach.",
        )

    strat = (dr.get("dr_strategy") or "").strip().lower()
    buyer_name = (dr.get("buyer_contact_name") or "").strip()
    buyer_role = (dr.get("buyer_role") or "").lower()
    buyer_email = (dr.get("buyer_email") or "").strip()
    tech_email = (dr.get("technical_email") or "").strip()
    tech_name = (dr.get("technical_contact_name") or "").strip()
    gen_email = (dr.get("general_contact_email") or "").strip()

    if tech_email and tech_name and is_institutional_email(tech_email):
        return ("ready", "Técnico nominado + email institucional + evidencia Mercado Público.")

    if buyer_email and buyer_name and is_institutional_email(buyer_email):
        if any(
            x in buyer_role
            for x in (
                "responsable",
                "contrato",
                "proyectos",
                "infraestructura",
                "infrastructure",
                "sección",
            )
        ):
            return ("ready", "Responsable de contrato / proyectos con nombre + email institucional (MP).")

    if strat == "compras primero" and buyer_email and buyer_name and is_institutional_email(buyer_email):
        if not is_weak_finance_local(buyer_email):
            return ("ready", "Estrategia compras + comprador nominado + email institucional.")

    if strat == "compras primero":
        for em in (buyer_email, gen_email):
            if em and is_institutional_email(em) and is_procurement_inbox(em):
                return ("ready", "Buzón oficial proveedores/compras + estrategia compras + MP.")

    return (
        "needs",
        "Hallazgos no alcanzan umbral conservador (solo central/derivación, persona sin rol de contrato, o sin buzón de compras claro).",
    )


def recommended_route(dr: Mapping[str, Any]) -> str:
    s = (dr.get("dr_strategy") or "").strip()
    if s:
        return s
    return "Ver estrategia en hunt"


def legacy_reference_overlap(current_ids: set[int], ref_glob: str) -> tuple[int, list[int]]:
    overlap: list[int] = []
    for path in glob.glob(ref_glob):
        with open(path, newline="", encoding="utf-8-sig") as f:
            r = csv.DictReader(f)
            if not r.fieldnames or "id_lead" not in r.fieldnames:
                continue
            for row in r:
                raw = (row.get("id_lead") or "").strip()
                if not raw:
                    continue
                try:
                    lid = int(raw)
                except ValueError:
                    continue
                if lid in current_ids:
                    overlap.append(lid)
    return len(set(overlap)), sorted(set(overlap))


def build_row_out(
    hunt: Mapping[str, str],
    dr: Mapping[str, Any],
    bucket: str,
    reason: str,
) -> dict[str, str]:
    dr = dict(dr)
    ev = _mp_url(str(dr["id_licitacion"])) if dr.get("id_licitacion") else (hunt.get("url_fuente") or "")
    pe = primary_outreach_email(dr)
    phone = (dr.get("buyer_phone") or dr.get("technical_phone") or dr.get("general_contact_phone") or "").strip()
    name = (dr.get("buyer_contact_name") or dr.get("technical_contact_name") or "").strip()
    role = (dr.get("buyer_role") or dr.get("technical_role") or "").strip()
    if bucket == "ready":
        next_action = "Validar una vez en MP; volcar a hunt alineado + import SQLite."
    else:
        next_action = "Completar compras/técnico con fuente oficial o usar contacto alternativo institucional antes de outreach."

    return {
        "id_lead": hunt["id_lead"],
        "org_name": hunt.get("organizacion_compradora", ""),
        "fit_bucket": hunt.get("ajuste_fit", ""),
        "priority_score": hunt.get("puntaje_prioridad", ""),
        "buyer_kind": hunt.get("tipo_comprador", ""),
        "source_url": hunt.get("url_fuente", ""),
        "dr_confidence": str(dr.get("dr_confidence", "")),
        "dr_strategy": str(dr.get("dr_strategy", "")),
        "evidence_url_dr": ev,
        "recommended_contact_route": recommended_route(dr),
        "primary_contact_email": pe,
        "contact_name": name,
        "contact_role": role,
        "contact_phone": phone,
        "contact_source": "deep_research_50row_chat_export",
        "reconciliation_bucket": bucket,
        "reconciliation_reason": reason,
        "next_action": next_action,
    }


def main() -> None:
    hunt_by_id = load_hunt_by_id(DEFAULT_CURRENT)
    cohort_ids = set(hunt_by_id)
    first50 = first_n_deepsearch_ids(DEFAULT_DEEPSEARCH, 50)
    if set(first50) - cohort_ids:
        missing = sorted(set(first50) - cohort_ids)
        raise SystemExit(f"First-50 deepsearch ids not all in current hunt: {missing[:20]}")

    dr50_rows = _load_dr50_rows()
    dr_by_id = {int(r["id_lead"]): r for r in dr50_rows}
    if len(dr_by_id) != len(dr50_rows):
        raise SystemExit("Duplicate id_lead in verified DR50 payload")
    enriched_ids = set(dr_by_id)
    if len(enriched_ids) != 23:
        raise SystemExit(f"Expected 23 enriched DR rows, got {len(enriched_ids)}")

    legacy_n, legacy_list = legacy_reference_overlap(cohort_ids, DEFAULT_REFERENCE_GLOB)

    ready_rows: list[dict[str, str]] = []
    needs_rows: list[dict[str, str]] = []

    for lid in first50:
        hunt = hunt_by_id[lid]
        if lid in dr_by_id:
            dr = dict(dr_by_id[lid])
        else:
            dr = {
                "id_lead": lid,
                "dr_confidence": "baja",
                "dr_strategy": "central y derivación a abastecimiento",
                "buyer_contact_name": "",
                "buyer_role": "",
                "buyer_email": "",
                "buyer_phone": "",
                "technical_contact_name": "",
                "technical_role": "",
                "technical_email": "",
                "technical_phone": "",
                "general_contact_email": "",
                "general_contact_phone": "",
                "id_licitacion": "",
            }
        bucket, reason = classify_dr_row(dr, hunt)
        row = build_row_out(hunt, dr, bucket, reason)
        if bucket == "ready":
            ready_rows.append(row)
        else:
            needs_rows.append(row)

    fieldnames = [
        "id_lead",
        "org_name",
        "fit_bucket",
        "priority_score",
        "buyer_kind",
        "source_url",
        "dr_confidence",
        "dr_strategy",
        "evidence_url_dr",
        "recommended_contact_route",
        "primary_contact_email",
        "contact_name",
        "contact_role",
        "contact_phone",
        "contact_source",
        "reconciliation_bucket",
        "reconciliation_reason",
        "next_action",
    ]

    OUT_READY.parent.mkdir(parents=True, exist_ok=True)
    with OUT_READY.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(ready_rows)

    with OUT_NEEDS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(needs_rows)

    md = f"""# Deep Research reconciliation (two cohorts)

## 1. Legacy vs current-style Deep Research

| Cohort | Typical `id_lead` | Repo examples | Overlap with current hunt (200 ids) |
|--------|-------------------|---------------|-------------------------------------|
| **Legacy / non-current** | Small integers (1, 294, 302, 624, …) | `reports/out/reference/*DEEPRESEARCH*.csv` | **{legacy_n}** matching ids: `{legacy_list}` |
| **Current-style DR batch (this note)** | 607xxx–622xxx | `scripts/leads/campaigns/data/dr50_payload_v1.json` (SHA256 in `dr50_manifest_v1.json`) | First **50** rows of `leads_contact_hunt_for_deepsearch.csv` — **all 50** are in `leads_contact_hunt_current.csv` |

Legacy files are useful as **historical examples** only. They must **not** be used to mark readiness for the present 200-id operational cohort except where `id_lead` literally matches (here: **none**).

## 2. Scope of the reconciled DR batch

- **Input cohort slice:** first **50** rows of `reports/out/active/leads_contact_hunt_for_deepsearch.csv` (same **50** `id_lead` values as the finished chat report).
- **Operational anchor:** `reports/out/active/leads_contact_hunt_current.csv` (same 200 ids as deepsearch export in this repo).
- **Payload:** 23 rows with non-empty contact findings from the finished 50-row DR report + 27 rows marked *baja* (no published contact in that report).

## 3. Conservative readiness rules (code)

A row becomes **`ready`** only if:

1. `id_lead` is in the 50-row slice and in the current hunt file.
2. `high_fit` **or** (`medium_fit` and `puntaje_prioridad` > {MEDIUM_PRIORITY_FLOOR}).
3. Evidence URL: Mercado Público `DetailsAcquisition` from DR, else `url_fuente` from hunt.
4. First non-empty of buyer / technical / general email is **institutional** (Gmail/Yahoo/Hotmail/Outlook excluded from *primary*).
5. That email is **not** a finance-only local part (`pagos`, `egresos`, `garantias`, `tesoreria`, `contabilidad`, `cobranza`).
6. And **one** of:
   - Technical: named person + institutional technical email.
   - Buyer: named + institutional email + role hints (`responsable`, `contrato`, `proyectos`, `infraestructura`, `sección`).
   - Buyer: DR strategy `compras primero` + named buyer + institutional email.
   - Inbox: DR strategy `compras primero` + `proveedores@` / `compras@` / `abastecimiento@` / `licitaciones@` / `adquisiciones@` on institutional domain.

Otherwise **`needs`** (still promising, but not a vetted outreach route under this bar).

## 4. Results (regenerate with the script)

| Bucket | Count (50-row slice) |
|--------|----------------------|
| **Ready candidates** | **{len(ready_rows)}** → `reports/out/active/leads_dr50_ready_candidates.csv` |
| **Needs research** | **{len(needs_rows)}** → `reports/out/active/leads_dr50_needs_research.csv` |

## 5. Operational next steps

1. **Merge** these emails into `leads_contact_hunt_current.csv` (or enrichment import) so `audit_contact_readiness.py` and SQLite reflect them.
2. **Re-run** `uv run python scripts/leads/advanced/audit_contact_readiness.py` after the sheet/DB is updated.
3. Treat **Gmail** responsable rows (e.g. 610686) as **needs**: use the institutional CC email from the same row after human check.
4. Keep **legacy** `reference/*DEEPRESEARCH*` separate from this batch.

---

Generated by `scripts/leads/campaigns/reconcile_deepresearch_50_with_current_cohort.py`.
"""
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"Wrote {OUT_MD}")
    print(f"Wrote {OUT_READY} ({len(ready_rows)} rows)")
    print(f"Wrote {OUT_NEEDS} ({len(needs_rows)} rows)")
    print(f"Legacy DEEPRESEARCH id_lead overlap with current cohort: {legacy_n}")


if __name__ == "__main__":
    main()
