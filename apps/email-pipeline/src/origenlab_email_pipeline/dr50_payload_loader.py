"""Load versioned **DR50** (deep-research) contact JSON with SHA256 verification.

Payload lives under ``scripts/leads/campaigns/data/``; consumed by hunt/reconcile utilities — not a general
configuration layer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class Dr50PayloadError(ValueError):
    """Raised when manifest or payload fails integrity checks."""


def default_dr50_data_dir(repo_root: Path) -> Path:
    return repo_root / "scripts" / "leads" / "campaigns" / "data"


def load_verified_dr50_rows(
    *,
    data_dir: Path | None = None,
    repo_root: Path | None = None,
    manifest_name: str = "dr50_manifest_v1.json",
) -> list[dict[str, Any]]:
    """Load DR50 rows from JSON after verifying SHA256 against manifest.

    ``data_dir`` defaults to ``<repo_root>/scripts/leads/campaigns/data`` when ``repo_root`` is set.
    """
    if data_dir is None:
        if repo_root is None:
            raise Dr50PayloadError("Provide data_dir or repo_root")
        data_dir = default_dr50_data_dir(repo_root)
    manifest_path = data_dir / manifest_name
    if not manifest_path.is_file():
        raise Dr50PayloadError(f"Missing manifest: {manifest_path}")
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_file = manifest.get("payload_file")
    expected = manifest.get("expected_sha256")
    row_count = manifest.get("row_count")
    if not payload_file or not expected or row_count is None:
        raise Dr50PayloadError("Manifest missing payload_file, expected_sha256, or row_count")
    payload_path = data_dir / str(payload_file)
    if not payload_path.is_file():
        raise Dr50PayloadError(f"Missing payload file: {payload_path}")
    raw = payload_path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != str(expected).lower():
        raise Dr50PayloadError(
            f"DR50 payload checksum mismatch: expected {expected}, got {actual} ({payload_path})"
        )
    rows = json.loads(raw.decode("utf-8"))
    if not isinstance(rows, list):
        raise Dr50PayloadError("Payload must be a JSON array")
    if len(rows) != int(row_count):
        raise Dr50PayloadError(f"Expected {row_count} rows, got {len(rows)}")
    seen: set[int] = set()
    for r in rows:
        if not isinstance(r, dict) or "id_lead" not in r:
            raise Dr50PayloadError("Each row must be an object with id_lead")
        lid = int(r["id_lead"])
        if lid in seen:
            raise Dr50PayloadError(f"Duplicate id_lead in payload: {lid}")
        seen.add(lid)
    return rows
