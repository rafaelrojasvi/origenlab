#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.tatiana_copilot.pilot_batch import run_pilot_batch


def _looks_like_doc_placeholder(p: Path) -> bool:
    s = p.as_posix().lower()
    return "path/to/" in s or s.startswith("path/to")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Run a small Tatiana pilot batch: retrieve + generate draft packages into reports/out "
            "(human review CSV only — no email send)."
        )
    )
    ap.add_argument(
        "--input",
        type=Path,
        required=True,
        help=(
            "Pilot case file (.csv, .jsonl, or .json batch). Must be a real path — "
            "not a 'path/to/…' doc placeholder (see docs/dataset/TATIANA_PILOT_WORKFLOW.md)."
        ),
    )
    ap.add_argument("--out-dir", type=Path, default=None, help="Output folder (default: timestamp under reports/out)")
    ap.add_argument("--max-cases", type=int, default=None, help="Limit number of cases (default: all rows)")
    ap.add_argument("--style-top-k", type=int, default=3)
    ap.add_argument("--retrieval-top-k", type=int, default=5)
    ap.add_argument(
        "--generator",
        default="openai_chat",
        choices=("openai_chat", "openai", "llm", "mock"),
        help="LLM backend (default openai_chat). mock requires --allow-mock.",
    )
    ap.add_argument(
        "--allow-mock",
        action="store_true",
        help="Use MockDraftGenerator (no API key). Intended for tests / dry runs.",
    )
    ap.add_argument(
        "--origenlab",
        action="store_true",
        help=(
            "OrigenLab drafting mode: inject company facts from apps/web/src/data (+ policy); "
            "historical examples are style-only. Also supports review-first marketing / presentation "
            "outreach rows when the input includes fields like variant_type / institution_name / sector. "
            "Writes origenlab_context_snapshot.json."
        ),
    )
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
    args = ap.parse_args()

    if not args.input.is_file():
        print("Input not found:", args.input, file=sys.stderr)
        if _looks_like_doc_placeholder(args.input):
            print(
                "Hint: `path/to/...` in docs is a placeholder. Examples:\n"
                "  • Tracked demo CSV (add --allow-mock for no API): "
                f"{_ROOT / 'config' / 'tatiana_pilot_input.example.csv'}\n"
                "  • After cohort export: reports/out/pilot_input_example.csv "
                "(from scripts/tatiana/prepare_tatiana_pilot_input.py)",
                file=sys.stderr,
            )
        raise SystemExit(1)

    settings = load_settings()
    result = run_pilot_batch(
        input_path=args.input,
        settings=settings,
        generator_name=args.generator,
        allow_mock=args.allow_mock,
        out_dir=args.out_dir,
        max_cases=args.max_cases,
        style_top_k=args.style_top_k,
        retrieval_top_k=args.retrieval_top_k,
        labeled_final_csv=args.labeled_final,
        style_seed_csv=args.style_seed,
        retrieval_seed_csv=args.retrieval_seed,
        origenlab_mode=args.origenlab,
    )
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
