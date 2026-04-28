#!/usr/bin/env python3
"""Automate Deep Research prospecting through review-ready outputs.

Safety: this command never sends email and stops before outbound execution.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.core.research_automation import (
    DEFAULT_PROMPT_PATH,
    SECTOR_CHOICES,
    default_seed_paths,
    resolve_out_dir,
    resolve_sector_for_day_rotation,
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
        choices=SECTOR_CHOICES,
        default="broad",
        help="Research lens preset used in the prompt.",
    )
    ap.add_argument(
        "--day-rotation",
        action="store_true",
        help="Override --sector with a day-of-week rotation (Mon..Sun).",
    )
    ap.add_argument(
        "--daily-mode",
        action="store_true",
        help="Apply daily-run guidance metadata and warnings (review-only; no send).",
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
    ap.add_argument(
        "--max-candidates",
        type=int,
        default=200,
        help="Maximum extracted candidate rows allowed before truncation/fail (default: 200).",
    )
    ap.add_argument(
        "--max-send-ready",
        type=int,
        default=50,
        help="Review warning threshold for send_ready rows after processing (default: 50).",
    )
    ap.add_argument(
        "--fail-on-over-limit",
        action="store_true",
        help="Fail instead of truncating when extracted candidates exceed --max-candidates.",
    )
    ap.add_argument(
        "--run-contacted-coverage-check",
        action="store_true",
        help=(
            "Run read-only scripts/qa/validate_contacted_csv_coverage.py and store JSON report in the run folder."
        ),
    )
    ap.add_argument(
        "--strict-contacted-coverage",
        action="store_true",
        help="Only meaningful with --run-contacted-coverage-check; fail run on validator non-zero exit.",
    )
    ap.add_argument(
        "--max-seed-email-sample",
        type=int,
        default=300,
        help="Max emails kept in compact seed sample file (default: 300).",
    )
    ap.add_argument(
        "--max-seed-institutions",
        type=int,
        default=500,
        help="Max institution rows kept in compact seed file (default: 500).",
    )
    ap.add_argument(
        "--max-seed-domains",
        type=int,
        default=500,
        help="Max domain rows kept in compact seed file (default: 500).",
    )
    ap.add_argument(
        "--use-file-search",
        action="store_true",
        help="Future-ready flag: note intent to use vector-store file search (not enabled by default).",
    )
    ap.add_argument(
        "--max-retries",
        type=int,
        default=4,
        help="Max retry attempts for retryable Deep Research API failures (default: 4).",
    )
    ap.add_argument(
        "--initial-backoff-seconds",
        type=float,
        default=5.0,
        help="Initial backoff seconds before retrying retryable API failures (default: 5.0).",
    )
    ap.add_argument(
        "--max-backoff-seconds",
        type=float,
        default=120.0,
        help="Max backoff cap in seconds for retries (default: 120.0).",
    )
    ap.add_argument(
        "--fallback-sector",
        choices=SECTOR_CHOICES,
        default=None,
        help="Optional narrow fallback sector if primary sector keeps failing with retryable API errors.",
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
    selected_sector = str(args.sector)
    if args.day_rotation:
        selected_sector = resolve_sector_for_day_rotation(weekday=datetime.now().weekday())
    if args.daily_mode and selected_sector == "broad":
        print("Warning: daily broad runs may hit rate limits; prefer weekday sector rotation.")
    artifacts = run_research_automation(
        model=str(args.model),
        prompt_file=Path(args.prompt_file),
        out_dir=out_dir,
        sector=selected_sector,
        limit_hint=int(args.limit_hint) if args.limit_hint and args.limit_hint > 0 else None,
        dry_run=bool(args.dry_run),
        sample_response=Path(args.sample_response) if args.sample_response else None,
        seed_paths=seeds,
        use_background=not bool(args.no_background),
        app_root=_ROOT,
        max_candidates=max(1, int(args.max_candidates)),
        max_send_ready=max(1, int(args.max_send_ready)),
        fail_on_over_limit=bool(args.fail_on_over_limit),
        run_contacted_coverage_check=bool(args.run_contacted_coverage_check),
        strict_contacted_coverage=bool(args.strict_contacted_coverage),
        max_seed_email_sample=max(1, int(args.max_seed_email_sample)),
        max_seed_institutions=max(1, int(args.max_seed_institutions)),
        max_seed_domains=max(1, int(args.max_seed_domains)),
        use_file_search=bool(args.use_file_search),
        max_retries=max(1, int(args.max_retries)),
        initial_backoff_seconds=max(0.1, float(args.initial_backoff_seconds)),
        max_backoff_seconds=max(1.0, float(args.max_backoff_seconds)),
        fallback_sector=str(args.fallback_sector) if args.fallback_sector else None,
        daily_mode=bool(args.daily_mode),
    )
    print(f"Wrote: {artifacts.out_dir}")
    print(f"Review summary: {artifacts.review_summary_md}")
    print("Ready for review; no live send performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
