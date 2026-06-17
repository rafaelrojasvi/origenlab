"""Unit tests for operator automation path redaction helpers."""

from __future__ import annotations

import json

import pytest

from origenlab_api.path_redaction import (
    collect_path_info,
    enrich_automation_status_paths,
    enrich_operator_status_paths,
    is_absolute_path_string,
    is_path_like_key,
    redact_path_string,
    redact_path_value,
)


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("active_current_dir", True),
        ("published_queue", True),
        ("candidate_audit", True),
        ("queue_dir", True),
        ("sqlite_path", True),
        ("custom_audit", True),
        ("custom_file", True),
        ("verdict", False),
        ("published_rows", False),
    ],
)
def test_is_path_like_key(key: str, expected: bool) -> None:
    assert is_path_like_key(key) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/home/user/reports/out/active/current", True),
        ("/mnt/data/queue.csv", True),
        ("C:\\Users\\ops\\queue.csv", True),
        ("~/reports/current", True),
        ("relative/path.csv", False),
        ("<local-active-current>", False),
        ("", False),
    ],
)
def test_is_absolute_path_string(value: str, expected: bool) -> None:
    assert is_absolute_path_string(value) is expected


def test_redact_path_string_file() -> None:
    info = redact_path_string(
        "/home/ops/reports/out/active/current/equipment_first_operator_queue_20260616.csv"
    )
    assert info == {
        "redacted": True,
        "basename": "equipment_first_operator_queue_20260616.csv",
        "kind": "file",
    }


def test_redact_path_string_directory() -> None:
    info = redact_path_string("/home/ops/reports/out/active/current")
    assert info == {"redacted": True, "basename": "current", "kind": "directory"}


def test_redact_path_string_placeholder() -> None:
    info = redact_path_string("<local-active-current>")
    assert info == {"redacted": True, "basename": "current", "kind": "directory"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/home/ops/reports/out/active/current/equipment_first_operator_queue_20260616.csv", "equipment_first_operator_queue_20260616.csv"),
        ("/home/ops/reports/out/active/current", "current"),
        ("<local-active-current>", "current"),
        ("relative/path.csv", "relative/path.csv"),
        ("", ""),
    ],
)
def test_redact_path_value(value: str, expected: str) -> None:
    assert redact_path_value(value) == expected


def test_enrich_operator_status_paths_redacts_sqlite_path() -> None:
    payload = {
        "verdict": "READY",
        "sqlite_path": "/home/ops/data/emails.sqlite",
        "daily_core_run": {"exists": False, "path": "/home/ops/active/current/daily_core_run_manifest.json"},
    }
    enriched = enrich_operator_status_paths(payload)
    assert enriched["sqlite_path"] == "emails.sqlite"
    assert enriched["sqlite_path_info"] == {
        "redacted": True,
        "basename": "emails.sqlite",
        "kind": "file",
    }
    assert enriched["daily_core_run"]["path"] == "daily_core_run_manifest.json"
    assert "/home/" not in json.dumps(enriched)


def test_collect_path_info_skips_non_path_keys() -> None:
    section = {
        "published_rows": 7,
        "published_queue": "/tmp/equipment_first_operator_queue_20260616.csv",
        "candidate_audit": "/tmp/chilecompra_equipment_candidate_audit_20260616.csv",
    }
    path_info = collect_path_info(section)
    assert set(path_info.keys()) == {"published_queue", "candidate_audit"}
    assert path_info["published_queue"]["basename"] == "equipment_first_operator_queue_20260616.csv"


def test_enrich_automation_status_paths_redacts_legacy_fields() -> None:
    payload = {
        "generated_at_utc": "2026-06-16T12:00:00+00:00",
        "active_current_dir": "/home/ops/reports/out/active/current",
        "verdict": "healthy",
        "chilecompra_equipment_auto_refresh": {
            "published_queue": "/home/ops/reports/out/active/current/equipment_first_operator_queue_20260616.csv",
            "candidate_audit": "/home/ops/reports/out/active/current/chilecompra_equipment_candidate_audit_20260616.csv",
        },
    }
    enriched = enrich_automation_status_paths(payload)

    assert enriched["active_current_dir"] == "current"
    assert enriched["path_redaction_applied"] is True
    assert enriched["active_current_dir_info"]["basename"] == "current"

    chilecompra = enriched["chilecompra_equipment_auto_refresh"]
    assert chilecompra["published_queue"] == "equipment_first_operator_queue_20260616.csv"
    assert chilecompra["candidate_audit"] == "chilecompra_equipment_candidate_audit_20260616.csv"
    path_info = chilecompra["path_info"]
    assert path_info["published_queue"]["basename"] == "equipment_first_operator_queue_20260616.csv"
    assert path_info["candidate_audit"]["basename"] == "chilecompra_equipment_candidate_audit_20260616.csv"

    blob = json.dumps(enriched)
    for forbidden in ("/home/", "/mnt/", "\\", "postgres://", "ORIGENLAB_"):
        assert forbidden not in blob
