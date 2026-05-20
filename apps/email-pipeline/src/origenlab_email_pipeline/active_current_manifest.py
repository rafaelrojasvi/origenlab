"""Validate reports/out/active/current/manifest.json (read-only guardrails)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ALLOWED_CAMPAIGN_MODES = frozenset(
    {"equipment_first", "volume_marketing", "precision_leads", "none"}
)

_OPERATOR_QUEUE_PREFIX = "equipment_first_operator_queue_"
_STALE_CROSSCHECK_FRAGMENT = "buyer_opportunity_crosscheck"


def _stale_paths_from_manifest(manifest: dict[str, Any]) -> set[str]:
    return {
        str(entry.get("path") or "").strip()
        for entry in (manifest.get("stale_files") or [])
        if entry.get("path")
    }


def _is_forbidden_queue_name(name: str) -> bool:
    lower = name.lower()
    return _STALE_CROSSCHECK_FRAGMENT in lower or "tender_buyer_outreach_queue" in lower


def resolve_equipment_operator_queue_csv(active_current: Path, manifest: dict[str, Any]) -> Path | None:
    """Pick canonical equipment_first_operator_queue CSV; never stale crosscheck artifacts."""
    stale = _stale_paths_from_manifest(manifest)
    active_current = active_current.resolve()

    for rel in manifest.get("canonical_files") or []:
        rel_s = str(rel).strip()
        if not rel_s or rel_s in stale:
            continue
        if _is_forbidden_queue_name(rel_s):
            continue
        if not (rel_s.startswith(_OPERATOR_QUEUE_PREFIX) and rel_s.endswith(".csv")):
            continue
        candidate = active_current / rel_s
        if candidate.is_file():
            return candidate

    globs = sorted(active_current.glob(f"{_OPERATOR_QUEUE_PREFIX}*.csv"))
    for candidate in reversed(globs):
        if candidate.name in stale or _is_forbidden_queue_name(candidate.name):
            continue
        return candidate
    return None


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
    warn_text = " ".join(str(w) for w in warnings).lower()
    fastlab_notes = (manifest.get("operator_notes") or {}).get("fastlab") or {}
    fastlab_state = str(fastlab_notes.get("outreach_state") or "").strip().lower()
    if "fastlab" not in warn_text:
        errors.append("known_warnings must include a FastLab operator note")
    elif fastlab_state == "not_contacted":
        if "not_contacted" not in warn_text and "corrected" not in warn_text:
            errors.append(
                "known_warnings must document FastLab not_contacted correction "
                "(operator_notes.fastlab.outreach_state is not_contacted)"
            )
        if "manual_state_only_pending" in warn_text or "outreach_state contacted" in warn_text:
            errors.append("known_warnings must not include stale FastLab contacted/pending text")
    elif not (
        "pending" in warn_text
        or "verification" in warn_text
        or "contacted" in warn_text
    ):
        errors.append("known_warnings must describe FastLab outreach/Sent status")

    if manifest.get("postgres_status") != "parked":
        errors.append("postgres_status should be parked for daily ops")
    if manifest.get("api_status") != "parked":
        errors.append("api_status should be parked for daily ops")

    mode = manifest.get("campaign_mode")
    if mode is None:
        errors.append("campaign_mode is required")
    elif mode not in ALLOWED_CAMPAIGN_MODES:
        errors.append(
            f"campaign_mode must be one of {sorted(ALLOWED_CAMPAIGN_MODES)}; got {mode!r}"
        )

    focus = manifest.get("current_operator_focus")
    if not focus or not str(focus).strip():
        errors.append("current_operator_focus must be a non-empty string")

    rt = manifest.get("runtime_truth") or {}
    notes = str(rt.get("notes", "")).lower()
    if "postgres" not in notes and "optional" not in notes:
        errors.append("runtime_truth.notes should state Postgres/API are optional")

    return errors
