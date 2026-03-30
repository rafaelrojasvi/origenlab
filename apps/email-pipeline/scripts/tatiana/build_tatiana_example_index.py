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
from origenlab_email_pipeline.tatiana_copilot.index import TatianaExampleIndex
from origenlab_email_pipeline.tatiana_copilot.normalize import build_example_sets


def main() -> None:
    ap = argparse.ArgumentParser(description="Build local Tatiana copilot index artifact")
    ap.add_argument("--method", choices=("tfidf", "sbert"), default="tfidf")
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
    ap.add_argument("--out", type=Path, default=None, help="JSON index artifact path")
    args = ap.parse_args()

    settings = load_settings()
    out = args.out or (settings.resolved_reports_dir() / "tatiana_copilot_index.json")
    style, retr = build_example_sets(
        labeled_final_csv=args.labeled_final,
        style_seed_csv=args.style_seed,
        retrieval_seed_csv=args.retrieval_seed,
    )
    idx = TatianaExampleIndex.build(style_examples=style, retrieval_examples=retr, method=args.method)
    idx.save(out)

    preview = {
        "index_path": str(out),
        "method": args.method,
        "style_examples": len(style),
        "retrieval_examples": len(retr),
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
