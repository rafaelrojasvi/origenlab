"""Tests for Presentación Batch 1 pre-send audit."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from origenlab_email_pipeline.campaigns.presentacion_origenlab_presend_audit import (
    DRY_RUN_FIELDS,
    INPUT_BATCH1,
    OUTPUT_DRY_RUN,
    OUTPUT_FINAL,
    audit_batch1_row,
    run_batch1_presend_audit,
    write_presend_audit_outputs,
)
from origenlab_email_pipeline.campaigns.presentacion_origenlab_quality_types import (
    CLASS_PRESENTATION,
    PresentacionBatchRow,
)
from origenlab_email_pipeline.campaigns.presentacion_origenlab_templates import (
    PRESENTACION_BATCH1_SUBJECT,
)
from origenlab_email_pipeline.leads.new_customer_research import ExclusionLists


def _minimal_gate():
    from origenlab_email_pipeline.candidate_export_gate import GateContext

    return GateContext(
        sent_recipient_norms=frozenset(),
        suppressed_norms=frozenset(),
        outreach_state_by_email={},
        supplier_domains=frozenset(),
        blocked_domains=frozenset({"origenlab.cl"}),
        suppressed_contact_domains=frozenset(),
    )


def _minimal_excl() -> ExclusionLists:
    return ExclusionLists(
        contacted_emails=frozenset(),
        contacted_domains=frozenset(),
        bounced_emails=frozenset({"bounce@bad.cl"}),
        bounced_domains=frozenset(),
        suppressed_emails=frozenset(),
        supplier_domains=frozenset(),
        internal_domains=frozenset(),
    )


def test_audit_fails_same_domain_and_cyber() -> None:
    row = PresentacionBatchRow(
        email="contacto@cslab.cl",
        domain="cslab.cl",
        organization="CSLAB",
        contact_name="",
        classification=CLASS_PRESENTATION,
        sector_guess="lab_privado_industria",
        reason_for_inclusion="test",
        history_note="",
        product_angle="",
        suggested_subject="",
        suggested_message="",
        recommended_action="",
    )
    findings = audit_batch1_row(
        row,
        gate_ctx=_minimal_gate(),
        excl=_minimal_excl(),
        cyberday_sent=frozenset({"cyber@lab.cl"}),
        hold_emails=frozenset(),
        same_domain_emails=frozenset({"kpena@cslab.cl"}),
        same_domain_domains=frozenset({"cslab.cl"}),
        batch2_emails=frozenset(),
    )
    codes = {f.code for f in findings if f.severity == "fail"}
    assert "same_domain_review_domain" in codes

    row2 = PresentacionBatchRow(
        email="cyber@lab.cl",
        domain="lab.cl",
        organization="X",
        contact_name="",
        classification=CLASS_PRESENTATION,
        sector_guess="",
        reason_for_inclusion="",
        history_note="",
        product_angle="",
        suggested_subject="",
        suggested_message="",
        recommended_action="",
    )
    findings2 = audit_batch1_row(
        row2,
        gate_ctx=_minimal_gate(),
        excl=_minimal_excl(),
        cyberday_sent=frozenset({"cyber@lab.cl"}),
        hold_emails=frozenset(),
        same_domain_emails=frozenset(),
        same_domain_domains=frozenset(),
        batch2_emails=frozenset(),
    )
    assert any(f.code == "cyberday_47" for f in findings2)


def test_presend_audit_removes_cslab_and_writes_outputs(tmp_path: Path) -> None:
    out = tmp_path / "current"
    out.mkdir()
    fields = [
        "email",
        "domain",
        "organization",
        "contact_name",
        "classification",
        "sector_guess",
        "reason_for_inclusion",
        "history_note",
        "product_angle",
        "suggested_subject",
        "suggested_message",
        "recommended_action",
        "priority_score",
        "dedupe_key",
        "primary_or_secondary",
    ]
    with (out / INPUT_BATCH1).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerow(
            {
                "email": "contacto@cslab.cl",
                "domain": "cslab.cl",
                "organization": "CSLAB",
                "classification": CLASS_PRESENTATION,
                "sector_guess": "lab_privado_industria",
                "reason_for_inclusion": "test",
                "history_note": "envíos=1",
                "product_angle": "lab",
                "suggested_subject": PRESENTACION_BATCH1_SUBJECT,
                "suggested_message": "body",
                "recommended_action": "operator_review_before_send",
                "priority_score": "100",
                "dedupe_key": "cslab",
                "primary_or_secondary": "primary",
            }
        )
        w.writerow(
            {
                "email": "lab@privado.cl",
                "domain": "privado.cl",
                "organization": "Lab Privado",
                "classification": CLASS_PRESENTATION,
                "sector_guess": "lab_privado_industria",
                "reason_for_inclusion": "test",
                "history_note": "envíos=1",
                "product_angle": "lab",
                "suggested_subject": PRESENTACION_BATCH1_SUBJECT,
                "suggested_message": "body",
                "recommended_action": "operator_review_before_send",
                "priority_score": "90",
                "dedupe_key": "privado",
                "primary_or_secondary": "primary",
            }
        )

    (out / "presentacion_hold_active_personalized.csv").write_text(
        "email,domain,organization\n", encoding="utf-8"
    )
    with (out / "presentacion_same_domain_review_curated.csv").open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["email", "domain", "organization", "contact_name", "review_note"]
        )
        w.writeheader()
        w.writerow(
            {
                "email": "kpena@cslab.cl",
                "domain": "cslab.cl",
                "organization": "CSLAB",
                "contact_name": "Karina",
                "review_note": "same domain",
            }
        )
    (out / "presentacion_batch2_followup_old_25.csv").write_text(
        "email,domain\n", encoding="utf-8"
    )
    (out / "cyber_production_send_log.json").write_text(json.dumps({"sent": []}), encoding="utf-8")
    for fn in (
        "bounced_emails_for_exclusion.csv",
        "suppressed_contacts_for_exclusion.csv",
        "contacted_exact_emails_for_exclusion.csv",
        "contacted_domains_for_exclusion.csv",
    ):
        (out / fn).write_text("normalized_email\n", encoding="utf-8")

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE contact_email_suppression (email TEXT PRIMARY KEY, suppression_reason_code TEXT);
        CREATE TABLE outreach_contact_state (contact_email_norm TEXT PRIMARY KEY, state TEXT);
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY, date_iso TEXT, subject TEXT, sender TEXT,
          recipients TEXT, source_file TEXT, folder TEXT
        );
        """
    )
    try:
        result = run_batch1_presend_audit(
            conn, out, gmail_user="ops@origenlab.cl", sent_folders=("Sent",)
        )
    finally:
        conn.close()

    assert any(r["email"] == "contacto@cslab.cl" for r in result.removed)
    assert any(r.email == "lab@privado.cl" for r in result.approved)
    paths = write_presend_audit_outputs(result, out)
    assert paths["final"].is_file()
    with paths["dry_run"].open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == list(DRY_RUN_FIELDS)
        rows = list(reader)
        assert rows[0]["subject"] == PRESENTACION_BATCH1_SUBJECT
