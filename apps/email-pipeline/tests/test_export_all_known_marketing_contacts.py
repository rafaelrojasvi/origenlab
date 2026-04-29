from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "export_all_known_marketing_contacts.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_all_known_marketing_contacts", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def test_defaults_include_outreach_contacted_and_reference_txt_path(tmp_path: Path) -> None:
    reports_out = tmp_path / "reports" / "out"
    active = reports_out / "active"
    archive_research = reports_out / "archive" / "research"
    reference = reports_out / "reference"
    _write_csv(active / "outreach_contacted_all.csv", ["contact_email"], [["a@x.cl"]])
    _write_csv(archive_research / "chile_institutional_marketing_contacts.csv", ["contact_email"], [["b@y.cl"]])
    out_csv = active / "all_known_marketing_contacts_dedup.csv"
    out_txt = reference / "all_known_marketing_emails_dedup.txt"
    mod = _load_module()
    mod._ROOT = tmp_path
    rc = mod.main(["--out-csv", str(out_csv)])
    assert rc == 0
    assert out_csv.is_file()
    assert out_txt.is_file()
    with out_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    emails = sorted({r["contact_email"] for r in rows})
    assert emails == ["a@x.cl", "b@y.cl"]


def test_fails_safe_without_inputs_and_does_not_overwrite_existing(tmp_path: Path) -> None:
    reports_out = tmp_path / "reports" / "out"
    active = reports_out / "active"
    out_csv = active / "all_known_marketing_contacts_dedup.csv"
    _write_csv(out_csv, ["contact_email"], [["keep@x.cl"]])
    mod = _load_module()
    mod._ROOT = tmp_path
    rc = mod.main(["--out-csv", str(out_csv)])
    assert rc == 2
    with out_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["contact_email"] for r in rows] == ["keep@x.cl"]


def test_explicit_inputs_override_discovery(tmp_path: Path) -> None:
    in_csv = tmp_path / "custom.csv"
    out_csv = tmp_path / "reports" / "out" / "active" / "all_known_marketing_contacts_dedup.csv"
    _write_csv(in_csv, ["contact_email", "institution_name"], [["z@k.cl", "Inst Z"]])
    mod = _load_module()
    mod._ROOT = tmp_path
    rc = mod.main(["--out-csv", str(out_csv), str(in_csv)])
    assert rc == 0
    with out_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["contact_email"] for r in rows] == ["z@k.cl"]
