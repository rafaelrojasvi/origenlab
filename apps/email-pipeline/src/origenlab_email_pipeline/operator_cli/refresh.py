"""Refresh-dashboard workflow orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from origenlab_email_pipeline.core.step_runner import run_step_sequence
from origenlab_email_pipeline.operator_cli.constants import REFRESH_DASHBOARD_USAGE

SubcommandRunner = Callable[..., int]


@dataclass(frozen=True)
class RefreshDashboardStep:
    """One step in the refresh-dashboard workflow."""

    label: str
    command: str
    passthrough: tuple[str, ...] = ()
    mirror_apply: bool = False
    mirror_alembic: bool = False


@dataclass(frozen=True)
class RefreshDashboardOptions:
    apply: bool = False
    no_mirror: bool = False
    mirror_dry_run: bool = False
    skip_ingest: bool = False
    since_days: int | None = None


def parse_refresh_dashboard_wrapper_args(argv: list[str]) -> RefreshDashboardOptions:
    apply = False
    no_mirror = False
    mirror_dry_run = False
    skip_ingest = False
    since_days: int | None = None
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in ("-h", "--help"):
            i += 1
            continue
        if tok == "--apply":
            apply = True
            i += 1
            continue
        if tok == "--no-mirror":
            no_mirror = True
            i += 1
            continue
        if tok == "--mirror-dry-run":
            mirror_dry_run = True
            i += 1
            continue
        if tok == "--skip-ingest":
            skip_ingest = True
            i += 1
            continue
        if tok == "--since-days":
            if i + 1 >= len(argv):
                raise ValueError("refresh-dashboard --since-days requires a value")
            since_days = int(argv[i + 1])
            i += 2
            continue
        if tok.startswith("-"):
            raise ValueError(f"refresh-dashboard: unknown flag {tok!r}")
        raise ValueError(f"refresh-dashboard: unexpected argument {tok!r}")
    if mirror_dry_run and no_mirror:
        raise ValueError("refresh-dashboard: --mirror-dry-run and --no-mirror are mutually exclusive")
    if since_days is not None and since_days < 1:
        raise ValueError("refresh-dashboard --since-days must be a positive integer")
    return RefreshDashboardOptions(
        apply=apply,
        no_mirror=no_mirror,
        mirror_dry_run=mirror_dry_run,
        skip_ingest=skip_ingest,
        since_days=since_days,
    )


def build_refresh_dashboard_steps(options: RefreshDashboardOptions) -> list[RefreshDashboardStep]:
    """Build ordered workflow steps from options (used for plan and apply)."""
    steps: list[RefreshDashboardStep] = []
    if not options.skip_ingest:
        ingest_pt: tuple[str, ...] = ()
        ingest_label = "gmail-ingest"
        if options.since_days is not None:
            ingest_pt = ("--", "--since-days", str(options.since_days))
            ingest_label = f"gmail-ingest -- --since-days {options.since_days}"
        steps.append(
            RefreshDashboardStep(label=ingest_label, command="gmail-ingest", passthrough=ingest_pt)
        )
    steps.extend(
        [
            RefreshDashboardStep(
                label="build-mart -- --rebuild",
                command="build-mart",
                passthrough=("--", "--rebuild"),
            ),
            RefreshDashboardStep(label="build-commercial-intel", command="build-commercial-intel"),
            RefreshDashboardStep(label="refresh-safety", command="refresh-safety"),
            RefreshDashboardStep(label="ndr-review", command="ndr-review"),
            RefreshDashboardStep(label="post-send-digest", command="post-send-digest"),
            RefreshDashboardStep(label="status", command="status"),
        ]
    )
    if not options.no_mirror:
        if options.mirror_dry_run:
            steps.append(RefreshDashboardStep(label="mirror-dashboard", command="mirror-dashboard"))
        else:
            steps.append(
                RefreshDashboardStep(
                    label="mirror-dashboard --apply",
                    command="mirror-dashboard",
                    mirror_apply=True,
                )
            )
    return steps


def refresh_dashboard_usage_line(*flags: str) -> str:
    """Example command line for plan/help; always keeps a space before flags."""
    return f"  {REFRESH_DASHBOARD_USAGE} {' '.join(flags)}"


def print_refresh_dashboard_plan(steps: list[RefreshDashboardStep], options: RefreshDashboardOptions) -> None:
    total = len(steps)
    print("refresh-dashboard — plan only (no Gmail ingest, mart rebuild, commercial intel, or Postgres writes)\n")
    print(f"Planned steps ({total}) when you pass --apply:")
    for i, step in enumerate(steps, 1):
        note = ""
        if step.command == "build-mart":
            note = "  # break-glass: deletes mart tables"
        print(f"  {i}/{total} {step.label}{note}")
    print("\nVariants:")
    print(refresh_dashboard_usage_line("--apply"))
    print(refresh_dashboard_usage_line("--apply", "--no-mirror"))
    print(refresh_dashboard_usage_line("--apply", "--mirror-dry-run"))
    print(refresh_dashboard_usage_line("--apply", "--skip-ingest"))
    if options.since_days is None:
        print(refresh_dashboard_usage_line("--apply", "--since-days", "14"))
    print("\nNo alembic in this workflow; use mirror-dashboard --alembic --apply separately if needed.")


def print_refresh_dashboard_help() -> None:
    print(
        "refresh-dashboard — orchestrated operator stack refresh\n\n"
        f"{refresh_dashboard_usage_line()}                    # plan only (default)\n"
        f"{refresh_dashboard_usage_line('--apply')}            # full workflow + mirror apply\n"
        f"{refresh_dashboard_usage_line('--apply', '--no-mirror')}\n"
        f"{refresh_dashboard_usage_line('--apply', '--mirror-dry-run')}\n"
        f"{refresh_dashboard_usage_line('--apply', '--skip-ingest')}\n"
        f"{refresh_dashboard_usage_line('--apply', '--since-days', '14')}\n\n"
        "Includes build-mart -- --rebuild (break-glass) and incremental build-commercial-intel. "
        "No alembic in this workflow.\n"
    )


def run_refresh_dashboard(
    options: RefreshDashboardOptions,
    runner: SubcommandRunner | None = None,
) -> int:
    """Run refresh-dashboard plan or apply workflow via existing CLI subcommands."""
    from origenlab_email_pipeline.operator_cli.runner import run_subcommand

    execute = runner or run_subcommand
    steps = build_refresh_dashboard_steps(options)
    if not options.apply:
        print_refresh_dashboard_plan(steps, options)
        return 0

    def _run_step(step: RefreshDashboardStep) -> int:
        return execute(
            step.command,
            list(step.passthrough) or None,
            mirror_apply=step.mirror_apply,
            mirror_alembic=step.mirror_alembic,
        )

    return run_step_sequence(steps, _run_step, prefix="[refresh-dashboard]")
