"""Postgres dashboard mirror CLI builders and runners."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

from origenlab_email_pipeline.core.step_runner import run_step_sequence
from origenlab_email_pipeline.operator_cli.constants import (
    MIRROR_DASHBOARD_SYNC_SCRIPT,
    POSTGRES_ENV_VARS,
)
from origenlab_email_pipeline.operator_cli.paths import (
    mirror_dashboard_sync_script_path,
    normalize_passthrough_args,
    repo_root,
)


@dataclass(frozen=True)
class _MirrorDashboardStep:
    label: str
    argv: list[str]


def postgres_url_configured() -> bool:
    return any((os.environ.get(name) or "").strip() for name in POSTGRES_ENV_VARS)


def missing_postgres_env_message() -> str:
    names = " or ".join(POSTGRES_ENV_VARS)
    return (
        f"mirror-dashboard requires {names} to be set (see .env.example). "
        "Postgres mirror is optional reporting only — not send approval."
    )


def mirror_dashboard_uses_cloud_postgres_only() -> bool:
    """True when sync resolves ORIGENLAB_CLOUD_POSTGRES_URL (no scratch URL env set)."""
    if (os.environ.get("ORIGENLAB_POSTGRES_URL") or "").strip():
        return False
    if (os.environ.get("ALEMBIC_DATABASE_URL") or "").strip():
        return False
    return bool((os.environ.get("ORIGENLAB_CLOUD_POSTGRES_URL") or "").strip())


def mirror_dashboard_sync_safety_flags() -> list[str]:
    """Extra sync flags when target is non-scratch (e.g. Render cloud mirror)."""
    if mirror_dashboard_uses_cloud_postgres_only():
        return ["--allow-non-scratch-postgres"]
    return []


def parse_mirror_dashboard_wrapper_args(argv: list[str]) -> tuple[bool, bool, list[str]]:
    """Return ``(apply, alembic, passthrough)`` for mirror-dashboard wrapper flags."""
    apply = False
    alembic = False
    rest: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            rest.extend(argv[i:])
            break
        if tok in ("-h", "--help"):
            rest.append(tok)
            i += 1
            continue
        if tok == "--apply":
            apply = True
            i += 1
            continue
        if tok == "--alembic":
            alembic = True
            i += 1
            continue
        if tok.startswith("-"):
            raise ValueError(f"mirror-dashboard: unknown flag {tok!r}")
        rest.append(tok)
        i += 1
    if alembic and not apply:
        raise ValueError("mirror-dashboard --alembic requires --apply")
    return apply, alembic, normalize_passthrough_args(rest)


def build_mirror_dashboard_sync_argv(
    *,
    apply: bool,
    passthrough: list[str] | None = None,
) -> list[str]:
    cmd = [sys.executable, str(mirror_dashboard_sync_script_path())]
    if not apply:
        cmd.append("--dry-run")
    extra = normalize_passthrough_args(passthrough or [])
    for flag in mirror_dashboard_sync_safety_flags():
        if flag not in extra:
            cmd.append(flag)
    cmd.extend(extra)
    return cmd


def build_mirror_dashboard_alembic_argv() -> list[str]:
    return ["alembic", "-c", "alembic.ini", "upgrade", "head"]


def build_mirror_dashboard_argv_list(
    *,
    apply: bool = False,
    alembic: bool = False,
    passthrough: list[str] | None = None,
) -> list[list[str]]:
    """Build argv for optional alembic then sync (no subprocess)."""
    cmds: list[list[str]] = []
    if alembic:
        cmds.append(build_mirror_dashboard_alembic_argv())
    cmds.append(build_mirror_dashboard_sync_argv(apply=apply, passthrough=passthrough))
    return cmds


def _mirror_dashboard_step_label(argv: list[str]) -> str:
    if argv and argv[0] == "alembic":
        return "alembic upgrade head"
    return MIRROR_DASHBOARD_SYNC_SCRIPT


def _mirror_dashboard_steps(
    *,
    apply: bool = False,
    alembic: bool = False,
    passthrough: list[str] | None = None,
) -> list[_MirrorDashboardStep]:
    return [
        _MirrorDashboardStep(label=_mirror_dashboard_step_label(argv), argv=argv)
        for argv in build_mirror_dashboard_argv_list(
            apply=apply,
            alembic=alembic,
            passthrough=passthrough,
        )
    ]


def run_mirror_dashboard(
    *,
    apply: bool = False,
    alembic: bool = False,
    passthrough: list[str] | None = None,
) -> int:
    if not postgres_url_configured():
        print(missing_postgres_env_message(), file=sys.stderr)
        return 2
    cwd = str(repo_root())

    def _run_step(step: _MirrorDashboardStep) -> int:
        proc = subprocess.run(step.argv, cwd=cwd, check=False)
        return int(proc.returncode)

    return run_step_sequence(
        _mirror_dashboard_steps(apply=apply, alembic=alembic, passthrough=passthrough),
        _run_step,
        prefix="[mirror-dashboard]",
    )


def print_mirror_dashboard_help() -> None:
    print(
        "mirror-dashboard — Postgres dashboard mirror (EXPERIMENTAL_PARKED)\n\n"
        "  uv run origenlab mirror-dashboard              # dry-run sync (default)\n"
        "  uv run origenlab mirror-dashboard --apply      # write Postgres mirror\n"
        "  uv run origenlab mirror-dashboard --alembic --apply\n"
        "  uv run origenlab mirror-dashboard -- --only mart --json-out path\n\n"
        f"Requires {' or '.join(POSTGRES_ENV_VARS)}.\n"
        "When only ORIGENLAB_CLOUD_POSTGRES_URL is set, adds --allow-non-scratch-postgres "
        "(Render/cloud target).\n"
        f"Advanced: {MIRROR_DASHBOARD_SYNC_SCRIPT}\n"
    )
