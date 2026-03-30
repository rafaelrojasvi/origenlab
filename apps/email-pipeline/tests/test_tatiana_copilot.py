from __future__ import annotations

import csv
from pathlib import Path

from origenlab_email_pipeline.tatiana_copilot.draft_package import build_draft_package
from origenlab_email_pipeline.tatiana_copilot.evaluation import run_holdout_evaluation
from origenlab_email_pipeline.tatiana_copilot.generator import MockDraftGenerator
from origenlab_email_pipeline.tatiana_copilot.index import TatianaExampleIndex
from origenlab_email_pipeline.tatiana_copilot.normalize import build_example_sets
from origenlab_email_pipeline.tatiana_copilot.schemas import DraftCase


def _write_seed_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "review_priority_rank",
        "id",
        "date_iso",
        "subject",
        "body_for_review",
        "risk_flags",
        "heavy_reply_tail",
        "human_label",
        "auto_label",
        "keep_for_style_guide",
        "keep_for_retrieval_later",
        "marketing_rank_score",
        "marketing_rank_notes",
        "likely_outbound_external",
        "intent_primary_category",
        "intent_commercial_subtype",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def test_normalization_build_example_sets(tmp_path: Path) -> None:
    labeled = tmp_path / "labeled.csv"
    style = tmp_path / "style.csv"
    retr = tmp_path / "retr.csv"
    row_a = {
        "review_priority_rank": "1",
        "id": "101",
        "date_iso": "2019-01-01T00:00:00+00:00",
        "subject": "Cotización balanza",
        "body_for_review": "Gracias por contactarnos. Junto con saludar adjunto cotización.",
        "human_label": "quote_followup",
        "keep_for_style_guide": "y",
        "keep_for_retrieval_later": "y",
    }
    row_b = {
        "review_priority_rank": "2",
        "id": "102",
        "date_iso": "2018-01-01T00:00:00+00:00",
        "subject": "Presentación Labdelivery",
        "body_for_review": "Me presento, mi nombre es Tatiana Vivanco.",
        "human_label": "intro_marketing",
        "keep_for_style_guide": "y",
        "keep_for_retrieval_later": "y",
    }
    _write_seed_csv(labeled, [row_a, row_b])
    _write_seed_csv(style, [row_b])
    _write_seed_csv(retr, [row_a, row_b])

    style_examples, retr_examples = build_example_sets(
        labeled_final_csv=labeled,
        style_seed_csv=style,
        retrieval_seed_csv=retr,
    )
    assert len(style_examples) == 1
    assert len(retr_examples) == 2
    assert style_examples[0].kind == "style"
    assert retr_examples[0].kind == "retrieval"
    assert style_examples[0].label == "intro_marketing"


def test_retrieval_top_hit_is_relevant(tmp_path: Path) -> None:
    labeled = tmp_path / "labeled.csv"
    style = tmp_path / "style.csv"
    retr = tmp_path / "retr.csv"
    q = {
        "review_priority_rank": "1",
        "id": "1",
        "subject": "Cotización termobalanza",
        "body_for_review": "Adjunto cotización por termobalanza y especificaciones.",
        "human_label": "quote_followup",
        "keep_for_style_guide": "y",
        "keep_for_retrieval_later": "y",
    }
    i = {
        "review_priority_rank": "2",
        "id": "2",
        "subject": "Presentación empresa",
        "body_for_review": "Me presento, mi nombre es Tatiana Vivanco.",
        "human_label": "intro_marketing",
        "keep_for_style_guide": "y",
        "keep_for_retrieval_later": "y",
    }
    _write_seed_csv(labeled, [q, i])
    _write_seed_csv(style, [i])
    _write_seed_csv(retr, [q, i])
    style_examples, retr_examples = build_example_sets(
        labeled_final_csv=labeled,
        style_seed_csv=style,
        retrieval_seed_csv=retr,
    )
    idx = TatianaExampleIndex.build(
        style_examples=style_examples, retrieval_examples=retr_examples, method="tfidf"
    )
    got = idx.retrieve_retrieval(query_text="Necesito cotización de termobalanza", top_k=1)
    assert len(got) == 1
    assert "cotización" in got[0].body_text.lower()


def test_holdout_exclusion_in_package(tmp_path: Path) -> None:
    labeled = tmp_path / "labeled.csv"
    style = tmp_path / "style.csv"
    retr = tmp_path / "retr.csv"
    row = {
        "review_priority_rank": "1",
        "id": "1",
        "subject": "Cotización equipos",
        "body_for_review": "Gracias por contactarnos. Adjunto cotización.",
        "human_label": "quote_followup",
        "keep_for_style_guide": "y",
        "keep_for_retrieval_later": "y",
    }
    _write_seed_csv(labeled, [row])
    _write_seed_csv(style, [row])
    _write_seed_csv(retr, [row])
    style_examples, retr_examples = build_example_sets(
        labeled_final_csv=labeled,
        style_seed_csv=style,
        retrieval_seed_csv=retr,
    )
    idx = TatianaExampleIndex.build(
        style_examples=style_examples, retrieval_examples=retr_examples, method="tfidf"
    )
    case = DraftCase(case_id="c1", subject="Cotización equipos", body_text="Adjunto cotización para revisión")
    exid = retr_examples[0].example_id
    pkg = build_draft_package(
        case=case,
        index=idx,
        exclude_example_ids={exid},
    )
    assert all(x["example_id"] != exid for x in pkg.retrieved_examples)


def test_mock_generator_safe_no_provider_abstain() -> None:
    gen = MockDraftGenerator()
    out = gen.generate({"case": {"subject": "Hola", "body_text": "muy corto"}})
    assert out.abstained is True
    assert out.provider_name == "mock"


def test_evaluation_output_schema(tmp_path: Path) -> None:
    labeled = tmp_path / "labeled.csv"
    style = tmp_path / "style.csv"
    retr = tmp_path / "retr.csv"
    row = {
        "review_priority_rank": "1",
        "id": "1",
        "subject": "Cotización equipos",
        "body_for_review": "Gracias por contactarnos. Adjunto cotización con especificaciones.",
        "human_label": "quote_followup",
        "keep_for_style_guide": "y",
        "keep_for_retrieval_later": "y",
    }
    _write_seed_csv(labeled, [row])
    _write_seed_csv(style, [row])
    _write_seed_csv(retr, [row])
    style_examples, retr_examples = build_example_sets(
        labeled_final_csv=labeled,
        style_seed_csv=style,
        retrieval_seed_csv=retr,
    )
    out_dir = tmp_path / "eval_out"
    summary = run_holdout_evaluation(
        examples_for_eval=retr_examples,
        style_examples=style_examples,
        retrieval_examples=retr_examples,
        out_dir=out_dir,
        max_cases=1,
    )
    assert summary["eval_cases"] == 1
    assert summary["holdout_excluded_from_retrieval_pool"] == 1
    eval_csv = out_dir / "eval_cases.csv"
    assert eval_csv.is_file()
    rows = list(csv.DictReader(eval_csv.open(newline="", encoding="utf-8")))
    assert "reviewer_score_tone" in rows[0]
    assert "reviewer_decision" in rows[0]


def test_eval_holdout_excluded_from_retrieval_results(tmp_path: Path) -> None:
    labeled = tmp_path / "labeled.csv"
    style = tmp_path / "style.csv"
    retr = tmp_path / "retr.csv"
    row1 = {
        "review_priority_rank": "1",
        "id": "1",
        "subject": "Cotización equipos A",
        "body_for_review": "Gracias por contactarnos. Adjunto cotización A.",
        "human_label": "quote_followup",
        "keep_for_style_guide": "y",
        "keep_for_retrieval_later": "y",
    }
    row2 = {
        "review_priority_rank": "2",
        "id": "2",
        "subject": "Cotización equipos B",
        "body_for_review": "Gracias por contactarnos. Adjunto cotización B.",
        "human_label": "quote_followup",
        "keep_for_style_guide": "y",
        "keep_for_retrieval_later": "y",
    }
    _write_seed_csv(labeled, [row1, row2])
    _write_seed_csv(style, [row1, row2])
    _write_seed_csv(retr, [row1, row2])
    style_examples, retr_examples = build_example_sets(
        labeled_final_csv=labeled,
        style_seed_csv=style,
        retrieval_seed_csv=retr,
    )
    out_dir = tmp_path / "eval_out2"
    run_holdout_evaluation(
        examples_for_eval=retr_examples[:2],
        style_examples=style_examples,
        retrieval_examples=retr_examples,
        out_dir=out_dir,
        max_cases=2,
        retrieval_top_k=5,
    )
    # Each eval case JSON should not retrieve any of the holdout ids (2 cases held out)
    holdout = {retr_examples[0].example_id, retr_examples[1].example_id}
    for cid in ("eval_001", "eval_002"):
        import json

        obj = json.loads((out_dir / f"{cid}.json").read_text(encoding="utf-8"))
        got = {x["example_id"] for x in obj.get("retrieved_examples", [])} | {
            x["example_id"] for x in obj.get("retrieved_style_examples", [])
        }
        assert got.isdisjoint(holdout)
