"""Tests for read-only Presentación OrigenLab review builder."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from origenlab_email_pipeline.campaigns.presentacion_origenlab_campaign import (
    build_presentacion_origenlab_review,
    is_presentacion_hold_active_case,
    load_cyberday_sent_emails,
    write_presentacion_outputs,
)
from origenlab_email_pipeline.campaigns.presentacion_origenlab_types import (
    ACTION_HOLD_ACTIVE,
    ACTION_REVIEW_HISTORY_ONLY,
    ACTION_SEND_NOW_REVIEW,
    BUCKET_HOLD_ACTIVE,
    REVIEW_CSV_FIELDS,
)


def test_load_cyberday_sent_emails(tmp_path: Path) -> None:
    log = {
        "sent": [
            {"email": "a@lab.cl"},
            {"email": "  B@Lab.CL "},
        ]
    }
    p = tmp_path / "cyber_production_send_log.json"
    p.write_text(json.dumps(log), encoding="utf-8")
    assert load_cyberday_sent_emails(p) == frozenset({"a@lab.cl", "b@lab.cl"})


def test_hold_active_ongo_crtop_extensions() -> None:
    hold, reason = is_presentacion_hold_active_case(
        "hola@ongo.cl", organization="ONGO", domain="ongo.cl"
    )
    assert hold is True
    assert "ongo" in reason.lower()

    hold2, _ = is_presentacion_hold_active_case(
        "ventas@crtopmachine.com", organization="CRTOP", domain="crtopmachine.com"
    )
    assert hold2 is True

    hold3, _ = is_presentacion_hold_active_case(
        "marcos.a@hielscher.com", organization="Hielscher", domain="hielscher.com"
    )
    assert hold3 is True


def test_build_presentacion_excludes_cyberday_and_routes_buckets(tmp_path: Path) -> None:
    out = tmp_path / "current"
    out.mkdir()
    cyber_log = {"sent": [{"email": "cyber@lab.cl"}]}
    (out / "cyber_production_send_log.json").write_text(
        json.dumps(cyber_log), encoding="utf-8"
    )
    (out / "bounced_emails_for_exclusion.csv").write_text(
        "normalized_email\nbounce@bad.cl\n", encoding="utf-8"
    )
    (out / "suppressed_contacts_for_exclusion.csv").write_text(
        "normalized_email\n", encoding="utf-8"
    )
    (out / "contacted_exact_emails_for_exclusion.csv").write_text(
        "normalized_email\n", encoding="utf-8"
    )
    (out / "contacted_domains_for_exclusion.csv").write_text(
        "domain,sent_count,recommended_status,supplier_bool,internal_bool,reason_codes\n",
        encoding="utf-8",
    )
    with (out / "contacted_universe_contacts.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "normalized_email",
                "domain",
                "display_name",
                "organization_name",
                "first_contacted_at",
                "last_contacted_at",
                "sent_count",
                "received_count",
                "replied_bool",
                "bounced_bool",
                "suppressed_bool",
                "outreach_state",
                "role_guess",
                "buyer_type_guess",
                "product_interest_guess",
                "latest_subject_safe",
                "recommended_status",
                "reason_codes",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "normalized_email": "leftover@uni.cl",
                "domain": "uni.cl",
                "display_name": "Ana",
                "organization_name": "Universidad Test",
                "sent_count": "2",
                "received_count": "0",
                "bounced_bool": "false",
                "suppressed_bool": "false",
                "latest_subject_safe": "OrigenLab - Equipos para Laboratorio",
                "recommended_status": "already_contacted",
            }
        )
        w.writerow(
            {
                "normalized_email": "cyber@lab.cl",
                "domain": "lab.cl",
                "organization_name": "Cyber Co",
                "sent_count": "1",
                "received_count": "0",
                "bounced_bool": "false",
                "suppressed_bool": "false",
                "latest_subject_safe": "CYBERDAY — equipos",
                "recommended_status": "already_contacted",
            }
        )
        w.writerow(
            {
                "normalized_email": "hola@ongo.cl",
                "domain": "ongo.cl",
                "organization_name": "ONGO",
                "sent_count": "2",
                "received_count": "0",
                "bounced_bool": "false",
                "suppressed_bool": "false",
                "latest_subject_safe": "Cotización Sonicador",
                "recommended_status": "already_contacted",
            }
        )
    with (out / "new_customer_targets_review.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "organization_name",
                "contact_name",
                "email",
                "domain",
                "classification",
                "spanish_message_angle",
                "product_angle",
                "block_or_review_reason",
                "final_score",
                "input_priority_score",
                "evidence_note",
                "evidence_url",
                "risk_flags",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "organization_name": "CSLAB",
                "contact_name": "Karina",
                "email": "kpena@cslab.cl",
                "domain": "cslab.cl",
                "classification": "same_domain_contacted_review",
                "product_angle": "incubadoras",
                "block_or_review_reason": "mismo_dominio_ya_contactado",
                "final_score": "100",
            }
        )
        w.writerow(
            {
                "organization_name": "CeBiB",
                "contact_name": "",
                "email": "",
                "domain": "cebib.cl",
                "classification": "research_only_contact_needed",
                "product_angle": "centrífugas",
                "block_or_review_reason": "falta_email_directo",
                "final_score": "98",
            }
        )
    (out / "cyber_expanded_previous_buyers_review.csv").write_text(
        "email,organization,contact_name,domain,reason,latest_contact_date\n",
        encoding="utf-8",
    )

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE contact_email_suppression (email TEXT PRIMARY KEY, suppression_reason_code TEXT);
        CREATE TABLE outreach_contact_state (
          contact_email_norm TEXT PRIMARY KEY, state TEXT
        );
        CREATE TABLE emails (
          id INTEGER PRIMARY KEY, date_iso TEXT, subject TEXT, sender TEXT,
          recipients TEXT, source_file TEXT, folder TEXT
        );
        """
    )
    try:
        result = build_presentacion_origenlab_review(
            conn,
            out_dir=out,
            gmail_user="ops@origenlab.cl",
            sent_folders=("Sent",),
        )
    finally:
        conn.close()

    assert len(result.send_now) == 1
    assert result.send_now[0].email == "leftover@uni.cl"
    assert result.send_now[0].recommended_action == ACTION_SEND_NOW_REVIEW
    assert not any(r.email == "cyber@lab.cl" for r in result.send_now)
    assert any(
        r.email == "hola@ongo.cl" and r.bucket == BUCKET_HOLD_ACTIVE for r in result.hold_active
    )
    assert len(result.same_domain) == 1
    assert result.same_domain[0].recommended_action == ACTION_REVIEW_HISTORY_ONLY
    assert len(result.missing_email) == 1
    assert result.missing_email[0].organization == "CeBiB"

    paths = write_presentacion_outputs(result, out)
    assert paths["send_now"].is_file()
    with paths["send_now"].open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == list(REVIEW_CSV_FIELDS)
