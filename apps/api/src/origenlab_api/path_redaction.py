"""Redact absolute local filesystem paths for operator-facing API responses."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

_PATH_LIKE_KEYS = frozenset(
    {
        "active_current_dir",
        "queue_dir",
        "published_queue",
        "candidate_audit",
        "api_queue",
        "audit_path",
        "allowlist_path",
        "out_dir",
        "sqlite_path",
        "path",
    }
)
_PATH_KEY_SUFFIXES = ("_path", "_dir", "_queue", "_audit", "_file")
_KNOWN_PLACEHOLDER_PATHS: dict[str, tuple[str, str]] = {
    "<local-active-current>": ("current", "directory"),
    "<unset>": ("unset", "directory"),
}
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[/\\]")

NESTED_AUTOMATION_SECTIONS = (
    "daily_core",
    "mail_auto_refresh",
    "dashboard_auto_mirror",
    "chilecompra_equipment_auto_refresh",
    "ndr_pending_review",
    "cron",
)


def is_path_like_key(key: str) -> bool:
    if key in _PATH_LIKE_KEYS:
        return True
    return any(key.endswith(suffix) for suffix in _PATH_KEY_SUFFIXES)


def is_absolute_path_string(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if text.startswith(("/", "~")):
        return True
    return _WINDOWS_DRIVE_RE.match(text) is not None


def _basename_of_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    name = PurePosixPath(normalized).name
    return name or normalized.rstrip("/").split("/")[-1] or value.strip()


def _path_kind(basename: str) -> str:
    if "." in basename and not basename.startswith("."):
        return "file"
    return "directory"


def redact_path_string(value: str) -> dict[str, Any] | None:
    """Return safe path metadata (basename + kind only; no parent directories)."""
    text = (value or "").strip()
    if not text:
        return None

    placeholder = _KNOWN_PLACEHOLDER_PATHS.get(text)
    if placeholder is not None:
        basename, kind = placeholder
        return {"redacted": True, "basename": basename, "kind": kind}

    if not is_absolute_path_string(text):
        return None

    basename = _basename_of_path(text)
    if not basename:
        return None
    return {"redacted": True, "basename": basename, "kind": _path_kind(basename)}


def collect_path_info(mapping: dict[str, Any]) -> dict[str, Any]:
    """Collect redacted path metadata for known path-like keys in a section."""
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        if key == "path_info" or not isinstance(value, str):
            continue
        if not is_path_like_key(key):
            continue
        info = redact_path_string(value)
        if info is not None:
            out[key] = info
    return out


def enrich_automation_status_paths(payload: dict[str, Any]) -> dict[str, Any]:
    """Add additive redacted path companion fields; preserve legacy raw path strings."""
    enriched = dict(payload)

    active_dir = enriched.get("active_current_dir")
    if isinstance(active_dir, str):
        info = redact_path_string(active_dir)
        if info is not None:
            enriched["active_current_dir_info"] = info

    for section_key in NESTED_AUTOMATION_SECTIONS:
        section = enriched.get(section_key)
        if not isinstance(section, dict):
            continue
        path_info = collect_path_info(section)
        if not path_info:
            continue
        merged = dict(section)
        merged["path_info"] = path_info
        enriched[section_key] = merged

    enriched["path_redaction_applied"] = True
    return enriched
