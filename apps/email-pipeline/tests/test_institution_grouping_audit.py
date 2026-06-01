"""Tests for read-only institution grouping audit."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.business_mart_schema import BUSINESS_MART_SCHEMA_SQL
from origenlab_email_pipeline.contact_domain_suppression import (
    ensure_contact_domain_suppression_table,
)
from origenlab_email_pipeline.contact_email_suppression import (
    ensure_contact_email_suppression_table,
    upsert_contact_email_suppression,
    validate_contact_email_suppression_payload,
)
from origenlab_email_pipeline.lead_research.institution_grouping_audit import (
    connect_sqlite_readonly,
    run_institution_grouping_audit,
)
from origenlab_email_pipeline.outreach_contact_state import (
    ensure_outreach_contact_state_table,
    upsert_outreach_contact_state,
    validate_outreach_contact_state_payload,
)

_FIXED_AT = "2026-06-01T12:00:00+00:00"


def _insert_contact(
    conn: sqlite3.Connection,
    *,
    email: str,
    domain: str,
    org: str,
    outbound: int = 0,
    inbound: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO contact_master (
          email, contact_name_best, domain, organization_name_guess,
          organization_type_guess, first_seen_at, last_seen_at,
          total_emails, inbound_emails, outbound_emails,
          quote_email_count, invoice_email_count, purchase_email_count,
          business_doc_email_count, quote_doc_count, invoice_doc_count,
          top_equipment_tags, confidence_score
        ) VALUES (?, ?, ?, ?, '', ?, ?, 1, ?, ?, 0,0,0,0,0,0, '', 0.5)
        """,
        (email, "Contact", domain, org, _FIXED_AT, _FIXED_AT, inbound, outbound),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO organization_master (
          domain, organization_name_guess, organization_type_guess,
          first_seen_at, last_seen_at, total_emails, total_contacts,
          quote_email_count, invoice_email_count, purchase_email_count,
          business_doc_email_count, quote_doc_count, invoice_doc_count,
          top_equipment_tags, key_contacts
        ) VALUES (?, ?, '', ?, ?, 1, 1, 0,0,0,0,0,0, '', '')
        """,
        (domain, org, _FIXED_AT, _FIXED_AT),
    )


@pytest.fixture
def grouping_db(tmp_path: Path) -> Path:
    db = tmp_path / "grouping.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(BUSINESS_MART_SCHEMA_SQL)
    conn.execute(
        """
        CREATE TABLE supplier_master (
          id INTEGER PRIMARY KEY,
          domain_norm TEXT,
          is_exclusion INTEGER
        )
        """
    )
    ensure_contact_email_suppression_table(conn)
    ensure_contact_domain_suppression_table(conn)
    ensure_outreach_contact_state_table(conn)

    _insert_contact(
        conn,
        email="alice@acme-lab.cl",
        domain="acme-lab.cl",
        org="Acme Laboratorio",
        outbound=10,
        inbound=2,
    )
    _insert_contact(
        conn,
        email="bob@acme-lab.cl",
        domain="acme-lab.cl",
        org="Acme Laboratorio",
        outbound=1,
    )

    _insert_contact(
        conn,
        email="contacto@buyer.cl",
        domain="buyer.cl",
        org="Comprador SA",
        outbound=0,
    )
    _insert_contact(
        conn,
        email="ventas@foo.cl",
        domain="foo.cl",
        org="Foo Labs Chile",
        outbound=0,
    )
    _insert_contact(
        conn,
        email="user@bar.cl",
        domain="bar.cl",
        org="Foo Labs Chile",
        outbound=0,
    )

    conn.execute(
        "INSERT INTO supplier_master (domain_norm, is_exclusion) VALUES (?, 1)",
        ("supplier-tools.cl",),
    )
    _insert_contact(
        conn,
        email="sales@supplier-tools.cl",
        domain="supplier-tools.cl",
        org="Supplier Tools Inc",
        outbound=0,
    )

    upsert_contact_email_suppression(
        conn,
        payload=validate_contact_email_suppression_payload(
            email="bounced@client.cl",
            suppression_reason_code="bounce_no_such_user",
            suppression_reason_text="test",
            suppression_source="test",
            last_bounced_at=_FIXED_AT,
            updated_by="test",
        ),
    )
    _insert_contact(
        conn,
        email="bounced@client.cl",
        domain="client.cl",
        org="Cliente SpA",
        outbound=2,
    )
    upsert_outreach_contact_state(
        conn,
        payload=validate_outreach_contact_state_payload(
            contact_email="contacted@client.cl",
            state="contacted",
            source="test",
        ),
    )
    _insert_contact(
        conn,
        email="contacted@client.cl",
        domain="client.cl",
        org="Cliente SpA",
        outbound=5,
    )

    conn.commit()
    conn.close()
    return db


def test_clean_domain_group_and_counts(grouping_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    conn = connect_sqlite_readonly(grouping_db)
    try:
        result = run_institution_grouping_audit(
            conn,
            sqlite_path=grouping_db,
            out_dir=out,
            generated_at=_FIXED_AT,
        )
    finally:
        conn.close()

    assert result.summary["total_contacts"] == 8
    assert result.summary["high_confidence_groups_count"] >= 1
    assert (out / "organization_grouping_summary.json").is_file()
    inv = (out / "domain_org_inventory.csv").read_text(encoding="utf-8")
    assert "acme-lab.cl" in inv


def test_org_name_collision_across_domains(grouping_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "out2"
    conn = connect_sqlite_readonly(grouping_db)
    try:
        result = run_institution_grouping_audit(
            conn, sqlite_path=grouping_db, out_dir=out, generated_at=_FIXED_AT
        )
    finally:
        conn.close()

    collision_text = (out / "org_name_collision_review.csv").read_text(encoding="utf-8")
    assert "org_name_multiple_domains" in collision_text
    assert "foo.cl" in collision_text or "bar.cl" in collision_text
    assert result.summary["org_names_with_multiple_domains"] >= 1


def test_generic_mailbox_and_supplier_rows(grouping_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "out3"
    conn = connect_sqlite_readonly(grouping_db)
    try:
        run_institution_grouping_audit(conn, sqlite_path=grouping_db, out_dir=out, generated_at=_FIXED_AT)
    finally:
        conn.close()

    generic = (out / "generic_mailbox_review.csv").read_text(encoding="utf-8")
    assert "contacto@buyer.cl" in generic
    assert "ventas@foo.cl" in generic

    supplier = (out / "supplier_vendor_review.csv").read_text(encoding="utf-8")
    assert "supplier-tools.cl" in supplier


def test_suppressed_and_contacted_domains_reflected(grouping_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "out4"
    conn = connect_sqlite_readonly(grouping_db)
    try:
        result = run_institution_grouping_audit(
            conn, sqlite_path=grouping_db, out_dir=out, generated_at=_FIXED_AT
        )
    finally:
        conn.close()

    inv = (out / "domain_org_inventory.csv").read_text(encoding="utf-8")
    assert "client.cl" in inv
    assert result.summary["contacted_domains_count"] >= 1


def test_no_db_writes(grouping_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "out5"
    conn = connect_sqlite_readonly(grouping_db)
    before = conn.execute("SELECT COUNT(*) FROM contact_master").fetchone()[0]
    try:
        run_institution_grouping_audit(conn, sqlite_path=grouping_db, out_dir=out, generated_at=_FIXED_AT)
        after = conn.execute("SELECT COUNT(*) FROM contact_master").fetchone()[0]
    finally:
        conn.close()
    assert before == after


def test_deterministic_outputs(grouping_db: Path, tmp_path: Path) -> None:
    for name in ("a", "b"):
        out = tmp_path / name
        conn = connect_sqlite_readonly(grouping_db)
        try:
            run_institution_grouping_audit(
                conn, sqlite_path=grouping_db, out_dir=out, generated_at=_FIXED_AT
            )
        finally:
            conn.close()

    assert (
        (tmp_path / "a" / "organization_grouping_summary.json").read_text(encoding="utf-8")
        == (tmp_path / "b" / "organization_grouping_summary.json").read_text(encoding="utf-8")
    )


def _run_audit(db: Path, out: Path) -> dict:
    conn = connect_sqlite_readonly(db)
    try:
        result = run_institution_grouping_audit(
            conn, sqlite_path=db, out_dir=out, generated_at=_FIXED_AT
        )
    finally:
        conn.close()
    return result.summary


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture
def noise_filter_db(tmp_path: Path) -> Path:
    db = tmp_path / "noise.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(BUSINESS_MART_SCHEMA_SQL)
    conn.execute(
        "CREATE TABLE supplier_master (id INTEGER PRIMARY KEY, domain_norm TEXT, is_exclusion INTEGER)"
    )

    for dom in (
        "com.solostocks.com",
        "mailer.solostocks.com",
        "mkt.solostocks.com",
        "solostocks.cl",
    ):
        _insert_contact(conn, email=f"x@{dom}", domain=dom, org="SoloStocks", inbound=5)

    for dom, org in (
        ("agrosuper.onmicrosoft.com", "onmicrosoft"),
        ("udeconce.onmicrosoft.com", "onmicrosoft"),
    ):
        _insert_contact(conn, email=f"a@{dom}", domain=dom, org=org, inbound=1)

    conn.execute(
        "INSERT INTO supplier_master (domain_norm, is_exclusion) VALUES (?, 1)",
        ("vendor-lab.com",),
    )
    _insert_contact(
        conn,
        email="sales@vendor-lab.com",
        domain="vendor-lab.com",
        org="Vendor Lab Inc",
        outbound=2,
    )

    _insert_contact(
        conn,
        email="lab@bureauveritas.cl",
        domain="bureauveritas.cl",
        org="Bureau Veritas",
        outbound=3,
    )
    _insert_contact(
        conn,
        email="info@bureauveritas.com",
        domain="bureauveritas.com",
        org="Bureau Veritas",
        outbound=1,
    )

    _insert_contact(
        conn,
        email="nominas@bancoestado.cl",
        domain="bancoestado.cl",
        org="BancoEstado",
        inbound=2,
    )
    _insert_contact(
        conn,
        email="x@m5.bancoestado.site",
        domain="m5.bancoestado.site",
        org="BancoEstado",
        inbound=1,
    )

    conn.commit()
    conn.close()
    return db


def test_solostocks_excluded_from_alias_seeds(noise_filter_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "noise"
    summary = _run_audit(noise_filter_db, out)
    seeds = _read_csv_rows(out / "alias_seed_candidates.csv")
    assert not any("solostocks" in (r.get("alias_name") or "") for r in seeds)
    collisions = _read_csv_rows(out / "org_name_collision_review.csv")
    solo = [r for r in collisions if "solostocks" in (r.get("org_names") or "")]
    assert solo
    assert all(r.get("do_not_promote_to_institution") == "True" for r in solo)
    assert summary["alias_seed_candidates_count"] >= 0


def test_onmicrosoft_collision_not_alias_seed(noise_filter_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "ms"
    _run_audit(noise_filter_db, out)
    seeds = _read_csv_rows(out / "alias_seed_candidates.csv")
    assert not any("onmicrosoft" in (r.get("alias_name") or "") for r in seeds)
    collisions = _read_csv_rows(out / "org_name_collision_review.csv")
    ms = [r for r in collisions if r.get("org_names") == "onmicrosoft"]
    assert ms
    assert ms[0]["collision_category"] in ("marketplace_platform", "platform_or_marketing", "noise_token")


def test_supplier_stays_vendor_not_institution_candidate(noise_filter_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "sup"
    _run_audit(noise_filter_db, out)
    inv = _read_csv_rows(out / "domain_org_inventory.csv")
    vendor = next(r for r in inv if r["domain"] == "vendor-lab.com")
    assert vendor["promotion_bucket"] == "supplier_vendor"
    assert vendor["do_not_promote_to_institution"] == "True"
    candidates = _read_csv_rows(out / "institution_candidates.csv")
    cand = next(r for r in candidates if r["domains"] == "vendor-lab.com")
    assert cand["confidence"] == "low"
    assert "do_not_promote" in cand["review_reason"]


def test_bureauveritas_alias_seed_candidate(noise_filter_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "bv"
    summary = _run_audit(noise_filter_db, out)
    seeds = _read_csv_rows(out / "alias_seed_candidates.csv")
    assert any("bureau" in (r.get("alias_name") or "") for r in seeds)
    assert summary["alias_seed_candidates_count"] >= 1


def test_bancoestado_manual_review_collision(noise_filter_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "be"
    _run_audit(noise_filter_db, out)
    collisions = _read_csv_rows(out / "org_name_collision_review.csv")
    be = [r for r in collisions if "bancoestado" in (r.get("org_names") or "")]
    assert be
    assert be[0]["collision_category"] == "manual_review"
    assert be[0]["recommended_action"] == "manual_review"
    seeds = _read_csv_rows(out / "alias_seed_candidates.csv")
    assert not any("bancoestado" in (r.get("alias_name") or "") for r in seeds)
