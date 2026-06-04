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
from origenlab_email_pipeline.tatiana_copilot.draft_package import build_draft_package
from origenlab_email_pipeline.tatiana_copilot.origenlab_context import DRAFTING_PROFILE_ORIGENLAB
from origenlab_email_pipeline.tatiana_copilot.origenlab_facts_loader import load_origenlab_drafting_context
from origenlab_email_pipeline.tatiana_copilot.generator_factory import (
    TatianaLLMConfigurationError,
    resolve_draft_generator,
)
from origenlab_email_pipeline.tatiana_copilot.index import TatianaExampleIndex
from origenlab_email_pipeline.tatiana_copilot.schemas import DraftCase


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a review-first Tatiana draft package JSON")
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--case-json", type=Path, required=True, help="Input case JSON: case_id/subject/body_text")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--style-top-k", type=int, default=3)
    ap.add_argument("--retrieval-top-k", type=int, default=5)
    ap.add_argument(
        "--generator",
        default="mock",
        choices=("mock", "openai_chat", "openai", "llm"),
        help="mock = offline template; openai_chat|openai|llm = OpenAI Chat Completions (requires API key)",
    )
    ap.add_argument(
        "--origenlab",
        action="store_true",
        help="OrigenLab drafting profile + load OrigenLab drafting context (facts). Matches the retired "
        "Borrador comercial page and run_tatiana_pilot_batch.py --origenlab. Default (historical curator profile) is unchanged.",
    )
    args = ap.parse_args()

    settings = load_settings()
    try:
        gen = resolve_draft_generator(args.generator, settings=settings)
    except TatianaLLMConfigurationError as e:
        print("Configuration error:", e, file=sys.stderr)
        raise SystemExit(2) from e
    index_path = args.index or (settings.resolved_reports_dir() / "tatiana_copilot_index.json")
    out = args.out or (settings.resolved_reports_dir() / "tatiana_draft_package.json")
    idx = TatianaExampleIndex.load(index_path)

    case_obj = json.loads(args.case_json.read_text(encoding="utf-8"))
    case = DraftCase(
        case_id=str(case_obj.get("case_id") or "case_001"),
        subject=str(case_obj.get("subject") or ""),
        body_text=str(case_obj.get("body_text") or ""),
        expected_label=(str(case_obj["expected_label"]) if case_obj.get("expected_label") else None),
        context_metadata=dict(case_obj.get("context_metadata") or {}),
    )

    kw: dict = {}
    if args.origenlab:
        kw["drafting_profile"] = DRAFTING_PROFILE_ORIGENLAB
        kw["origenlab_context"] = load_origenlab_drafting_context()
    pkg = build_draft_package(
        case=case,
        index=idx,
        generator=gen,
        style_top_k=args.style_top_k,
        retrieval_top_k=args.retrieval_top_k,
        **kw,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pkg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
