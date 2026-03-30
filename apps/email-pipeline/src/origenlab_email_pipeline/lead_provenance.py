"""Factual provenance for leads client pack, operational stack manifests, and QA correlation.

Reads/writes paths under ``reports/out/active/`` and env vars set by ``run_leads_operational_stack.sh``;
does not infer business outcomes — only filesystem and env facts for ``run_id`` / DB path alignment."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

# Written by scripts/leads/write_operational_stack_provenance.py at stack completion.
OPERATIONAL_STACK_LAST_RUN_RELATIVE = Path("reports/out/active/operational_stack_last_run.json")
# One JSON file per operational run_id (append-only archive; same payload as last_run snapshot).
OPERATIONAL_RUN_MANIFESTS_RELATIVE = Path("reports/out/active/operational_run_manifests")

# Exported by run_leads_operational_stack.sh for the whole stack (pack, gate, manifest).
OPERATIONAL_RUN_ID_ENV = "ORIGENLAB_LEADS_OPERATIONAL_RUN_ID"
OPERATIONAL_STACK_STARTED_AT_ENV = "ORIGENLAB_LEADS_OPERATIONAL_STACK_STARTED_AT"

PROVENANCE_SCHEMA_VERSION = 2
# Stack manifest / last-run file uses the same version as pack provenance for this repo generation.
MANIFEST_SCHEMA_VERSION = PROVENANCE_SCHEMA_VERSION


def operational_stack_last_run_path(repo_root: Path) -> Path:
    return (repo_root / OPERATIONAL_STACK_LAST_RUN_RELATIVE).resolve()


def operational_run_manifest_path(repo_root: Path, run_id: str) -> Path:
    safe = run_id.replace("/", "_").replace("\\", "_").strip()
    if not safe:
        raise ValueError("run_id must be non-empty")
    return (repo_root / OPERATIONAL_RUN_MANIFESTS_RELATIVE / f"{safe}.json").resolve()


def read_operational_run_id_from_env() -> str | None:
    raw = (os.environ.get(OPERATIONAL_RUN_ID_ENV) or "").strip()
    return raw if raw else None


def read_operational_stack_last_run(repo_root: Path) -> dict[str, Any] | None:
    """Return last stack record JSON, or None if missing/unreadable."""
    p = operational_stack_last_run_path(repo_root)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def try_git_revision(repo_root: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if r.returncode == 0 and (s := r.stdout.strip()):
            return s
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def build_operational_stack_manifest_payload(
    *,
    repo_root: Path,
    run_id: str,
    started_at_utc: str,
    completed_at_utc: str,
    reconcile_mode: str,
    skip_fetch: bool,
    skip_focus: bool,
    skip_pack: bool,
    skip_gate: bool,
    publish_gate_exit_code: int | None,
    db_path_resolved: Path,
) -> dict[str, Any]:
    """Factual manifest for one operational stack run (written to last_run + per-run archive)."""
    gate_executed = not skip_gate
    if not gate_executed:
        gate_passed: bool | None = None
        gate_exit: int | None = None
    else:
        gate_exit = publish_gate_exit_code
        gate_passed = publish_gate_exit_code == 0 if publish_gate_exit_code is not None else None

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "started_at_utc": started_at_utc,
        "completed_at_utc": completed_at_utc,
        "invoking_script": "run_leads_operational_stack.sh",
        "db_path_resolved": str(db_path_resolved.resolve()),
        "reconcile_mode": reconcile_mode,
        "skipped": {
            "fetch": skip_fetch,
            "weekly_focus": skip_focus,
            "client_pack": skip_pack,
            "publish_gate": skip_gate,
        },
        "publish_gate": {
            "executed": gate_executed,
            "passed": gate_passed,
            "exit_code": gate_exit,
        },
        "git_revision": try_git_revision(repo_root),
        "ingest": {
            "chilecompra_file_env_set": bool((os.environ.get("LEADS_CHILECOMPRA_FILE") or "").strip()),
            "inn_file_env_set": bool((os.environ.get("LEADS_INN_FILE") or "").strip()),
            "corfo_file_env_set": bool((os.environ.get("LEADS_CORFO_FILE") or "").strip()),
        },
    }


def build_client_pack_provenance(
    *,
    repo_root: Path,
    db_path_configured: str | None,
    db_path_resolved: Path,
    generated_at_utc: str,
    operational_run_id: str | None = None,
) -> dict[str, Any]:
    """Provenance block for client pack summary.json (additive; honest about limits)."""
    run_id = operational_run_id if operational_run_id is not None else read_operational_run_id_from_env()
    stack = read_operational_stack_last_run(repo_root)
    git_rev = try_git_revision(repo_root)
    res = db_path_resolved.resolve()
    caveat_parts = [
        "last_operational_stack is the latest record from run_leads_operational_stack.sh on disk; "
        "it does not prove this pack was produced in that same run unless you chained commands without "
        "other pack builds in between. Provenance aids traceability; it does not replace publish_gate.",
    ]
    if run_id:
        caveat_parts.append(
            "This summary.json is written before publish_gate in run_leads_operational_stack.sh; "
            "publish_gate.passed for the same operational_run_id is recorded only in "
            "operational_stack_last_run.json after the stack finishes. "
            "publish_gate_validated_this_artifact is always false here."
        )
    out: dict[str, Any] = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "db_path": db_path_configured,
        "db_path_resolved": str(res),
        "git_revision": git_rev,
        "operational_run_id": run_id,
        "publish_gate_validated_this_artifact": False,
        "operational_stack_last_run_present": stack is not None,
        "upstream_reconcile_mode": (
            stack.get("reconcile_mode")
            if stack and isinstance(stack.get("reconcile_mode"), str)
            else "unknown"
        ),
        "publish_gate_skipped_in_last_stack": _publish_gate_skipped(stack),
        "last_operational_stack": stack,
        "caveat": " ".join(caveat_parts),
    }
    return out


def _publish_gate_skipped(stack: dict[str, Any] | None) -> bool | None:
    if not stack:
        return None
    sk = stack.get("skipped")
    if not isinstance(sk, dict):
        return None
    v = sk.get("publish_gate")
    if isinstance(v, bool):
        return v
    return None
