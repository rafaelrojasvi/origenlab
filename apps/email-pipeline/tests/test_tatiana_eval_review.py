from __future__ import annotations

import csv
import json
from pathlib import Path

from origenlab_email_pipeline.tatiana_copilot.review_schema import parse_decision, parse_score_1_5
from origenlab_email_pipeline.tatiana_copilot.review_summary import (
    failure_bucket_for_row,
    load_review_rows,
    summarize_review,
    write_review_outputs,
)


def test_parse_score_1_5() -> None:
    assert parse_score_1_5("") is None
    assert parse_score_1_5("3") == 3
    assert parse_score_1_5("0") is None
    assert parse_score_1_5("6") is None
    assert parse_score_1_5("x") is None


def test_parse_decision() -> None:
    assert parse_decision("") is None
    assert parse_decision("accept") == "accept"
    assert parse_decision("EDIT_LIGHT") == "edit_light"
    assert parse_decision("nope") is None


def _write_eval_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "eval_case_id",
        "label_expected",
        "source_example_id",
        "retrieved_example_ids",
        "retrieved_style_ids",
        "generated_draft",
        "abstained",
        "system_notes",
        "notes",
        "reviewer_score_tone",
        "reviewer_score_usefulness",
        "reviewer_score_groundedness",
        "reviewer_score_edit_distance_estimate",
        "reviewer_decision",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def test_summarize_empty_scores(tmp_path: Path) -> None:
    p = tmp_path / "eval_cases.csv"
    _write_eval_csv(
        p,
        [
            {
                "eval_case_id": "eval_001",
                "label_expected": "quote_followup",
                "abstained": "n",
                "system_notes": "mock",
            }
        ],
    )
    rows = load_review_rows(p)
    s = summarize_review(rows)
    assert s["counts"]["scored_cases"] == 0
    assert s["recommendation"]["label"] == "insufficient_review_data"


def test_failure_bucket_keywords(tmp_path: Path) -> None:
    p = tmp_path / "eval_cases.csv"
    _write_eval_csv(
        p,
        [
            {
                "eval_case_id": "eval_001",
                "label_expected": "quote_followup",
                "abstained": "n",
                "system_notes": "",
                "notes": "Falta información de cantidad y plazo",
                "reviewer_score_groundedness": "3",
                "reviewer_decision": "edit_light",
            }
        ],
    )
    rr = load_review_rows(p)[0]
    assert failure_bucket_for_row(rr) in {"missing_context", "commercial_facts_missing"}


def test_recommendation_ready_for_provider(tmp_path: Path) -> None:
    p = tmp_path / "eval_cases.csv"
    rows = []
    for i in range(12):
        rows.append(
            {
                "eval_case_id": f"eval_{i:03d}",
                "label_expected": "quote_followup",
                "abstained": "n",
                "system_notes": "",
                "notes": "",
                "reviewer_score_tone": "5",
                "reviewer_score_usefulness": "4",
                "reviewer_score_groundedness": "4",
                "reviewer_score_edit_distance_estimate": "2",
                "reviewer_decision": "accept",
            }
        )
    _write_eval_csv(p, rows)
    s = summarize_review(load_review_rows(p))
    assert s["recommendation"]["label"] == "ready_for_provider_pilot"


def test_write_review_outputs(tmp_path: Path) -> None:
    p = tmp_path / "eval_cases.csv"
    _write_eval_csv(
        p,
        [
            {
                "eval_case_id": "eval_001",
                "label_expected": "quote_followup",
                "abstained": "n",
                "system_notes": "",
                "notes": "muy genérico",
                "reviewer_score_usefulness": "2",
                "reviewer_score_groundedness": "4",
                "reviewer_decision": "edit_heavy",
                "reviewer_score_edit_distance_estimate": "4",
            }
        ],
    )
    rr = load_review_rows(p)
    s = summarize_review(rr)
    out_dir = tmp_path / "out"
    write_review_outputs(summary=s, rows=rr, out_dir=out_dir)
    assert (out_dir / "review_summary.json").is_file()
    assert (out_dir / "review_summary.md").is_file()
    assert (out_dir / "review_failures.csv").is_file()
    assert (out_dir / "review_priority_cases.csv").is_file()
