#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.tatiana_copilot.evaluation import run_holdout_evaluation
from origenlab_email_pipeline.tatiana_copilot.generator_factory import (
    TatianaLLMConfigurationError,
    resolve_draft_generator,
)
from origenlab_email_pipeline.tatiana_copilot.normalize import build_example_sets


def main() -> None:
    ap = argparse.ArgumentParser(description="Run held-out Tatiana draft eval (review-first artifacts)")
    ap.add_argument("--max-cases", type=int, default=30)
    ap.add_argument("--style-top-k", type=int, default=3)
    ap.add_argument("--retrieval-top-k", type=int, default=5)
    ap.add_argument(
        "--labeled-final",
        type=Path,
        default=_ROOT / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_labeled_final.csv",
    )
    ap.add_argument(
        "--style-seed",
        type=Path,
        default=_ROOT / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_seed_style_guide.csv",
    )
    ap.add_argument(
        "--retrieval-seed",
        type=Path,
        default=_ROOT / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_seed_retrieval.csv",
    )
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument(
        "--generator",
        default="mock",
        choices=("mock", "openai_chat", "openai", "llm"),
        help="mock = offline; openai_chat|openai|llm = OpenAI Chat Completions (API key required)",
    )
    args = ap.parse_args()

    settings = load_settings()
    try:
        gen = resolve_draft_generator(args.generator, settings=settings)
    except TatianaLLMConfigurationError as e:
        print("Configuration error:", e, file=sys.stderr)
        raise SystemExit(2) from e
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or (settings.resolved_reports_dir() / f"{ts}_tatiana_draft_eval")
    style, retr = build_example_sets(
        labeled_final_csv=args.labeled_final,
        style_seed_csv=args.style_seed,
        retrieval_seed_csv=args.retrieval_seed,
    )
    summary = run_holdout_evaluation(
        examples_for_eval=retr,
        style_examples=style,
        retrieval_examples=retr,
        out_dir=out_dir,
        generator=gen,
        max_cases=args.max_cases,
        style_top_k=args.style_top_k,
        retrieval_top_k=args.retrieval_top_k,
    )
    print(summary)


if __name__ == "__main__":
    main()
