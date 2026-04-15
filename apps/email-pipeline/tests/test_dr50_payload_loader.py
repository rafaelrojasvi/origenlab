"""Tests for versioned DR50 JSON payload + manifest verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from origenlab_email_pipeline.dr50_payload_loader import Dr50PayloadError, load_verified_dr50_rows

REPO = Path(__file__).resolve().parents[1]
_DEFAULT_DATA = REPO / "scripts" / "leads" / "campaigns" / "data"
_MANIFEST = _DEFAULT_DATA / "dr50_manifest_v1.json"


def test_load_verified_dr50_rows_happy_path(tmp_path: Path) -> None:
    """Self-contained payload: CI must not rely on gitignored or absent repo files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    payload_rows = [{"id_lead": 608694, "dr_confidence": "alta"}]
    raw = json.dumps(payload_rows, ensure_ascii=False, indent=2).encode("utf-8")
    payload_path = data_dir / "dr50_payload_v1.json"
    payload_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = {
        "payload_file": "dr50_payload_v1.json",
        "expected_sha256": digest,
        "row_count": 1,
    }
    (data_dir / "dr50_manifest_v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = load_verified_dr50_rows(data_dir=data_dir)
    assert len(rows) == 1
    assert int(rows[0]["id_lead"]) == 608694


@pytest.mark.skipif(not _MANIFEST.is_file(), reason="Repo DR50 data not present (optional checkout)")
def test_load_verified_dr50_rows_repo_payload_when_present() -> None:
    """Integration: real committed payload under scripts/leads/campaigns/data/ when available."""
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
