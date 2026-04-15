#!/usr/bin/env python3
"""Apply Deep Research top-10 contact findings into a v1.2 contact-hunt sheet.

This script is intentionally simple and conservative:
- It fills contact/evidence fields for specific `id_lead` values only.
- It does NOT guess or infer missing values beyond what was explicitly provided.
- By default it overwrites only empty cells.

NOTE: The mapping below was extracted from the Deep Research text table pasted by the user.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def _is_empty(v: str | None) -> bool:
    return v is None or str(v).strip() == ""


# ---- Extracted from the pasted Deep Research table (top-10) ----
# Each entry maps to fields in the contact-hunt sheet.
TOP10: dict[str, dict[str, str]] = {
    # id_lead: {sheet_column: value}
    "1": {
        # Deep Research marked "Not found" / ambiguous for this one.
        "confianza_contacto": "",
    },
    "294": {
        # Procurement
        "nombre_contacto_compras": "Berta Mella Hermosilla",
        "rol_contacto_compras": "Responsable de contrato / adquisiciones",
        "telefono_publico_compras": "56-41-2725060",
        "url_evidencia_compras": "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=3265-24-LP11",
        # Technical
        "nombre_contacto_tecnico": "Rodolfo Mamut Henriquez",
        "rol_contacto_tecnico": "Jefe Unidad Laboratorio Clínico y UMT (S)",
        "telefono_publico_tecnico": "",
        "url_evidencia_tecnico": "https://www.hospitaldetome.cl/cargador/transparencia/REHT390LEYDELLOBBY%284%29.pdf",
        # General
        "sitio_oficial_estimado": "https://hospitaldetome.cl/",
        "dominio_oficial_estimado": "hospitaldetome.cl",
        "telefono_contacto_general": "41-2724950",
        "url_evidencia_general": "https://hospitaldetome.cl/organigrama/",
        "confianza_contacto": "alta",
    },
    "624": {
        "nombre_contacto_compras": "Roberto Hacin",
        "rol_contacto_compras": "Responsable de contrato",
        "telefono_publico_compras": "56-63-2264855",
        "url_evidencia_compras": "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=1057545-44-LR21",
        "telefono_contacto_general": "2265580",
        "url_evidencia_general": "https://www.superdesalud.gob.cl/registro/hospital-de-corral/",
        "confianza_contacto": "alta",
    },
    "813": {
        "nombre_contacto_compras": "Alejandra Fernández Almendra",
        "rol_contacto_compras": "Responsable de contrato",
        "telefono_publico_compras": "56-41-3270758",
        "url_evidencia_compras": "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=4375-138-LP25",

        "nombre_contacto_tecnico": "Roberto Vega Montanares",
        "rol_contacto_tecnico": "Jefatura Laboratorio Clínico",
        "telefono_publico_tecnico": "2687666",
        "url_evidencia_tecnico": "https://hospitalregional.cl/repo_calidad/20250627_APL_1.4_FICHA_DE_ADSCRIPCION_PROGRAMA_PEEC_2025_LABORATORIO_URGENCIA.pdf",

        "sitio_oficial_estimado": "https://www.hospitalregional.cl/",
        "dominio_oficial_estimado": "hospitalregional.cl",
        "telefono_contacto_general": "41 2 722 500",
        "url_evidencia_general": "https://www.hospitalregional.cl/",
        "confianza_contacto": "alta",
    },
    "883": {
        # Procurement name not found; role + phone exist.
        "nombre_contacto_compras": "",
        "rol_contacto_compras": "Responsable de contrato",
        "telefono_publico_compras": "56-72-2336122",
        "url_evidencia_compras": "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=1627-79-LP25",

        "sitio_oficial_estimado": "https://www.hospitalsanfernando.cl/",
        "dominio_oficial_estimado": "hospitalsanfernando.cl",
        "telefono_contacto_general": "072-2335104",
        "url_evidencia_general": "https://www.superdesalud.gob.cl/registro/hospital-san-juan-de-dios-de-san-fernando/",
        "confianza_contacto": "media",
    },
    "1086": {
        "nombre_contacto_tecnico": "Marlene Muñoz González",
        "rol_contacto_tecnico": "Directora (Servicio de Salud Osorno)",
        "telefono_publico_tecnico": "(64) 233 57 87",
        "url_evidencia_tecnico": "https://ssosorno.redsalud.gob.cl/conozcanos/elementor-356/",

        "sitio_oficial_estimado": "https://ssosorno.redsalud.gob.cl/",
        "dominio_oficial_estimado": "ssosorno.redsalud.gob.cl",
        "telefono_contacto_general": "(64) 233 57 87",
        "url_evidencia_general": "https://ssosorno.redsalud.gob.cl/conozcanos/elementor-356/",
        "confianza_contacto": "alta",
    },
    "302": {
        "nombre_contacto_compras": "Macarena Viertel",
        "rol_contacto_compras": "Administrador de contratos",
        "telefono_publico_compras": "56-64-2335205",
        "url_evidencia_compras": "https://www.mercadopublico.cl/Procurement/Modules/RFB/StepsProcessAward/PreviewAwardAct.aspx?qs=58W7iDkgC%2Fj%2F0wSBx66YKbeqzhqcmxfXu7C2uWh0N1w%3D",

        "dominio_oficial_estimado": "sslosrios.redsalud.gob.cl",
        "sitio_oficial_estimado": "https://sslosrios.redsalud.gob.cl/hospital-la-union/",
        "telefono_contacto_general": "642335200",
        "url_evidencia_general": "https://www.superdesalud.gob.cl/registro/hospital-dr-juan-morey-de-la-union/",
        "confianza_contacto": "alta",
    },
    "1155": {
        "nombre_contacto_compras": "Gustavo Burgos",
        "rol_contacto_compras": "Responsable de contrato",
        "telefono_publico_compras": "56-41-2725504",
        "url_evidencia_compras": "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=2098-191-LP25",

        "sitio_oficial_estimado": "https://hospitaldecuranilahue.cl/",
        "dominio_oficial_estimado": "hospitaldecuranilahue.cl",
        "telefono_contacto_general": "56-41-2725504",
        "url_evidencia_general": "https://hospitaldecuranilahue.cl/wordpress/wp-content/uploads/2022/12/PROTOCOLO-TRATO-AL-USUARIO-HRAV-V01-2.pdf",
        "confianza_contacto": "alta",
    },
    "1161": {
        "nombre_contacto_compras": "Jorge Unda Araya",
        "rol_contacto_compras": "Responsable de contrato",
        "telefono_publico_compras": "56-41-2724313",
        "url_evidencia_compras": "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=652-122-LQ23",
        "confianza_contacto": "alta",
    },
    "6540": {
        "nombre_contacto_compras": "Werner Aguilar Labraña",
        "rol_contacto_compras": "Responsable de contrato",
        "telefono_publico_compras": "56-75-565934",
        "url_evidencia_compras": "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?qs=EiTDGFJ72thywTpLFVTm0w%3D%3D",

        "nombre_contacto_tecnico": "María Fernanda Gutiérrez González",
        "rol_contacto_tecnico": "Jefe Servicio Laboratorio Clínico",
        "telefono_publico_tecnico": "75 2566337",
        "url_evidencia_tecnico": "https://www.hospitalcurico.gob.cl/?page_id=4766",

        "sitio_oficial_estimado": "https://www.hospitalcurico.gob.cl/",
        "dominio_oficial_estimado": "hospitalcurico.gob.cl",
        "telefono_contacto_general": "75 2566200",
        "url_evidencia_general": "https://www.hospitalcurico.gob.cl/?page_id=887",
        "confianza_contacto": "alta",
    },
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill Deep Research contacts into an existing contact-hunt sheet.")
    ap.add_argument("--base", "-b", type=Path, required=True, help="Base contact-hunt CSV (v1.2).")
    ap.add_argument("--out", "-o", type=Path, required=True, help="Output CSV path.")
    ap.add_argument(
        "--overwrite-non-empty",
        action="store_true",
        help="Overwrite non-empty cells (default: only fill empty cells).",
    )
    args = ap.parse_args()

    with args.base.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        # Some CSVs have leading whitespace in the header cell due to BOM/format.
        fieldnames = [h.strip() if h else h for h in (reader.fieldnames or [])]
        reader.fieldnames = fieldnames
        rows = list(reader)

    if not rows:
        raise SystemExit("Base CSV has no rows.")
    if "id_lead" not in fieldnames:
        raise SystemExit("Base CSV must include `id_lead` column.")

    filled_rows = 0
    for row in rows:
        rid = (row.get("id_lead") or "").strip()
        if rid not in TOP10:
            continue
        upd = TOP10[rid]
        changed = False
        for k, v in upd.items():
            if k not in row:
                continue
            if not args.overwrite_non_empty and not _is_empty(row.get(k)):
                continue
            if v is None:
                v = ""
            row[k] = v
            if _is_empty(v) is False:
                changed = True
        if changed:
            filled_rows += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Updated {filled_rows} lead rows in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

