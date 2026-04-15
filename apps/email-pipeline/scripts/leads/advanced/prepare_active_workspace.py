#!/usr/bin/env python3
"""Mantener `reports/out/active/` pequeño y predecible.

**Archivos operativos principales en active/** (el resto se archiva al limpiar):

- `leads_weekly_focus.csv` + `leads_weekly_focus_summary_es.md`
- `leads_contact_hunt_current.csv`
- Opcional: `leads_contact_hunt_for_deepsearch.csv`

Derivados (shortlist, client review, merged, unified) y paquetes para cliente viven fuera
de este núcleo: regenerar a `reports/out/archive/` o generar `reports/out/client_pack_latest/`
con `scripts/reports/build_leads_client_pack.py`.

- Archiva duplicados / derivados (CSV inglés, con_db, netnew, hunt_es duplicado, etc.).
- Opcional: regenera `leads_contact_hunt_for_deepsearch.csv`.
- Opcional: genera `leads_active_unified.csv` (foco + hunt; se archiva en la próxima limpieza si no está en el núcleo).
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Archivar siempre si aparecen (regenerables o duplicados de idioma).
ARCHIVE_ALWAYS = frozenset(
    {
        "leads_shortlist.csv",
        "leads_client_review.csv",
        "leads_contact_hunt_es.csv",
        "leads_contact_hunt_current_con_db.csv",
        "leads_contact_hunt_netnew_sin_contactos_db.csv",
    }
)

# Núcleo operativo en active/; cualquier otro CSV se mueve a archive/ al limpiar.
CANONICAL_KEEP = frozenset(
    {
        "leads_weekly_focus_summary_es.md",
        "leads_weekly_focus.csv",
        "leads_contact_hunt_current.csv",
        "leads_contact_hunt_for_deepsearch.csv",
    }
)

FOCUS_COLS = [
    "id_lead",
    "fit_bucket",
    "priority_score",
    "org_name",
    "buyer_kind",
    "equipment_match_tags",
    "lab_context_score",
    "already_in_archive_flag",
    "source_url",
    "evidence_summary",
    "status",
    "next_action",
]

def _load_hunt_headers() -> list[str]:
    path = _ROOT / "scripts" / "leads" / "export_contact_hunt_sheet.py"
    spec = importlib.util.spec_from_file_location("export_contact_hunt_sheet_mod", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.HEADERS)


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def _archive_dir(root: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    d = root / "archive" / f"active_cleanup_{ts}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _move_to_archive(src: Path, dest_dir: Path, dry_run: bool) -> None:
    dest = dest_dir / src.name
    if dry_run:
        print(f"[dry-run] movería: {src} -> {dest}")
        return
    shutil.move(str(src), str(dest))
    print(f"Movido: {src.name} -> {dest}")


def _build_unified(active: Path) -> None:
    focus_path = active / "leads_weekly_focus.csv"
    hunt_path = active / "leads_contact_hunt_current.csv"
    out_path = active / "leads_active_unified.csv"

    _, focus_rows = _read_csv(focus_path)
    _, hunt_rows = _read_csv(hunt_path)
    hunt_by_id: dict[str, dict[str, str]] = {}
    for r in hunt_rows:
        k = (r.get("id_lead") or "").strip()
        if k:
            hunt_by_id[k] = r

    hunt_tail = [h for h in _load_hunt_headers() if h != "id_lead"]
    out_fields = FOCUS_COLS + hunt_tail
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields, extrasaction="ignore")
        w.writeheader()
        for fr in focus_rows:
            rid = (fr.get("id_lead") or "").strip()
            hr = hunt_by_id.get(rid, {})
            row: dict[str, str] = {}
            for c in FOCUS_COLS:
                row[c] = (fr.get(c) or "").strip()
            for c in hunt_tail:
                row[c] = (hr.get(c) or "").strip()
            w.writerow(row)
    print(f"Escrito unificado: {out_path} ({len(focus_rows)} filas).")


def main() -> int:
    ap = argparse.ArgumentParser(description="Limpia reports/out/active y regenera derivados opcionales.")
    ap.add_argument(
        "--active-dir",
        type=Path,
        default=Path("reports/out/active"),
        help="Carpeta active (default: reports/out/active)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo imprimir qué se haría.",
    )
    ap.add_argument(
        "--deepsearch",
        action="store_true",
        help="Regenerar leads_contact_hunt_for_deepsearch.csv vía export_contact_hunt_sheet_existing_contacts_check.",
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--unified",
        action="store_true",
        help="Generar leads_active_unified.csv (weekly focus + hunt current por id_lead).",
    )
    args = ap.parse_args()

    active = args.active_dir.resolve()
    if not active.is_dir():
        print(f"No existe {active}", file=sys.stderr)
        return 1

    reports_out = active.parent
    dest: Path | None = None

    def _dest() -> Path:
        nonlocal dest
        if dest is None:
            dest = _archive_dir(reports_out)
        return dest

    moved = 0
    for p in sorted(active.iterdir()):
        if not p.is_file():
            continue
        name = p.name
        if name in ARCHIVE_ALWAYS:
            _move_to_archive(p, _dest(), args.dry_run)
            moved += 1
        elif name.endswith(".csv") and name not in CANONICAL_KEEP:
            # CSV desconocido en active: archivar para reducir ruido
            print(f"Advertencia: CSV no canónico en active: {name}", file=sys.stderr)
            _move_to_archive(p, _dest(), args.dry_run)
            moved += 1

    if moved == 0:
        print("Nada que archivar en active/.")
    elif args.dry_run:
        print(f"[dry-run] Se archivarían ~{moved} archivos bajo {_dest() if dest else '(nuevo)'}")
    else:
        print(f"Archivo de limpieza: {dest} ({moved} archivos movidos).")

    db_arg: list[str] = []
    if args.db:
        db_arg = ["--db", str(args.db)]

    if args.deepsearch:
        inp = active / "leads_contact_hunt_current.csv"
        outp = active / "leads_contact_hunt_for_deepsearch.csv"
        if not inp.exists():
            print(f"Falta {inp}; exporta primero contact_hunt_current.", file=sys.stderr)
            return 2
        cmd = [
            sys.executable,
            str(_ROOT / "scripts" / "leads" / "export_contact_hunt_sheet_existing_contacts_check.py"),
            "-i",
            str(inp),
            "-o",
            str(outp),
            "--exclude-has-contacts",
            *db_arg,
        ]
        if args.dry_run:
            print("[dry-run] ejecutaría:", " ".join(cmd))
        else:
            subprocess.run(cmd, check=True)
            print(f"Regenerado: {outp}")

    if args.unified:
        fp = active / "leads_weekly_focus.csv"
        hp = active / "leads_contact_hunt_current.csv"
        if not fp.exists() or not hp.exists():
            print(
                f"Faltan {fp.name} o {hp.name}; ejecuta run_weekly_focus y export_contact_hunt primero.",
                file=sys.stderr,
            )
            return 3
        if args.dry_run:
            print("[dry-run] generaría leads_active_unified.csv")
        else:
            _build_unified(active)

    print(
        "\nNúcleo en active/: leads_weekly_focus.csv, leads_weekly_focus_summary_es.md, "
        "leads_contact_hunt_current.csv, opcional leads_contact_hunt_for_deepsearch.csv. "
        "Paquete cliente: reports/out/client_pack_latest/ (build_leads_client_pack.py)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
