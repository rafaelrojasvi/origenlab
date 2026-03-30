from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .draft_package import build_draft_package
from .generator import DraftGenerator, MockDraftGenerator
from .index import TatianaExampleIndex
from .schemas import DraftCase, ExampleRecord


def run_holdout_evaluation(
    *,
    examples_for_eval: list[ExampleRecord],
    style_examples: list[ExampleRecord],
    retrieval_examples: list[ExampleRecord],
    out_dir: Path,
    generator: DraftGenerator | None = None,
    max_cases: int = 30,
    style_top_k: int = 3,
    retrieval_top_k: int = 5,
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    gen = generator or MockDraftGenerator()
    cases = examples_for_eval[:max_cases]
    eval_rows: list[dict[str, object]] = []
    abstained = 0

    holdout_ids = {ex.example_id for ex in cases}
    retrieval_pool = [ex for ex in retrieval_examples if ex.example_id not in holdout_ids]
    style_pool = style_examples

    index = TatianaExampleIndex.build(
        style_examples=style_pool,
        retrieval_examples=retrieval_pool,
        method="tfidf",
    )

    for i, ex in enumerate(cases, start=1):
        case = DraftCase(
            case_id=f"eval_{i:03d}",
            subject=ex.subject,
            body_text=ex.body_text,
            expected_label=ex.label or None,
            context_metadata={"source_example_id": ex.example_id},
        )
        pkg = build_draft_package(
            case=case,
            index=index,
            generator=gen,
            style_top_k=style_top_k,
            retrieval_top_k=retrieval_top_k,
            # self-match is already excluded by pool, but keep belt+suspenders
            exclude_example_ids={ex.example_id},
        )
        if pkg.abstained:
            abstained += 1

        case_json = out_dir / f"{case.case_id}.json"
        case_json.write_text(json.dumps(pkg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        eval_rows.append(
            {
                "eval_case_id": case.case_id,
                "label_expected": case.expected_label or "",
                "source_example_id": ex.example_id,
                "retrieved_example_ids": ";".join(x["example_id"] for x in pkg.retrieved_examples),
                "retrieved_style_ids": ";".join(x["example_id"] for x in pkg.retrieved_style_examples),
                "generated_draft": pkg.generated_draft,
                "abstained": "y" if pkg.abstained else "n",
                # system_notes = pipeline metadata (not reviewer input)
                "system_notes": pkg.notes,
                # notes = reviewer free-text (filled manually)
                "notes": "",
                "reviewer_score_tone": "",
                "reviewer_score_usefulness": "",
                "reviewer_score_groundedness": "",
                "reviewer_score_edit_distance_estimate": "",
                "reviewer_decision": "",
            }
        )

    csv_path = out_dir / "eval_cases.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(eval_rows[0].keys()) if eval_rows else [])
        if eval_rows:
            w.writeheader()
            w.writerows(eval_rows)

    summary = {
        "eval_cases": len(eval_rows),
        "abstained_cases": abstained,
        "abstain_rate": (abstained / len(eval_rows)) if eval_rows else 0.0,
        "style_pool_size": len(style_examples),
        "retrieval_pool_size": len(retrieval_pool),
        "holdout_excluded_from_retrieval_pool": len(holdout_ids),
        "generator": gen.__class__.__name__,
        "output_dir": str(out_dir),
    }
    (out_dir / "eval_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
