"""Postgres dashboard mirror CLI builders and runners."""

from __future__ import annotations

import os
import subprocess
import sys

from origenlab_email_pipeline.operator_cli.constants import (
    MIRROR_DASHBOARD_SYNC_SCRIPT,
    POSTGRES_ENV_VARS,
)
from origenlab_email_pipeline.operator_cli.paths import (
    mirror_dashboard_sync_script_path,
    normalize_passthrough_args,
    repo_root,
)


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
    for cmd in build_mirror_dashboard_argv_list(apply=apply, alembic=alembic, passthrough=passthrough):
        proc = subprocess.run(cmd, cwd=cwd, check=False)
        if proc.returncode != 0:
            return int(proc.returncode)
    return 0


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
