"""Tests for import_contact_hunt_to_sqlite."""

from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


def _load_import_script():
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts" / "leads" / "advanced" / "import_contact_hunt_to_sqlite.py"
    spec = importlib.util.spec_from_file_location("import_contact_hunt_to_sqlite", script_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_import_stores_json_and_promotes(tmp_path: Path) -> None:
    mod = _load_import_script()
    db = tmp_path / "t.sqlite"
    from origenlab_email_pipeline.leads_schema import ensure_leads_tables

    conn = sqlite3.connect(str(db))
    ensure_leads_tables(conn)
    conn.execute(
        """
        INSERT INTO lead_master (id, source_name, source_record_id, org_name, status)
        VALUES (607499, 'chilecompra', 'x', 'Hospital Test', 'nuevo')
        """
    )
    conn.commit()
    conn.close()

    csv_path = tmp_path / "hunt.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "id_lead",
                "nombre_contacto_compras",
                "email_publico_compras",
                "telefono_publico_compras",
                "nombre_contacto_tecnico",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "id_lead": "607499",
                "nombre_contacto_compras": "Ana Pérez",
                "email_publico_compras": "compras@hospital.cl",
                "telefono_publico_compras": "+56 9 1111 1111",
                "nombre_contacto_tecnico": "Luis Lab",
            }
        )

    argv = [
        "import_contact_hunt_to_sqlite.py",
        "--csv",
        str(csv_path),
        "--db",
        str(db),
        "--promote-procurement",
    ]
    old = sys.argv
    try:
        sys.argv = argv
        code = mod.main()
    finally:
        sys.argv = old
    assert code == 0

    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT enrichment_json FROM lead_outreach_enrichment WHERE lead_id=607499").fetchone()
    assert row
    data = json.loads(row[0])
    assert data["email_publico_compras"] == "compras@hospital.cl"
    assert data["nombre_contacto_tecnico"] == "Luis Lab"
    lm = conn.execute(
        "SELECT contact_name, email, phone FROM lead_master WHERE id=607499"
    ).fetchone()
    assert lm == ("Ana Pérez", "compras@hospital.cl", "+56 9 1111 1111")
    conn.close()


def test_import_fails_when_require_aligned_with_mismatch(tmp_path: Path) -> None:
    mod = _load_import_script()
    db = tmp_path / "t2.sqlite"
    from origenlab_email_pipeline.leads_schema import ensure_leads_tables

    conn = sqlite3.connect(str(db))
    ensure_leads_tables(conn)
    for lid in (1, 2):
        conn.execute(
            """
            INSERT INTO lead_master (id, source_name, source_record_id, org_name, status)
            VALUES (?, 'x', ?, 'Org', 'nuevo')
            """,
            (lid, str(lid)),
        )
    conn.commit()
    conn.close()

    base = tmp_path / "base2.csv"
    merged = tmp_path / "merged2.csv"
    with base.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id_lead", "k"])
        w.writeheader()
        w.writerow({"id_lead": "1", "k": "v"})
    with merged.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id_lead", "k"])
        w.writeheader()
        w.writerow({"id_lead": "2", "k": "v"})

    argv = [
        "import_contact_hunt_to_sqlite.py",
        "--csv",
        str(merged),
        "--db",
        str(db),
        "--require-aligned-with",
        str(base),
    ]
    old = sys.argv
    try:
        sys.argv = argv
        code = mod.main()
    finally:
        sys.argv = old
    assert code == 1
