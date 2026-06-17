"""Unit tests for scripts/remote_response_audit.py helpers (no network)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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
main = _remote.main
require_error_envelope = _remote.require_error_envelope
require_meta_items = _remote.require_meta_items
require_request_id_header = _remote.require_request_id_header
scan_forbidden_leaks_in_text = _remote.scan_forbidden_leaks_in_text


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
