"""Unit tests for scripts/remote_response_audit.py helpers (no network)."""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "remote_response_audit.py"
_SPEC = importlib.util.spec_from_file_location("remote_response_audit", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_remote = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _remote
_SPEC.loader.exec_module(_remote)

RemoteAuditError = _remote.RemoteAuditError
RemoteResponse = _remote.RemoteResponse
SKIP_MESSAGE = _remote.SKIP_MESSAGE
audit_response = _remote.audit_response
cf_credentials_from_env = _remote.cf_credentials_from_env
fetch_get = _remote.fetch_get
main = _remote.main
require_equipment_current_contract = _remote.require_equipment_current_contract
require_error_envelope = _remote.require_error_envelope
require_meta_items = _remote.require_meta_items
require_request_id_header = _remote.require_request_id_header
request_timeout_seconds = _remote.request_timeout_seconds
scan_forbidden_leaks_in_text = _remote.scan_forbidden_leaks_in_text


def _valid_equipment_body(*, duplicate_key: bool = False, **overrides: object) -> dict[str, object]:
    items = [
        {
            "opportunity_key": "equipment:equipment_queue:lp-001",
            "priority_rank": 1,
            "codigo_licitacion": "LP-001",
        },
        {
            "opportunity_key": "equipment:equipment_queue:lp-001"
            if duplicate_key
            else "equipment:equipment_queue:lp-002",
            "priority_rank": 2,
            "codigo_licitacion": "LP-002",
        },
    ]
    body: dict[str, object] = {
        "meta": {
            "data_source": "postgres_mirror",
            "read_only": True,
            "count": len(items),
            "source_path": "equipment_first_operator_queue_20260518.csv",
            "source_path_info": {
                "redacted": True,
                "basename": "equipment_first_operator_queue_20260518.csv",
                "kind": "file",
            },
            "reduced_mode": False,
            "note": "",
        },
        "items": items,
    }
    body.update(overrides)
    return body


def test_require_request_id_header_missing_fails() -> None:
    try:
        require_request_id_header({})
    except RemoteAuditError as exc:
        assert "x-request-id" in str(exc).lower()
    else:
        raise AssertionError("expected RemoteAuditError")


def test_require_request_id_header_accepts_lowercase_header() -> None:
    assert require_request_id_header({"x-request-id": "abc123"}) == "abc123"


def test_scan_forbidden_leaks_in_text_detects_home_path() -> None:
    hits = scan_forbidden_leaks_in_text('{"sqlite_path":"/home/ops/data.sqlite"}')
    assert "/home/" in hits


def test_scan_forbidden_leaks_in_text_empty_when_safe() -> None:
    assert scan_forbidden_leaks_in_text('{"ok":true,"meta":{"read_only":true}}') == []


def test_require_meta_items_requires_meta_and_items() -> None:
    try:
        require_meta_items({"items": []})
    except RemoteAuditError as exc:
        assert "meta" in str(exc).lower()
    else:
        raise AssertionError("expected RemoteAuditError")


def test_require_meta_items_accepts_valid_list_shape() -> None:
    require_meta_items({"meta": {"read_only": True}, "items": []})


def test_require_equipment_current_contract_accepts_valid_response() -> None:
    require_equipment_current_contract(_valid_equipment_body())  # type: ignore[arg-type]


def test_require_equipment_current_contract_missing_opportunity_key_fails() -> None:
    body = _valid_equipment_body()
    body["items"][0].pop("opportunity_key")  # type: ignore[index]
    with pytest.raises(RemoteAuditError, match="opportunity_key"):
        require_equipment_current_contract(body)  # type: ignore[arg-type]


def test_require_equipment_current_contract_duplicate_opportunity_key_fails() -> None:
    with pytest.raises(RemoteAuditError, match="duplicate opportunity_key"):
        require_equipment_current_contract(_valid_equipment_body(duplicate_key=True))  # type: ignore[arg-type]


def test_require_equipment_current_contract_meta_count_mismatch_fails() -> None:
    body = _valid_equipment_body()
    body["meta"]["count"] = 99  # type: ignore[index]
    with pytest.raises(RemoteAuditError, match="meta.count"):
        require_equipment_current_contract(body)  # type: ignore[arg-type]


def test_require_equipment_current_contract_source_path_info_redacted_false_fails() -> None:
    body = _valid_equipment_body()
    body["meta"]["source_path_info"]["redacted"] = False  # type: ignore[index]
    with pytest.raises(RemoteAuditError, match="redacted"):
        require_equipment_current_contract(body)  # type: ignore[arg-type]


def test_require_equipment_current_contract_item_source_path_fails() -> None:
    body = _valid_equipment_body()
    body["items"][0]["source_path"] = "equipment_first_operator_queue_20260518.csv"  # type: ignore[index]
    with pytest.raises(RemoteAuditError, match="source_path"):
        require_equipment_current_contract(body)  # type: ignore[arg-type]


def test_audit_response_equipment_current_contract() -> None:
    body = _valid_equipment_body()
    response = RemoteResponse(
        status=200,
        headers={"x-request-id": "rid-1"},
        body_text=json.dumps(body),
    )
    audit_response(
        "GET /opportunities/equipment?limit=3",
        response,
        "/opportunities/equipment?limit=3",
        expect_success=True,
    )


def test_fetch_get_timeout_raises_remote_audit_error_without_traceback() -> None:
    def _timeout(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("timed out")

    with patch("urllib.request.urlopen", side_effect=_timeout):
        with pytest.raises(RemoteAuditError, match="timed out") as exc_info:
            fetch_get("https://api.origenlab.cl/opportunities/equipment?limit=3", {})
    assert "Traceback" not in str(exc_info.value)


def test_fetch_get_urlerror_raises_remote_audit_error() -> None:
    def _url_error(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("connection refused")

    with patch("urllib.request.urlopen", side_effect=_url_error):
        with pytest.raises(RemoteAuditError, match="connection refused"):
            fetch_get("https://api.origenlab.cl/health", {})


def test_request_timeout_seconds_reads_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORIGENLAB_REMOTE_AUDIT_TIMEOUT_SECONDS", "45")
    assert request_timeout_seconds() == 45
    monkeypatch.setenv("ORIGENLAB_REMOTE_AUDIT_TIMEOUT_SECONDS", "not-a-number")
    assert request_timeout_seconds() == _remote.REQUEST_TIMEOUT_SECONDS


def test_require_error_envelope_requires_request_id_matching_header() -> None:
    body = {
        "error": {
            "code": "validation_error",
            "message": "Invalid",
            "details": {},
            "request_id": "abc123",
        }
    }
    try:
        require_error_envelope(body, request_id_header="different")
    except RemoteAuditError as exc:
        assert "match" in str(exc).lower()
    else:
        raise AssertionError("expected RemoteAuditError")


def test_require_error_envelope_accepts_matching_request_id() -> None:
    body = {
        "error": {
            "code": "not_found",
            "message": "Missing",
            "details": {},
            "request_id": "req-1",
        }
    }
    assert require_error_envelope(body, request_id_header="req-1") == "req-1"


def test_audit_response_success_list_shape() -> None:
    body = {"meta": {"count": 0}, "items": []}
    response = RemoteResponse(
        status=200,
        headers={"x-request-id": "rid-1"},
        body_text=json.dumps(body),
    )
    audit_response(
        "GET /cases/warm?limit=3",
        response,
        "/cases/warm?limit=3",
        expect_success=True,
    )


def test_audit_response_fails_on_forbidden_leak() -> None:
    response = RemoteResponse(
        status=200,
        headers={"x-request-id": "rid-1"},
        body_text='{"path":"/home/ops/file"}',
    )
    with pytest.raises(RemoteAuditError, match="/home/"):
        audit_response("GET /health", response, "/health", expect_success=True)


def test_main_skips_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    assert main() == 0
    captured = capsys.readouterr()
    assert SKIP_MESSAGE in captured.out
