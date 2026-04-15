from __future__ import annotations

import csv
from pathlib import Path


def test_merge_fills_only_empty(tmp_path: Path) -> None:
    base = tmp_path / "base.csv"
    enr = tmp_path / "enr.csv"
    out = tmp_path / "out.csv"

    with base.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id_lead", "email_publico_compras", "url_evidencia_compras"])
        w.writeheader()
        w.writerow({"id_lead": "1", "email_publico_compras": "", "url_evidencia_compras": ""})
        w.writerow({"id_lead": "2", "email_publico_compras": "a@b.cl", "url_evidencia_compras": ""})

    with enr.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id_lead", "email_publico_compras", "url_evidencia_compras"])
        w.writeheader()
        w.writerow({"id_lead": "1", "email_publico_compras": "x@y.cl", "url_evidencia_compras": "http://e1"})
        w.writerow({"id_lead": "2", "email_publico_compras": "z@w.cl", "url_evidencia_compras": "http://e2"})

    # Import dynamically to avoid packaging assumptions.
    import importlib.util
    import sys

    script_path = Path("scripts/leads/advanced/merge_contact_hunt_enrichment.py")
    spec = importlib.util.spec_from_file_location("merge_contact_hunt_enrichment", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["merge_contact_hunt_enrichment"] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]

    sys_argv_backup = list(__import__("sys").argv)
    __import__("sys").argv = [
        "merge_contact_hunt_enrichment",
        "--base",
        str(base),
        "--enrichment",
        str(enr),
        "--out",
        str(out),
    ]
    try:
        module.main()  # type: ignore[attr-defined]
    finally:
        __import__("sys").argv = sys_argv_backup

    with out.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    r1 = next(r for r in rows if r["id_lead"] == "1")
    r2 = next(r for r in rows if r["id_lead"] == "2")
    assert r1["email_publico_compras"] == "x@y.cl"
    assert r1["url_evidencia_compras"] == "http://e1"
    # Non-empty email_publico_compras in base should not be overwritten by default.
    assert r2["email_publico_compras"] == "a@b.cl"
    assert r2["url_evidencia_compras"] == "http://e2"

