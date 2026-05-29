"""Tests for DeepSearch new-customer processing (Phase 10B)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from origenlab_email_pipeline.leads.new_customer_research import (
    BLOCKED_OUTPUT_FIELDS,
    CLASS_ALREADY_CONTACTED,
    CLASS_BOUNCED,
    CLASS_NET_NEW,
    CLASS_PUBLIC_TENDER,
    CLASS_RESEARCH_ONLY,
    CLASS_SAME_DOMAIN,
    CLASS_SUPPLIER_INTERNAL,
    CLASS_SUPPRESSED,
    ExclusionLists,
    classify_prospect,
    dedupe_prospects,
    load_exclusion_lists,
    process_deepsearch_prospects,
    run_process,
    write_all_outputs,
    write_top25_markdown,
)


def _write_exclusion_fixtures(excl_dir: Path) -> None:
    excl_dir.mkdir(parents=True, exist_ok=True)
    with (excl_dir / "contacted_exact_emails_for_exclusion.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "normalized_email",
                "domain",
                "organization_name",
                "last_contacted_at",
                "sent_count",
                "received_count",
                "recommended_status",
                "reason_codes",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "normalized_email": "known@buyer.test",
                "domain": "buyer.test",
                "organization_name": "Buyer",
                "last_contacted_at": "2026-01-01",
                "sent_count": "1",
                "received_count": "0",
                "recommended_status": "already_contacted",
                "reason_codes": "sent_history",
            }
        )
    with (excl_dir / "contacted_domains_for_exclusion.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "domain",
                "organization_name",
                "sent_count",
                "received_count",
                "unique_contacts",
                "bounced_count",
                "recommended_status",
                "reason_codes",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "domain": "buyer.test",
                "organization_name": "Buyer",
                "sent_count": "2",
                "received_count": "0",
                "unique_contacts": "2",
                "bounced_count": "0",
                "recommended_status": "already_contacted",
                "reason_codes": "sent_history",
            }
        )
        w.writerow(
            {
                "domain": "serva.de",
                "organization_name": "SERVA",
                "sent_count": "0",
                "received_count": "0",
                "unique_contacts": "1",
                "bounced_count": "0",
                "recommended_status": "supplier_do_not_market",
                "reason_codes": "supplier_domain",
            }
        )
    with (excl_dir / "bounced_emails_for_exclusion.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["normalized_email", "domain", "organization_name", "recommended_status", "reason_codes"],
        )
        w.writeheader()
        w.writerow(
            {
                "normalized_email": "bounced@bad.test",
                "domain": "bad.test",
                "organization_name": "Bad",
                "recommended_status": "bounced",
                "reason_codes": "bounce",
            }
        )
    with (excl_dir / "suppressed_contacts_for_exclusion.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["normalized_email", "domain", "organization_name", "suppressed_bool", "reason_codes"],
        )
        w.writeheader()
        w.writerow(
            {
                "normalized_email": "blocked@manual.test",
                "domain": "manual.test",
                "organization_name": "Manual",
                "suppressed_bool": "true",
                "reason_codes": "suppression",
            }
        )


def _deepsearch_row(**kwargs: str) -> dict[str, str]:
    base = {
        "organization_name": "Test Org",
        "contact_name": "",
        "email": "",
        "domain": "",
        "role_title": "",
        "sector": "Laboratorios privados",
        "region": "RM",
        "buyer_type": "laboratorio_privado",
        "likely_need": "QC",
        "product_angle": "centrífugas; balanzas",
        "evidence_url": "https://example.cl",
        "evidence_note": "evidencia",
        "source": "sitio_oficial",
        "priority_score": "80",
        "confidence": "alta",
        "recommended_message_angle": "",
        "risk_flags": "",
    }
    base.update(kwargs)
    if base.get("email"):
        from origenlab_email_pipeline.leads.new_customer_research import _norm_email

        base["email"] = _norm_email(base["email"]) or ""
    return base


@pytest.fixture
def excl(tmp_path: Path) -> ExclusionLists:
    d = tmp_path / "excl"
    _write_exclusion_fixtures(d)
    return load_exclusion_lists(d)


def test_exact_contacted_email_is_blocked(excl: ExclusionLists) -> None:
    row = _deepsearch_row(email="known@buyer.test", domain="buyer.test")
    cls, _ = classify_prospect(row, excl)
    assert cls == CLASS_ALREADY_CONTACTED


def test_contacted_exact_email_blocked_preserves_deepsearch_context(excl: ExclusionLists) -> None:
    """5M-style prospect: blocked for no-repeat but keeps operator context from DeepSearch."""
    row = _deepsearch_row(
        organization_name="5M S.A.",
        contact_name="Alejandra Cid",
        email="known@buyer.test",
        domain="buyer.test",
        sector="Laboratorios privados",
        region="Biobío / Tarapacá",
        buyer_type="laboratorio_acuicola",
        product_angle="incubadoras; balances; sample prep; QC",
        evidence_url="https://www.sernapesca.cl/app/uploads/2023/11/entidades_de_analisis_20190102.pdf",
        evidence_note="Entidad SERNAPESCA con contactos públicos",
        source="sernapesca_entidades_analisis",
        priority_score="82",
        confidence="alta",
    )
    processed = process_deepsearch_prospects([row], excl)
    assert len(processed) == 1
    p = processed[0]
    assert p.classification == CLASS_ALREADY_CONTACTED
    assert p.is_blocked
    assert p.input_priority_score == 82
    assert p.final_score == 0
    blocked = p.to_blocked_dict()
    assert blocked["sector"] == "Laboratorios privados"
    assert blocked["region"] == "Biobío / Tarapacá"
    assert blocked["buyer_type"] == "laboratorio_acuicola"
    assert "incubadoras" in blocked["product_angle"]
    assert blocked["evidence_url"].startswith("https://www.sernapesca.cl/")
    assert blocked["input_priority_score"] == "82"
    assert blocked["final_score"] == "0"
    assert blocked["recommended_next_action"] == "No contactar: ya contactado"


def test_bounced_email_is_blocked(excl: ExclusionLists) -> None:
    row = _deepsearch_row(email="bounced@bad.test", domain="bad.test")
    cls, _ = classify_prospect(row, excl)
    assert cls == CLASS_BOUNCED


def test_suppressed_email_is_blocked(excl: ExclusionLists) -> None:
    row = _deepsearch_row(email="blocked@manual.test", domain="manual.test")
    cls, _ = classify_prospect(row, excl)
    assert cls == CLASS_SUPPRESSED


def test_supplier_domain_blocked(excl: ExclusionLists) -> None:
    row = _deepsearch_row(email="sales@serva.de", domain="serva.de", buyer_type="laboratorio_privado")
    cls, _ = classify_prospect(row, excl)
    assert cls == CLASS_SUPPLIER_INTERNAL


def test_same_domain_becomes_same_domain_review(excl: ExclusionLists) -> None:
    row = _deepsearch_row(
        email="newperson@buyer.test",
        domain="buyer.test",
        organization_name="Buyer Two",
    )
    cls, _ = classify_prospect(row, excl)
    assert cls == CLASS_SAME_DOMAIN


def test_public_tender_without_email_is_public_tender_review(excl: ExclusionLists) -> None:
    row = _deepsearch_row(
        organization_name="UV VRII",
        domain="uv.cl",
        buyer_type="public_tender_universidad",
        email="",
        risk_flags="lead_status=public_tender_opportunity; sin_email_publico",
        source="mercado_publico",
        evidence_url="https://www.mercadopublico.cl/lic",
    )
    cls, _ = classify_prospect(row, excl)
    assert cls == CLASS_PUBLIC_TENDER


def test_high_fit_private_lab_with_email_is_net_new(excl: ExclusionLists) -> None:
    row = _deepsearch_row(
        organization_name="Pathovet Labs",
        email="lab@newlab.cl",
        domain="newlab.cl",
        contact_name="María Lab",
        buyer_type="laboratorio_acuicola",
        product_angle="centrífugas; homogenizadores",
        priority_score="92",
    )
    cls, _ = classify_prospect(row, excl)
    assert cls == CLASS_NET_NEW


def test_sin_email_publico_is_research_only(excl: ExclusionLists) -> None:
    row = _deepsearch_row(
        organization_name="BIOREN",
        domain="ufro.cl",
        email="",
        risk_flags="sin_email_publico",
        buyer_type="centro_investigacion",
    )
    cls, _ = classify_prospect(row, excl)
    assert cls == CLASS_RESEARCH_ONLY


def test_dedupe_keeps_higher_score(excl: ExclusionLists) -> None:
    rows = [
        _deepsearch_row(organization_name="Dup", email="dup@newco.cl", domain="newco.cl", priority_score="70"),
        _deepsearch_row(organization_name="Dup", email="dup@newco.cl", domain="newco.cl", priority_score="90"),
    ]
    processed = process_deepsearch_prospects(rows, excl)
    deduped = dedupe_prospects(processed)
    assert len(deduped) == 1
    assert deduped[0].input_priority_score == 90


def test_run_process_writes_output_files(tmp_path: Path) -> None:
    excl_dir = tmp_path / "excl"
    input_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    _write_exclusion_fixtures(excl_dir)
    input_dir.mkdir()
    with (input_dir / "deepsearch_test.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "organization_name",
                "contact_name",
                "email",
                "domain",
                "role_title",
                "sector",
                "region",
                "buyer_type",
                "likely_need",
                "product_angle",
                "evidence_url",
                "evidence_note",
                "source",
                "priority_score",
                "confidence",
                "recommended_message_angle",
                "risk_flags",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "organization_name": "New Lab",
                "contact_name": "Ana",
                "email": "ana@freshlab.cl",
                "domain": "freshlab.cl",
                "role_title": "Jefa lab",
                "sector": "Laboratorios privados",
                "region": "RM",
                "buyer_type": "laboratorio_privado",
                "likely_need": "QC",
                "product_angle": "centrífugas",
                "evidence_url": "https://freshlab.cl",
                "evidence_note": "web",
                "source": "sitio_oficial",
                "priority_score": "88",
                "confidence": "alta",
                "recommended_message_angle": "",
                "risk_flags": "",
            }
        )
        w.writerow(
            {
                "organization_name": "Old Contact",
                "contact_name": "",
                "email": "known@buyer.test",
                "domain": "buyer.test",
                "role_title": "",
                "sector": "Laboratorios privados",
                "region": "RM",
                "buyer_type": "laboratorio_privado",
                "likely_need": "",
                "product_angle": "",
                "evidence_url": "",
                "evidence_note": "",
                "source": "",
                "priority_score": "50",
                "confidence": "",
                "recommended_message_angle": "",
                "risk_flags": "",
            }
        )

    result = run_process(input_dir, excl_dir, out_dir)
    assert (out_dir / "new_customer_targets_review.csv").is_file()
    assert (out_dir / "new_customer_targets_blocked.csv").is_file()
    assert (out_dir / "new_customer_targets_top25.md").is_file()
    assert (out_dir / "new_customer_targets_summary.md").is_file()
    assert result.summary["blocked_rows"] >= 1
    assert result.summary["review_rows"] >= 1

    with (out_dir / "new_customer_targets_blocked.csv").open(encoding="utf-8", newline="") as f:
        blocked_rows = list(csv.DictReader(f))
    old_contact = next(r for r in blocked_rows if r["email"] == "known@buyer.test")
    assert old_contact["classification"] == CLASS_ALREADY_CONTACTED
    assert old_contact.get("sector") == "Laboratorios privados"
    assert old_contact.get("input_priority_score") == "50"
    assert old_contact["recommended_next_action"] == "No contactar: ya contactado"


def test_blocked_csv_writes_preservation_columns(tmp_path: Path, excl: ExclusionLists) -> None:
    row = _deepsearch_row(
        organization_name="5M S.A.",
        email="known@buyer.test",
        domain="buyer.test",
        sector="Laboratorios privados",
        product_angle="incubadoras",
        priority_score="82",
    )
    prospects = process_deepsearch_prospects([row], excl)
    out_dir = tmp_path / "out"
    write_all_outputs(prospects, {"classification_counts": {}}, out_dir)
    with (out_dir / "new_customer_targets_blocked.csv").open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == list(BLOCKED_OUTPUT_FIELDS)
        row_out = next(reader)
    assert row_out["sector"] == "Laboratorios privados"
    assert row_out["product_angle"] == "incubadoras"


def test_top25_markdown_has_sections(tmp_path: Path, excl: ExclusionLists) -> None:
    rows = [
        _deepsearch_row(
            organization_name="Lab Priv",
            email="a@newpriv.cl",
            domain="newpriv.cl",
            buyer_type="laboratorio_privado",
            priority_score="90",
        ),
        _deepsearch_row(
            organization_name="Tender UV",
            domain="uv.cl",
            buyer_type="public_tender_universidad",
            risk_flags="sin_email_publico",
            source="mercado_publico",
            evidence_url="https://www.mercadopublico.cl/x",
            priority_score="95",
        ),
        _deepsearch_row(
            organization_name="Uni Center",
            email="c@uniresearch.cl",
            domain="uniresearch.cl",
            sector="Universidades e investigación",
            buyer_type="centro_investigacion",
            priority_score="85",
        ),
    ]
    prospects = process_deepsearch_prospects(rows, excl)
    md = tmp_path / "top25.md"
    write_top25_markdown(prospects, md)
    text = md.read_text(encoding="utf-8")
    assert "laboratorios privados" in text
    assert "licitaciones" in text
    assert "universidades" in text
