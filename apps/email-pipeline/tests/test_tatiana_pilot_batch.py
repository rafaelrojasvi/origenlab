from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from origenlab_email_pipeline.config import Settings
from origenlab_email_pipeline.tatiana_copilot.pilot_batch import (
    resolve_pilot_generator,
    run_pilot_batch,
)
from origenlab_email_pipeline.tatiana_copilot.pilot_loader import load_pilot_input
from origenlab_email_pipeline.tatiana_copilot.pilot_review_summary import (
    PILOT_REVIEW_ALL_FIELDS,
    recommend_pilot_phase,
    summarize_pilot_review,
    validate_pilot_review_csv_headers,
)
from origenlab_email_pipeline.tatiana_copilot.pilot_schemas import (
    extract_asunto_from_draft,
    safe_case_filename,
)


def test_load_pilot_csv_origenlab_columns(tmp_path: Path) -> None:
    p = tmp_path / "in.csv"
    p.write_text(
        "case_id,subject,body_text,requester_name,explicit_known_facts,missing_information\n"
        "c1,S,Hola cuerpo largo para el piloto con más de cuarenta caracteres requeridos.,"
        "Ana,Cotización N°1 confirmada.,Falta plazo.\n",
        encoding="utf-8",
    )
    cases = load_pilot_input(p)
    assert cases[0].requester_name == "Ana"
    assert cases[0].explicit_known_facts == "Cotización N°1 confirmada."
    assert cases[0].missing_information == "Falta plazo."
    meta = cases[0].context_metadata()
    assert meta.get("explicit_known_facts") == "Cotización N°1 confirmada."


def test_load_pilot_csv_aliases(tmp_path: Path) -> None:
    p = tmp_path / "in.csv"
    p.write_text(
        "case_id,subject,body_for_review\n"
        "c1,Cotización X,Estimados necesitamos precio.\n",
        encoding="utf-8",
    )
    cases = load_pilot_input(p)
    assert len(cases) == 1
    assert cases[0].case_id == "c1"
    assert "necesitamos" in cases[0].body_text


def test_load_pilot_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "in.jsonl"
    p.write_text(
        '{"case_id":"j1","subject":"S","body_text":"Hola cuerpo largo para el piloto."}\n',
        encoding="utf-8",
    )
    cases = load_pilot_input(p)
    assert cases[0].case_id == "j1"


def test_load_pilot_json_batch(tmp_path: Path) -> None:
    p = tmp_path / "in.json"
    p.write_text(
        json.dumps(
            {
                "cases": [
                    {"case_id": "x", "subject": "", "body": "Contenido mínimo suficiente."},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cases = load_pilot_input(p)
    assert cases[0].case_id == "x"


def test_pilot_csv_missing_body_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.csv"
    p.write_text("case_id,subject,body_text\n" "c1,Hi,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="body_text"):
        load_pilot_input(p)


def test_safe_case_filename() -> None:
    assert ".." not in safe_case_filename("a/b:c")
    assert safe_case_filename("  ") == "case"


def test_extract_asunto() -> None:
    d = "Asunto: Cotización – Test\n\nCuerpo.\n"
    assert extract_asunto_from_draft(d) == "Cotización – Test"


def test_resolve_pilot_mock_without_allow_mock_exits() -> None:
    settings = Settings()
    with pytest.raises(SystemExit, match="allow-mock"):
        resolve_pilot_generator(generator_name="mock", allow_mock=False, settings=settings)


def test_resolve_pilot_allows_mock_with_flag() -> None:
    settings = Settings()
    gen, name = resolve_pilot_generator(generator_name="openai_chat", allow_mock=True, settings=settings)
    assert name == "mock"
    assert gen.__class__.__name__ == "MockDraftGenerator"


def test_run_pilot_batch_output_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = Path(__file__).resolve().parents[1]
    labeled = repo / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_labeled_final.csv"
    style = repo / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_seed_style_guide.csv"
    retr = repo / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_seed_retrieval.csv"
    if not (labeled.is_file() and style.is_file() and retr.is_file()):
        pytest.skip("Curated seed CSVs not present in workspace")

    inp = tmp_path / "pilot_in.csv"
    inp.write_text(
        "case_id,subject,body_text\n"
        'p1,Hi,"Estimados, solicitamos cotización de balanza analítica Ohaus. Gracias."\n',
        encoding="utf-8",
    )
    out = tmp_path / "batch"
    settings = Settings()
    result = run_pilot_batch(
        input_path=inp,
        settings=settings,
        generator_name="openai_chat",
        allow_mock=True,
        out_dir=out,
        max_cases=1,
        labeled_final_csv=labeled,
        style_seed_csv=style,
        retrieval_seed_csv=retr,
    )
    assert result.cases_processed == 1
    latest = tmp_path / "latest_tatiana_pilot_batch"
    assert latest.is_symlink()
    assert (latest.resolve()) == out.resolve()
    assert (out / "pilot_cases.csv").is_file()
    assert (out / "pilot_review.csv").is_file()
    assert (out / "pilot_summary.json").is_file()
    assert (out / "pilot_summary.md").is_file()
    jfiles = list(out.glob("case_*.json"))
    assert len(jfiles) == 1
    pkg = json.loads(jfiles[0].read_text(encoding="utf-8"))
    assert "generated_draft" in pkg
    assert "case" in pkg

    with (out / "pilot_review.csv").open(encoding="utf-8", newline="") as f:
        row = next(csv.DictReader(f))
    for col in PILOT_REVIEW_ALL_FIELDS:
        assert col in row
    assert row["reviewer_decision"] == ""
    assert row["reviewer_final_body"] == ""
    assert "case_id" in row


def test_pilot_review_csv_validation_ok(tmp_path: Path) -> None:
    p = tmp_path / "pilot_review.csv"
    p.write_text(",".join(PILOT_REVIEW_ALL_FIELDS) + "\n", encoding="utf-8")
    assert validate_pilot_review_csv_headers(p) == []


def test_summarize_pilot_partial_and_recommendation(tmp_path: Path) -> None:
    p = tmp_path / "pilot_review.csv"
    p.write_text(
        "case_id,subject_input,body_preview,generated_subject,generated_body,abstained,"
        "provider_name,retrieved_style_ids,retrieved_example_ids,system_notes,"
        "reviewer_decision,reviewer_edit_level,reviewer_sentiment,reviewer_notes,"
        "reviewer_final_subject,reviewer_final_body,approved_for_send\n"
        "a,,,s,b,n,mock,,,notes,approve,none,good,,,,\n"
        "b,,,s,b,n,mock,,,notes,,,,,,,\n",
        encoding="utf-8",
    )
    s = summarize_pilot_review(p)
    assert s["counts"]["total_cases"] == 2
    assert s["counts"]["reviewed_cases"] == 1
    assert s["recommendation"]["label"] == "insufficient_review_data"


def test_recommend_stop_pilot() -> None:
    summary = {
        "counts": {
            "total_cases": 10,
            "reviewed_cases": 10,
            "abstained_cases": 0,
            "decision_approve": 1,
            "decision_approve_with_edits": 1,
            "decision_reject": 8,
            "decision_needs_clarification": 0,
            "edit_level_none": 0,
            "edit_level_light": 0,
            "edit_level_moderate": 2,
            "edit_level_heavy": 2,
            "sentiment_good": 0,
            "sentiment_mixed": 0,
            "sentiment_poor": 2,
            "approved_for_send_y": 0,
            "approved_for_send_n": 0,
            "note_bucket_grounding": 0,
            "note_bucket_tone": 0,
            "note_bucket_length": 0,
            "note_bucket_missing_context": 0,
            "note_bucket_subject": 0,
            "note_bucket_retrieval": 0,
        },
        "rates": {
            "approve_rate": 0.1,
            "approve_with_edits_rate": 0.1,
            "reject_rate": 0.8,
            "needs_clarification_rate": 0.0,
            "approve_or_aw_rate": 0.2,
        },
        "averages": {"reviewer_sentiment_score_1_to_3": None},
        "diagnostics": {"reject_case_ids": [], "heavy_edit_case_ids": [], "note_keyword_buckets": {}},
    }
    rec = recommend_pilot_phase(summary)
    assert rec["label"] == "stop_pilot"
