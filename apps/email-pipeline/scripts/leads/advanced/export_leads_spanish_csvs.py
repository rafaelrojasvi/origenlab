#!/usr/bin/env python3
"""Write Spanish, client-friendly versions of lead exports (advanced / parked helper).

Default: **plan-only** — reads English inputs and prints row counts; pass ``--write-outputs``
to write Spanish CSVs. Not a daily outbound lane and **not send approval**.

Creates three files when ``--write-outputs`` is passed (under ``--out-dir``):
- leads_shortlist_es.csv (weekly shortlist)
- leads_client_review_es.csv (client review with archive comparison)
- leads_export_es.csv (full export with Spanish headers)

``--export`` is the **input path** to the full English export CSV (not a boolean write flag).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        rows = list(r)
        return (r.fieldnames or []), rows


def _write_rows(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def _map_fit_bucket(v: str) -> str:
    v = (v or "").strip().lower()
    return {
        "high_fit": "alto_ajuste",
        "medium_fit": "ajuste_medio",
        "low_fit": "bajo_ajuste",
    }.get(v, v or "")


def _map_buyer_kind(v: str) -> str:
    v = (v or "").strip().lower()
    return {
        "hospital": "hospital",
        "universidad": "universidad",
        "agricola": "agro/sag",
        "municipal": "municipalidad",
        "gobierno": "gobierno",
        "publico": "organismo_público",
    }.get(v, v or "")


def _to_spanish_row(row: dict[str, str], *, mode: str) -> dict[str, str]:
    # id_lead first for stable joins (matches lead_master.id)
    out: dict[str, str] = {"id_lead": (row.get("id_lead") or "").strip()}
    out["ajuste"] = _map_fit_bucket(row.get("fit_bucket", ""))
    out["puntaje"] = row.get("priority_score", "")
    out["motivo_puntaje"] = row.get("priority_reason", "")
    out["organización"] = row.get("org_name", "")
    out["tipo_comprador"] = _map_buyer_kind(row.get("buyer_kind", ""))
    out["región"] = row.get("region", "")
    out["ciudad"] = row.get("city", "")
    out["tags_equipo"] = row.get("equipment_match_tags", "")
    out["contexto_lab_score"] = row.get("lab_context_score", "")
    out["contexto_lab_tags"] = row.get("lab_context_tags", "")
    out["evidencia"] = row.get("evidence_summary", "")
    out["url"] = row.get("source_url", "")

    if mode in ("shortlist", "export"):
        out["fuente"] = row.get("source_name", "")
        out["tipo_lead"] = row.get("lead_type", "")
        out["estado"] = row.get("status", "")
        out["dueño_revisión"] = row.get("review_owner", "")
        out["siguiente_acción"] = row.get("next_action", "")
        out["contacto_nombre"] = row.get("contact_name", "")
        out["contacto_email"] = row.get("email", "")
        out["contacto_tel"] = row.get("phone", "")
        out["sitio_web"] = row.get("website", "")
        out["ya_en_archivo"] = row.get("already_in_archive_flag", "")
        out["org_archivo_match"] = row.get("matched_org_name", "")

    if mode == "client_review":
        out["contacto_nombre"] = row.get("contact_name", "")
        out["contacto_email"] = row.get("lead_email", "")
        out["contacto_tel"] = row.get("lead_phone", "")
        out["sitio_web"] = row.get("lead_website", "")
        out["ya_en_archivo"] = row.get("already_in_archive_flag", "")
        out["org_archivo_match"] = row.get("matched_org_name", "")
        out["dominio_match"] = row.get("matched_domain", "")
        out["contactos_existentes_clave"] = row.get("existing_key_contacts", "")
        out["emails_existentes_top"] = row.get("existing_top_contact_emails", "")
        out["emails_existentes_total"] = row.get("existing_total_emails", "")
        out["emails_existentes_cotizaciones"] = row.get("existing_quote_email_count", "")
        out["estado"] = row.get("status", "")
        out["dueño_revisión"] = row.get("review_owner", "")
        out["siguiente_acción"] = row.get("next_action", "")
        out["notas"] = row.get("notes", "")

    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Plan or write Spanish-friendly CSV versions of lead exports (plan-only by default)."
    )
    ap.add_argument("--out-dir", type=Path, default=Path("reports/out"), help="Output directory (default: reports/out)")
    ap.add_argument("--shortlist", type=Path, default=Path("reports/out/leads_shortlist.csv"))
    ap.add_argument("--client-review", type=Path, default=Path("reports/out/leads_client_review.csv"))
    ap.add_argument(
        "--export",
        type=Path,
        default=Path("reports/out/leads_export.csv"),
        help="Input path to full English export CSV (not a write flag).",
    )
    ap.add_argument(
        "--write-outputs",
        action="store_true",
        help="Write leads_shortlist_es.csv, leads_client_review_es.csv, and leads_export_es.csv.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Same as default (plan-only). Kept for compatibility.",
    )
    args = ap.parse_args(argv)

    if args.write_outputs and args.dry_run:
        ap.error("--write-outputs and --dry-run cannot be used together")

    write_outputs = bool(args.write_outputs)

    _, shortlist_in = _read_rows(args.shortlist)
    s_rows = [_to_spanish_row(r, mode="shortlist") for r in shortlist_in]
    s_headers = list(s_rows[0].keys()) if s_rows else []

    _, client_in = _read_rows(args.client_review)
    c_rows = [_to_spanish_row(r, mode="client_review") for r in client_in]
    c_headers = list(c_rows[0].keys()) if c_rows else []

    _, export_in = _read_rows(args.export)
    e_rows = [_to_spanish_row(r, mode="export") for r in export_in]
    e_headers = list(e_rows[0].keys()) if e_rows else []

    shortlist_out = args.out_dir / "leads_shortlist_es.csv"
    client_out = args.out_dir / "leads_client_review_es.csv"
    export_out = args.out_dir / "leads_export_es.csv"

    if write_outputs:
        _write_rows(shortlist_out, s_headers, s_rows)
        _write_rows(client_out, c_headers, c_rows)
        _write_rows(export_out, e_headers, e_rows)
        print(
            f"Wrote Spanish CSVs to {args.out_dir}: "
            "leads_shortlist_es.csv, leads_client_review_es.csv, leads_export_es.csv"
        )
    else:
        print("Plan only: pass --write-outputs to write Spanish CSVs.")
        print(f"Planned output: {shortlist_out}")
        print(f"Planned output: {client_out}")
        print(f"Planned output: {export_out}")
        print(f"leads_shortlist_es.csv rows: {len(s_rows)}")
        print(f"leads_client_review_es.csv rows: {len(c_rows)}")
        print(f"leads_export_es.csv rows: {len(e_rows)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
