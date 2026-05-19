"""Validate reports/out/active/current/manifest.json (read-only guardrails)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"manifest missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_manifest(
    manifest: dict[str, Any],
    *,
    active_current: Path,
    active_root: Path | None = None,
) -> list[str]:
    """Return list of validation errors (empty if OK)."""
    errors: list[str] = []
    active_root = active_root or active_current.parent

    canonical = list(manifest.get("canonical_files") or [])
    stale_paths = {s.get("path") for s in (manifest.get("stale_files") or []) if s.get("path")}
    legacy_globs = list((manifest.get("legacy_do_not_use") or {}).get("artifacts_glob") or [])

    for rel in canonical:
        p = active_current / rel
        if not p.is_file():
            errors.append(f"canonical file missing: {rel} ({p})")

    for rel in manifest.get("auxiliary_files_active_parent") or []:
        p = active_root / rel
        if not p.is_file():
            errors.append(f"auxiliary file missing in active/: {rel} ({p})")

    overlap = set(canonical) & stale_paths
    if overlap:
        errors.append(f"stale paths must not be canonical: {sorted(overlap)}")

    for stale in stale_paths:
        if stale in canonical:
            continue
        if any(stale.startswith(glob.replace("*", "")) for glob in legacy_globs if "*" in glob):
            if stale in canonical:
                errors.append(f"legacy stale file listed as canonical: {stale}")

    if "buyer_opportunity_crosscheck_20260518.csv" in canonical:
        errors.append("buyer_opportunity_crosscheck_20260518.csv must not be canonical")

    warnings = manifest.get("known_warnings") or []
    fastlab_ok = any("fastlab" in str(w).lower() and "pending" in str(w).lower() for w in warnings) or any(
        "fastlab" in str(w).lower() and "verification" in str(w).lower() for w in warnings
    )
    if not fastlab_ok:
        errors.append("known_warnings must include FastLab pending verification until resolved")

    if manifest.get("postgres_status") != "parked":
        errors.append("postgres_status should be parked for daily ops")
    if manifest.get("api_status") != "parked":
        errors.append("api_status should be parked for daily ops")

    rt = manifest.get("runtime_truth") or {}
    notes = str(rt.get("notes", "")).lower()
    if "postgres" not in notes and "optional" not in notes:
        errors.append("runtime_truth.notes should state Postgres/API are optional")

    return errors
