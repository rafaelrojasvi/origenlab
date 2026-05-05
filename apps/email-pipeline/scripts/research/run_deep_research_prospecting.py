#!/usr/bin/env python3
"""Automate Deep Research prospecting through review-ready outputs.

Safety: this command never sends email and stops before outbound execution.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from itertools import cycle
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.core.research_automation import (
    DEFAULT_HEAVY_MODEL,
    DEFAULT_LIGHT_MODEL,
    DEFAULT_LIGHT_PROMPT_PATH,
    OUTPUT_MODE_CHOICES,
    DEFAULT_PROMPT_PATH,
    RESEARCH_MODE_CHOICES,
    SECTOR_CHOICES,
    default_seed_paths,
    is_deep_research_model,
    resolve_model_for_mode,
    resolve_out_dir,
    resolve_sector_for_day_rotation,
    run_research_automation,
)


def _flag_present(argv: list[str], flag: str) -> bool:
    return any(tok == flag or tok.startswith(f"{flag}=") for tok in argv)


class ProgressReporter:
    def __init__(self, *, out_dir: Path, verbose: bool) -> None:
        self._start = time.monotonic()
        self._out_dir = str(out_dir)
        self._verbose = bool(verbose)
        self._isatty = bool(sys.stdout.isatty())
        self._spinner = cycle(["|", "/", "-", "\\"])
        self._last_phase = ""
        self._last_line_len = 0

    def _line(self, *, phase: str, detail: str, elapsed: float, retries: int, sector: str) -> str:
        spin = next(self._spinner) if self._isatty else "*"
        return (
            f"{spin} [{elapsed:6.1f}s] phase={phase} retries={retries} "
            f"sector={sector} out_dir={self._out_dir} {detail}".strip()
        )

    def emit(self, event: dict[str, object]) -> None:
        phase = str(event.get("phase", "unknown"))
        detail = str(event.get("detail", "") or "")
        elapsed = float(event.get("elapsed_seconds", time.monotonic() - self._start))
        retries = int(event.get("retry_count", 0))
        sector = str(event.get("sector", "n/a"))
        line = self._line(phase=phase, detail=detail, elapsed=elapsed, retries=retries, sector=sector)
        should_print = self._verbose or phase != self._last_phase or phase in {
            "queued",
            "in_progress",
            "retrying_after_rate_limit",
            "ready_for_review",
        }
        if not should_print:
            return
        if self._isatty:
            sys.stdout.write("\r" + line + " " * max(0, self._last_line_len - len(line)))
            sys.stdout.flush()
            self._last_line_len = len(line)
            if phase in {"ready_for_review", "failed"}:
                sys.stdout.write("\n")
                sys.stdout.flush()
        else:
            print(line)
        self._last_phase = phase


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--research-mode",
        choices=RESEARCH_MODE_CHOICES,
        default="heavy",
        help="Research execution mode: heavy (weekly/off-peak) or light (daily).",
    )
    ap.add_argument(
        "--research-output-mode",
        choices=OUTPUT_MODE_CHOICES,
        default="direct_csv",
        help="direct_csv: model returns candidate CSV; evidence_first: model returns search plan only.",
    )
    ap.add_argument(
        "--model",
        default=None,
        help="Responses model id override. Defaults by --research-mode.",
    )
    ap.add_argument(
        "--prompt-file",
        type=Path,
        default=None,
        help="Prompt template path override (format placeholders supported).",
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
        default=None,
        help="Maximum extracted candidate rows allowed before truncation/fail (default: 200).",
    )
    ap.add_argument(
        "--max-send-ready",
        type=int,
        default=None,
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
        default=None,
        help="Max emails kept in compact seed sample file (default: 300).",
    )
    ap.add_argument(
        "--max-seed-institutions",
        type=int,
        default=None,
        help="Max institution rows kept in compact seed file (default: 500).",
    )
    ap.add_argument(
        "--max-seed-domains",
        type=int,
        default=None,
        help="Max domain rows kept in compact seed file (default: 500).",
    )
    ap.add_argument(
        "--tpm-safe",
        action="store_true",
        help=(
            "Apply conservative TPM-safe defaults for smaller real runs unless those flags "
            "are explicitly overridden."
        ),
    )
    ap.add_argument(
        "--tiny-run",
        action="store_true",
        help=(
            "Apply extra-small defaults for first successful real runs unless those flags "
            "are explicitly overridden."
        ),
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
    ap.add_argument(
        "--verbose-progress",
        action="store_true",
        help="Print every progress status event during long-running jobs.",
    )
    ap.add_argument(
        "--print-research-config",
        action="store_true",
        help="Print resolved research config before execution.",
    )
    args = ap.parse_args(argv)
    research_mode = str(args.research_mode)
    prompt_explicit = _flag_present(argv, "--prompt-file")
    resolved_model = resolve_model_for_mode(
        research_mode=research_mode,
        explicit_model=str(args.model) if args.model else None,
    )
    if research_mode == "light" and "deep-research" in resolved_model.lower():
        print(
            "Warning: light mode requires a non deep-research model; "
            f"switching to {DEFAULT_LIGHT_MODEL}."
        )
        resolved_model = DEFAULT_LIGHT_MODEL
    if prompt_explicit and args.prompt_file is not None:
        resolved_prompt_file = Path(args.prompt_file)
    else:
        resolved_prompt_file = (
            DEFAULT_PROMPT_PATH if research_mode == "heavy" else DEFAULT_LIGHT_PROMPT_PATH
        )

    base_defaults = {
        "max_candidates": 200,
        "max_send_ready": 50,
        "max_seed_email_sample": 300,
        "max_seed_institutions": 500,
        "max_seed_domains": 500,
        "max_retries": 4,
    }
    tpm_safe_defaults = {
        "max_candidates": 40,
        "max_send_ready": 15,
        "max_seed_email_sample": 100,
        "max_seed_institutions": 150,
        "max_seed_domains": 150,
        "max_retries": 4,
    }
    tiny_run_defaults = {
        "max_candidates": 20,
        "max_send_ready": 10,
        "max_seed_email_sample": 50,
        "max_seed_institutions": 80,
        "max_seed_domains": 80,
        "max_retries": 2,
    }

    resolved = {}
    for key, cli_flag in (
        ("max_candidates", "--max-candidates"),
        ("max_send_ready", "--max-send-ready"),
        ("max_seed_email_sample", "--max-seed-email-sample"),
        ("max_seed_institutions", "--max-seed-institutions"),
        ("max_seed_domains", "--max-seed-domains"),
    ):
        explicit = _flag_present(argv, cli_flag)
        raw_value = getattr(args, key)
        if raw_value is not None:
            resolved[key] = int(raw_value)
        elif bool(args.tiny_run) and not explicit:
            resolved[key] = tiny_run_defaults[key]
        elif bool(args.tpm_safe) and not explicit:
            resolved[key] = tpm_safe_defaults[key]
        else:
            resolved[key] = base_defaults[key]
    max_retries_resolved = (
        int(args.max_retries)
        if _flag_present(argv, "--max-retries")
        else (
            tiny_run_defaults["max_retries"]
            if bool(args.tiny_run)
            else base_defaults["max_retries"]
        )
    )

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
        print(
            "Warning: --daily-mode with --sector broad can hit TPM limits; "
            "prefer broad weekly/off-peak and smaller daily sectors."
        )
    if selected_sector in {"broad", "water_env"} and (
        int(resolved["max_candidates"]) > tiny_run_defaults["max_candidates"]
        or int(resolved["max_seed_email_sample"]) > tiny_run_defaults["max_seed_email_sample"]
        or int(resolved["max_seed_institutions"]) > tiny_run_defaults["max_seed_institutions"]
        or int(resolved["max_seed_domains"]) > tiny_run_defaults["max_seed_domains"]
    ):
        print(
            "Warning: selected sector plus current guardrails may exceed TPM on lower tiers. "
            "Use --tiny-run for first successful real executions."
        )
    if research_mode == "heavy":
        print(
            "Warning: heavy mode is higher cost; run it only after light/evidence pipeline is structurally stable. "
            "Heavy mode still uses the same evidence verification rules."
        )
    if args.print_research_config:
        print("Research config")
        print(f"  research_mode: {research_mode}")
        print(f"  research_output_mode: {args.research_output_mode}")
        print(f"  selected_model: {resolved_model}")
        print(f"  is_deep_research_model: {is_deep_research_model(resolved_model)}")
        print("  tools_enabled: web_search")
        print(f"  prompt_file: {resolved_prompt_file}")
        print(f"  sector: {selected_sector}")
    progress = ProgressReporter(out_dir=out_dir, verbose=bool(args.verbose_progress))
    artifacts = run_research_automation(
        model=resolved_model,
        prompt_file=resolved_prompt_file,
        out_dir=out_dir,
        sector=selected_sector,
        limit_hint=int(args.limit_hint) if args.limit_hint and args.limit_hint > 0 else None,
        dry_run=bool(args.dry_run),
        sample_response=Path(args.sample_response) if args.sample_response else None,
        seed_paths=seeds,
        use_background=not bool(args.no_background),
        app_root=_ROOT,
        max_candidates=max(1, int(resolved["max_candidates"])),
        max_send_ready=max(1, int(resolved["max_send_ready"])),
        fail_on_over_limit=bool(args.fail_on_over_limit),
        run_contacted_coverage_check=bool(args.run_contacted_coverage_check),
        strict_contacted_coverage=bool(args.strict_contacted_coverage),
        max_seed_email_sample=max(1, int(resolved["max_seed_email_sample"])),
        max_seed_institutions=max(1, int(resolved["max_seed_institutions"])),
        max_seed_domains=max(1, int(resolved["max_seed_domains"])),
        use_file_search=bool(args.use_file_search),
        max_retries=max(1, int(max_retries_resolved)),
        initial_backoff_seconds=max(0.1, float(args.initial_backoff_seconds)),
        max_backoff_seconds=max(1.0, float(args.max_backoff_seconds)),
        fallback_sector=str(args.fallback_sector) if args.fallback_sector else None,
        daily_mode=bool(args.daily_mode),
        progress_callback=progress.emit,
        research_mode=research_mode,
        research_output_mode=str(args.research_output_mode),
        tpm_safe=bool(args.tpm_safe),
    )
    print(f"Wrote: {artifacts.out_dir}")
    print(f"Review summary: {artifacts.review_summary_md}")
    print("Ready for review; no live send performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
