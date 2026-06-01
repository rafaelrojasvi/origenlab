"""Tests for legacy 2016–2019 contact workbook review pipeline."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.lead_research.legacy_contacts_2016_2019 import (
    CLASSIFICATION_LEGACY,
    DATASET_LABEL_LEGACY,
    SOURCE_TYPE_LEGACY,
    STATUS_ALREADY_CONTACTED_EXACT,
    STATUS_BOUNCED_SUPPRESSED,
    STATUS_DUP_DOMAIN_SECONDARY,
    STATUS_DUP_EMAIL,
    STATUS_INVALID_EMAIL,
    STATUS_POSSIBLE_BUYER,
    LegacyNormalizedRow,
    LegacyRawRow,
    LegacySafetyContext,
    apply_duplicate_labels,
    bucket_legacy_rows,
    classify_legacy_rows,
    legacy_row_to_lead_research_payload,
    load_legacy_safety_context,
    merge_legacy_possible_buyers_to_lead_research,
    normalize_legacy_raw_rows,
    split_emails_from_cell,
    write_legacy_review_outputs,
)
from origenlab_email_pipeline.lead_research.lead_research_schema import ensure_lead_research_tables
from origenlab_email_pipeline.leads.new_customer_research import load_exclusion_lists


def _excl_dir(tmp_path: Path) -> Path:
    d = tmp_path / "excl"
    d.mkdir()
    (d / "contacted_exact_emails_for_exclusion.csv").write_text(
        "normalized_email\nknown@labcliente.cl\n",
        encoding="utf-8",
    )
    (d / "contacted_domains_for_exclusion.csv").write_text(
        "domain,sent_count,recommended_status,supplier_bool,internal_bool,reason_codes\n"
        "historico.cl,2,already_contacted,false,false,\n",
        encoding="utf-8",
    )
    (d / "bounced_emails_for_exclusion.csv").write_text(
        "normalized_email\nbounced@rebote.cl\n",
        encoding="utf-8",
    )
    (d / "suppressed_contacts_for_exclusion.csv").write_text(
        "normalized_email\nsuppressed@hold.cl\n",
        encoding="utf-8",
    )
    return d


def _ctx_from_excl_dir(tmp_path: Path) -> LegacySafetyContext:
    excl = load_exclusion_lists(_excl_dir(tmp_path))
    return LegacySafetyContext(
        exclusion=excl,
        sqlite_suppressed_emails=frozenset(),
        sqlite_suppressed_domains=frozenset(),
        gmail_sent_emails=frozenset(),
        lead_research_emails=frozenset(),
        lead_research_domains=frozenset(),
        supplier_domains_sqlite=frozenset(),
    )


def test_split_multiple_emails_in_one_cell() -> None:
    found = split_emails_from_cell("a@x.cl; ventas@y.cl / info@z.com")
    assert found == ["a@x.cl", "ventas@y.cl", "info@z.com"]


def test_invalid_email_classified(tmp_path: Path) -> None:
    rows = [
        LegacyNormalizedRow(
            email="notld@nodomain",
            domain="nodomain",
            organization="Lab",
            contact_name="X",
            phone="",
            region="",
            source_sheet="Sheet1",
            source_row=2,
            original_notes="",
            product_angle="",
            category="",
        )
    ]
    classify_legacy_rows(rows, _ctx_from_excl_dir(tmp_path))
    assert rows[0].normalized_status == STATUS_INVALID_EMAIL


def test_duplicate_email_and_domain_secondary() -> None:
    rows = [
        LegacyNormalizedRow(
            email="a@dup.cl",
            domain="dup.cl",
            organization="A",
            contact_name="",
            phone="",
            region="",
            source_sheet="S",
            source_row=1,
            original_notes="",
            product_angle="",
            category="",
            normalized_status=STATUS_POSSIBLE_BUYER,
        ),
        LegacyNormalizedRow(
            email="b@dup.cl",
            domain="dup.cl",
            organization="B",
            contact_name="",
            phone="",
            region="",
            source_sheet="S",
            source_row=2,
            original_notes="",
            product_angle="",
            category="",
            normalized_status=STATUS_POSSIBLE_BUYER,
        ),
        LegacyNormalizedRow(
            email="a@dup.cl",
            domain="dup.cl",
            organization="C",
            contact_name="",
            phone="",
            region="",
            source_sheet="S",
            source_row=3,
            original_notes="",
            product_angle="",
            category="",
            normalized_status=STATUS_POSSIBLE_BUYER,
        ),
    ]
    apply_duplicate_labels(rows)
    assert rows[0].normalized_status == STATUS_POSSIBLE_BUYER
    assert rows[1].normalized_status == STATUS_DUP_DOMAIN_SECONDARY
    assert rows[2].normalized_status == STATUS_DUP_EMAIL


def test_suppression_and_contacted_matching(tmp_path: Path) -> None:
    raw = [
        LegacyRawRow("S", 2, {"Correo": "known@labcliente.cl", "Empresa ": "L"}),
        LegacyRawRow("S", 3, {"Correo": "bounced@rebote.cl", "Empresa ": "L"}),
        LegacyRawRow("S", 4, {"Correo": "suppressed@hold.cl", "Empresa ": "L"}),
        LegacyRawRow("S", 5, {"Correo": "nuevo@historico.cl", "Empresa ": "L"}),
        LegacyRawRow("S", 6, {"Correo": "fresh@nuevo-lab.cl", "Empresa ": "L", "Contacto": "Ana"}),
    ]
    rows = normalize_legacy_raw_rows(raw)
    classify_legacy_rows(rows, _ctx_from_excl_dir(tmp_path))
    by_email = {r.email: r.normalized_status for r in rows}
    assert by_email["known@labcliente.cl"] == STATUS_ALREADY_CONTACTED_EXACT
    assert by_email["bounced@rebote.cl"] == STATUS_BOUNCED_SUPPRESSED
    assert by_email["suppressed@hold.cl"] == STATUS_BOUNCED_SUPPRESSED
    assert by_email["nuevo@historico.cl"] == "domain_has_history"
    assert by_email["fresh@nuevo-lab.cl"] == STATUS_POSSIBLE_BUYER


def test_domain_history_classification(tmp_path: Path) -> None:
    raw = [LegacyRawRow("S", 2, {"Correo": "persona@historico.cl", "Empresa ": "Lab"})]
    rows = normalize_legacy_raw_rows(raw)
    classify_legacy_rows(rows, _ctx_from_excl_dir(tmp_path))
    assert rows[0].normalized_status == "domain_has_history"


def test_legacy_payload_not_net_new_safe() -> None:
    row = LegacyNormalizedRow(
        email="buyer@fresh-lab.cl",
        domain="fresh-lab.cl",
        organization="Fresh Lab",
        contact_name="Pat",
        phone="",
        region="RM",
        source_sheet="Sheet1",
        source_row=10,
        original_notes="",
        product_angle="termobalanza",
        category="",
        normalized_status=STATUS_POSSIBLE_BUYER,
    )
    payload = legacy_row_to_lead_research_payload(row)
    assert payload is not None
    assert payload["classification"] == CLASSIFICATION_LEGACY
    assert payload["classification"] != "net_new_safe_review"
    assert payload["status"] == "review_legacy_contact"
    assert payload["source_type"] == SOURCE_TYPE_LEGACY
    assert payload["dataset_label"] == DATASET_LABEL_LEGACY
    assert payload["is_blocked"] == 0


def test_possible_buyers_csv_excludes_bounced(tmp_path: Path) -> None:
    from origenlab_email_pipeline.lead_research.legacy_contacts_2016_2019 import (
        LegacyReviewBuildResult,
        WorkbookInspection,
        build_summary,
    )

    rows = [
        LegacyNormalizedRow(
            email="ok@fresh.cl",
            domain="fresh.cl",
            organization="O",
            contact_name="",
            phone="",
            region="",
            source_sheet="S",
            source_row=1,
            original_notes="",
            product_angle="",
            category="",
            normalized_status=STATUS_POSSIBLE_BUYER,
        ),
        LegacyNormalizedRow(
            email="bounced@rebote.cl",
            domain="rebote.cl",
            organization="B",
            contact_name="",
            phone="",
            region="",
            source_sheet="S",
            source_row=2,
            original_notes="",
            product_angle="",
            category="",
            normalized_status=STATUS_BOUNCED_SUPPRESSED,
        ),
    ]
    buckets = bucket_legacy_rows(rows)
    inspection = WorkbookInspection(path="test.xls", sheets=[])
    result = LegacyReviewBuildResult(
        inspection=inspection,
        normalized_rows=rows,
        summary=build_summary(inspection, rows, buckets),
        buckets=buckets,
    )
    paths = write_legacy_review_outputs(result, tmp_path / "out")
    with paths["possible_buyers"].open(encoding="utf-8") as f:
        buyers = list(csv.DictReader(f))
    emails = {r["email"] for r in buyers}
    assert "ok@fresh.cl" in emails
    assert "bounced@rebote.cl" not in emails


def test_merge_skips_non_buyers_and_sets_source_type(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    ensure_lead_research_tables(conn)
    rows = [
        LegacyNormalizedRow(
            email="merge@fresh.cl",
            domain="fresh.cl",
            organization="M",
            contact_name="",
            phone="",
            region="",
            source_sheet="S",
            source_row=1,
            original_notes="",
            product_angle="",
            category="",
            normalized_status=STATUS_POSSIBLE_BUYER,
        ),
        LegacyNormalizedRow(
            email="bounced@rebote.cl",
            domain="rebote.cl",
            organization="B",
            contact_name="",
            phone="",
            region="",
            source_sheet="S",
            source_row=2,
            original_notes="",
            product_angle="",
            category="",
            normalized_status=STATUS_BOUNCED_SUPPRESSED,
        ),
    ]
    stats = merge_legacy_possible_buyers_to_lead_research(conn, rows, dry_run=False)
    assert stats["inserted"] == 1
    row = conn.execute(
        "SELECT source_type, classification, status FROM lead_research_prospect WHERE email = ?",
        ("merge@fresh.cl",),
    ).fetchone()
    assert row[0] == SOURCE_TYPE_LEGACY
    assert row[1] == CLASSIFICATION_LEGACY
    assert row[2] == "review_legacy_contact"
    assert conn.execute(
        "SELECT COUNT(*) FROM lead_research_prospect WHERE classification = 'net_new_safe_review'"
    ).fetchone()[0] == 0
    conn.close()


def test_load_legacy_safety_context_sqlite_suppression(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE contact_email_suppression (
          email TEXT PRIMARY KEY, reason TEXT, source TEXT, created_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO contact_email_suppression VALUES (?,?,?,?)",
        ("sqlite@sup.cl", "bounce", "test", "2026-01-01"),
    )
    conn.commit()
    ctx = load_legacy_safety_context(conn, _excl_dir(tmp_path))
    rows = normalize_legacy_raw_rows(
        [LegacyRawRow("S", 2, {"Correo": "sqlite@sup.cl", "Empresa ": "L"})]
    )
    classify_legacy_rows(rows, ctx)
    assert rows[0].normalized_status == STATUS_BOUNCED_SUPPRESSED
    conn.close()


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("xlrd"),
    reason="xlrd not installed",
)
def test_read_real_workbook_schema_if_present() -> None:
    path = Path.home() / "data/origenlab-local-assets/legacy-contacts/Base de datos 2016-2019.xls"
    if not path.is_file():
        pytest.skip("legacy workbook not on this machine")
    from origenlab_email_pipeline.lead_research.legacy_contacts_2016_2019 import (
        read_legacy_workbook_xls,
    )

    raw, inspection = read_legacy_workbook_xls(path)
    assert inspection.sheets[0]["row_count"] > 1000
    assert len(raw) > 1000
