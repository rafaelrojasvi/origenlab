#!/usr/bin/env python3
"""Automate Deep Research prospecting through review-ready outputs.

Safety: this command never sends email and stops before outbound execution.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.core.research_automation import (
    DEFAULT_PROMPT_PATH,
    default_seed_paths,
    resolve_out_dir,
    run_research_automation,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--model",
        default="o4-mini-deep-research",
        help="Deep research model id (Responses API), default: o4-mini-deep-research",
    )
    ap.add_argument(
        "--prompt-file",
        type=Path,
        default=DEFAULT_PROMPT_PATH,
        help="Prompt template path (format placeholders supported).",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output run directory (default: reports/out/active/current/research_automation/<timestamp>/).",
    )
    ap.add_argument("--limit-hint", type=int, default=40, help="Soft candidate count hint for the model.")
    ap.add_argument(
        "--sector",
        choices=("broad", "food_qc", "water_env", "thin_regions", "custom"),
        default="broad",
        help="Research lens preset used in the prompt.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip API call and parse --sample-response through local screening pipeline.",
    )
    ap.add_argument(
        "--sample-response",
        type=Path,
        default=None,
        help="Raw model response text file used with --dry-run.",
    )
    ap.add_argument(
        "--seed-dnr",
        type=Path,
        default=None,
        help="Override do_not_repeat_master.csv path.",
    )
    ap.add_argument(
        "--seed-contacted",
        type=Path,
        default=None,
        help="Override outreach_contacted_all.csv path.",
    )
    ap.add_argument(
        "--seed-known-marketing",
        type=Path,
        default=None,
        help="Override all_known_marketing_contacts_dedup.csv path.",
    )
    ap.add_argument(
        "--no-background",
        action="store_true",
        help="Disable Responses API background mode and wait on a single request.",
    )
    args = ap.parse_args(argv)

    seeds = default_seed_paths()
    if args.seed_dnr is not None:
        seeds = seeds.__class__(
            do_not_repeat_master=args.seed_dnr,
            outreach_contacted_all=seeds.outreach_contacted_all,
            all_known_marketing_contacts_dedup=seeds.all_known_marketing_contacts_dedup,
        )
    if args.seed_contacted is not None:
        seeds = seeds.__class__(
            do_not_repeat_master=seeds.do_not_repeat_master,
            outreach_contacted_all=args.seed_contacted,
            all_known_marketing_contacts_dedup=seeds.all_known_marketing_contacts_dedup,
        )
    if args.seed_known_marketing is not None:
        seeds = seeds.__class__(
            do_not_repeat_master=seeds.do_not_repeat_master,
            outreach_contacted_all=seeds.outreach_contacted_all,
            all_known_marketing_contacts_dedup=args.seed_known_marketing,
        )

    out_dir = resolve_out_dir(out_dir=args.out_dir)
    artifacts = run_research_automation(
        model=str(args.model),
        prompt_file=Path(args.prompt_file),
        out_dir=out_dir,
        sector=str(args.sector),
        limit_hint=int(args.limit_hint) if args.limit_hint and args.limit_hint > 0 else None,
        dry_run=bool(args.dry_run),
        sample_response=Path(args.sample_response) if args.sample_response else None,
        seed_paths=seeds,
        use_background=not bool(args.no_background),
        app_root=_ROOT,
    )
    print(f"Wrote: {artifacts.out_dir}")
    print(f"Review summary: {artifacts.review_summary_md}")
    print("Ready for review; no live send performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
