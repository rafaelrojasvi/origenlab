"""Tests for versioned DR50 JSON payload + manifest verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from origenlab_email_pipeline.dr50_payload_loader import Dr50PayloadError, load_verified_dr50_rows

REPO = Path(__file__).resolve().parents[1]


def test_load_verified_dr50_rows_happy_path() -> None:
    rows = load_verified_dr50_rows(repo_root=REPO)
    assert len(rows) == 23
    ids = [int(r["id_lead"]) for r in rows]
    assert len(ids) == len(set(ids))


def test_load_verified_dr50_rows_checksum_mismatch(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    payload = data_dir / "dr50_payload_v1.json"
    payload.write_text("[]\n", encoding="utf-8")
    manifest = {
        "payload_file": "dr50_payload_v1.json",
        "expected_sha256": "0" * 64,
        "row_count": 0,
    }
    (data_dir / "dr50_manifest_v1.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    with pytest.raises(Dr50PayloadError, match="checksum mismatch"):
        load_verified_dr50_rows(data_dir=data_dir)
