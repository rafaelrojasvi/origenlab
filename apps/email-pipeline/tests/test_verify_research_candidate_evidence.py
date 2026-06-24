from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location("verify_research_candidate_evidence", str(path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_verify_404_and_strict(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "qa"
        / "verify_research_candidate_evidence.py"
    )
    mod = _load_module(script)

    def _fake_fetch(url: str, **kwargs):
        return 404, "text/html", "missing page"

    mod.fetch_source_text = _fake_fetch
    inp = tmp_path / "in.csv"
    inp.write_text(
        "institution_name,region,city,type,contact_email,contact_label,source_url,confidence,fit_signal\n"
        "U,RM,SCL,universidad,contacto@u.cl,Contacto,https://u.cl/contacto,low,contacto general\n",
        encoding="utf-8",
    )
    out_csv = tmp_path / "verify.csv"
    rc = mod.main(
        [
            "--input",
            str(inp),
            "--out-csv",
            str(out_csv),
            "--strict",
            "--require-source-200",
            "--require-email-visible",
            "--require-relevance-keywords",
        ]
    )
    assert rc == 1
    with out_csv.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert "source_url_unreachable" in rows[0]["evidence_warning"]
    assert "email_not_visible_on_source" in rows[0]["evidence_warning"]


def test_verify_email_visible_with_keywords_passes(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "qa"
        / "verify_research_candidate_evidence.py"
    )
    mod = _load_module(script)

    def _fake_fetch(url: str, **kwargs):
        return 200, "text/html", "doping@ciq.uchile.cl laboratorio de analisis y servicios"

    mod.fetch_source_text = _fake_fetch
    rows = mod.verify_rows(
        [
            {
                "institution_name": "Universidad de Chile",
                "contact_email": "doping@ciq.uchile.cl",
                "source_url": "https://ciq.uchile.cl/servicios/telefonos-y-correos",
            }
        ],
        require_email_visible=True,
        require_source_200=True,
        require_relevance_keywords=True,
    )
    assert rows[0]["evidence_ok"] == "1"
    assert rows[0]["evidence_warning"] == ""


def test_verify_official_gmail_allowed_with_exact_source(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "qa"
        / "verify_research_candidate_evidence.py"
    )
    mod = _load_module(script)

    def _fake_fetch(url: str, **kwargs):
        return 200, "text/html", "lab.contact@gmail.com laboratorio microbiologia y servicios"

    mod.fetch_source_text = _fake_fetch
    rows = mod.verify_rows(
        [
            {
                "institution_name": "Universidad de Chile",
                "contact_email": "lab.contact@gmail.com",
                "source_url": "https://ciq.uchile.cl/laboratorio/servicios-contacto",
            }
        ],
        require_email_visible=True,
        require_source_200=True,
        require_relevance_keywords=True,
    )
    assert rows[0]["evidence_ok"] == "1"


def test_verify_network_failure_does_not_crash(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "qa"
        / "verify_research_candidate_evidence.py"
    )
    mod = _load_module(script)

    def _fake_fetch(url: str, **kwargs):
        raise TimeoutError("network timeout")

    mod.fetch_source_text = _fake_fetch
    rows = mod.verify_rows(
        [
            {
                "institution_name": "Universidad de Valparaiso",
                "contact_email": "contacto@uv.cl",
                "source_url": "https://www.uv.cl/quimica",
            }
        ],
        require_email_visible=True,
        require_source_200=True,
        require_relevance_keywords=True,
    )
    assert "source_url_unreachable" in rows[0]["evidence_warning"]


def test_strip_html_to_text_removes_script_and_unescapes_entities() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "qa"
        / "verify_research_candidate_evidence.py"
    )
    mod = _load_module(script)
    html = b"<script>secret()</script><p>lab &amp; servicios</p>"
    text = mod._strip_html_to_text(html)
    assert "secret" not in text
    assert "lab & servicios" in text
