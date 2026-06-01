"""Tests for Presentación OrigenLab quality pass."""

from __future__ import annotations

import csv
from pathlib import Path

from origenlab_email_pipeline.campaigns.presentacion_origenlab_quality import (
    run_presentacion_quality_pass,
    write_presentacion_quality_outputs,
)
from origenlab_email_pipeline.campaigns.presentacion_origenlab_quality_types import (
    BATCH_CSV_FIELDS,
    CLASS_FOLLOWUP_OLD,
    CLASS_PRESENTATION,
)
from origenlab_email_pipeline.campaigns.presentacion_origenlab_templates import (
    PRESENTACION_BATCH1_SUBJECT,
    template_presentacion_batch1_es,
)


def test_template_batch1_subject_and_body() -> None:
    subj, body = template_presentacion_batch1_es(contact_name="Ana")
    assert subj == PRESENTACION_BATCH1_SUBJECT
    assert "Estimado/a Ana," in body
    assert "mejora comercial Cyber de 5% a 10%" in body
    assert "Junto con saludar" in body


def test_quality_pass_dedupes_and_routes(tmp_path: Path) -> None:
    out = tmp_path / "current"
    out.mkdir()
    review_fields = [
        "email",
        "organization",
        "contact_name",
        "bucket",
        "reason_for_inclusion",
        "product_angle",
        "history_note",
        "suggested_subject",
        "suggested_message",
        "recommended_action",
        "priority_score",
        "exclusion_flags",
    ]
    with (out / "presentacion_origenlab_send_now_review.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=review_fields)
        w.writeheader()
        rows = [
            {
                "email": "erikcarrasco@analisismmoll.cl",
                "organization": "Analisismmoll",
                "contact_name": "",
                "bucket": "send_now_review",
                "reason_for_inclusion": "previo",
                "product_angle": "lab",
                "history_note": "Último asunto: Re: Cotización Osmomettro; envíos=4",
                "suggested_subject": "x",
                "suggested_message": "x",
                "recommended_action": "operator_review_before_send",
                "priority_score": "82",
                "exclusion_flags": "",
            },
            {
                "email": "ericpadilla@analisismmoll.cl",
                "organization": "Analisismmoll",
                "contact_name": "",
                "bucket": "send_now_review",
                "reason_for_inclusion": "previo",
                "product_angle": "lab",
                "history_note": "Último asunto: Re: Cotización Osmomettro; envíos=3",
                "suggested_subject": "x",
                "suggested_message": "x",
                "recommended_action": "operator_review_before_send",
                "priority_score": "79",
                "exclusion_flags": "",
            },
            {
                "email": "miguel.martinez@virbac.cl",
                "organization": "Virbac",
                "contact_name": "Miguel",
                "bucket": "send_now_review",
                "reason_for_inclusion": "previo",
                "product_angle": "lab",
                "history_note": "Último asunto: Re: Solicitud de cotización; envíos=4",
                "suggested_subject": "x",
                "suggested_message": "x",
                "recommended_action": "operator_review_before_send",
                "priority_score": "82",
                "exclusion_flags": "",
            },
            {
                "email": "lab@privado.cl",
                "organization": "Lab Privado SpA",
                "contact_name": "",
                "bucket": "send_now_review",
                "reason_for_inclusion": "previo",
                "product_angle": "lab",
                "history_note": "Último asunto: OrigenLab - Equipos para Laboratorio; envíos=2",
                "suggested_subject": "x",
                "suggested_message": "x",
                "recommended_action": "operator_review_before_send",
                "priority_score": "70",
                "exclusion_flags": "",
            },
        ]
        w.writerows(rows)

    uni_fields = [
        "normalized_email",
        "domain",
        "display_name",
        "organization_name",
        "sent_count",
        "received_count",
        "latest_subject_safe",
        "recommended_status",
    ]
    with (out / "contacted_universe_contacts.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=uni_fields)
        w.writeheader()
        w.writerow(
            {
                "normalized_email": "erikcarrasco@analisismmoll.cl",
                "domain": "analisismmoll.cl",
                "organization_name": "Analisismmoll",
                "latest_subject_safe": "Re: Cotización Osmomettro",
                "sent_count": "4",
                "received_count": "0",
                "recommended_status": "already_contacted",
            }
        )
        w.writerow(
            {
                "normalized_email": "lab@privado.cl",
                "domain": "privado.cl",
                "organization_name": "Lab Privado SpA",
                "latest_subject_safe": "OrigenLab - Equipos para Laboratorio",
                "sent_count": "2",
                "received_count": "0",
                "recommended_status": "already_contacted",
            }
        )

    (out / "presentacion_origenlab_same_domain_review.csv").write_text(
        "email,organization,contact_name,domain,product_angle,priority_score\n",
        encoding="utf-8",
    )

    result = run_presentacion_quality_pass(out)
    paths = write_presentacion_quality_outputs(result, out)

    assert paths["batch1"].is_file()
    assert any(r.email == "lab@privado.cl" for r in result.batch1)
    assert all(r.classification == CLASS_PRESENTATION for r in result.batch1)
    assert any(r.email == "erikcarrasco@analisismmoll.cl" for r in result.batch2)
    assert all(r.classification == CLASS_FOLLOWUP_OLD for r in result.batch2)
    assert any(r.email == "miguel.martinez@virbac.cl" for h in result.hold_personalized for r in [h])
    assert any(
        r.email == "ericpadilla@analisismmoll.cl" and r.reason_code == "domain_duplicate_secondary"
        for r in result.do_not_send
    )
    assert any(
        r.email == "miguel.martinez@virbac.cl" and r.reason_code == "hold_active_personalized"
        for r in result.do_not_send
    )

    with paths["batch1"].open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == list(BATCH_CSV_FIELDS)
