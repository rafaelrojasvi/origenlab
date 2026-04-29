from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("audit_research_candidate_evidence", str(path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_audit_candidate_evidence_flags_homepage_and_mismatch(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "qa"
        / "audit_research_candidate_evidence.py"
    )
    mod = _load_module(script)
    inp = tmp_path / "candidates.csv"
    inp.write_text(
        """institution_name,region,city,type,contact_email,contact_label,source_url,confidence,fit_signal
Universidad de Concepcion,BioBio,Concepcion,universidad,centromedico@gestion.uta.cl,Contacto,https://www.udec.cl,low,contacto general
Universidad de Chile,RM,Santiago,universidad,doping@ciq.uchile.cl,Laboratorio,https://ciq.uchile.cl/servicios/telefonos-y-correos,high,laboratorio de analisis
""",
        encoding="utf-8",
    )
    out_csv = tmp_path / "warnings.csv"
    out_json = tmp_path / "warnings.json"
    rc = mod.main(["--input", str(inp), "--out-csv", str(out_csv), "--out-json", str(out_json)])
    assert rc == 0
    with out_csv.open(encoding="utf-8", newline="") as f:
        warnings = list(csv.DictReader(f))
    assert len(warnings) == 1
    assert warnings[0]["contact_email"] == "centromedico@gestion.uta.cl"
    assert "homepage_source_weak_evidence" in warnings[0]["evidence_warning"]
    assert "email_domain_source_mismatch" in warnings[0]["evidence_warning"]
