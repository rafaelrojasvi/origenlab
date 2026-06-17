"""Unit tests for scripts/audit_response_contract.py helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_response_contract.py"
_SPEC = importlib.util.spec_from_file_location("audit_response_contract", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_audit = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _audit
_SPEC.loader.exec_module(_audit)

ContractAuditError = _audit.ContractAuditError
require_json_object = _audit.require_json_object
require_meta_items = _audit.require_meta_items
require_error_envelope = _audit.require_error_envelope
scan_forbidden_leaks = _audit.scan_forbidden_leaks


class _FakeResponse:
    def __init__(self, *, headers: dict[str, str]):
        self.headers = headers


def test_require_json_object_rejects_non_object() -> None:
    try:
        require_json_object(["not", "object"])
    except ContractAuditError as exc:
        assert "expected JSON object" in str(exc)
    else:
        raise AssertionError("expected ContractAuditError")


def test_require_meta_items_accepts_valid_list_shape() -> None:
    require_meta_items({"meta": {"read_only": True}, "items": []})


def test_require_meta_items_rejects_missing_meta_items() -> None:
    try:
        require_meta_items({"items": []})
    except ContractAuditError as exc:
        assert "meta" in str(exc).lower()
    else:
        raise AssertionError("expected ContractAuditError")


def test_require_error_envelope_requires_request_id_header_match() -> None:
    body = {
        "error": {
            "code": "validation_error",
            "message": "Invalid",
            "details": {},
            "request_id": "abc123",
        }
    }
    try:
        require_error_envelope(body, response=_FakeResponse(headers={"X-Request-ID": "different"}))
    except ContractAuditError as exc:
        assert "match" in str(exc).lower()
    else:
        raise AssertionError("expected ContractAuditError")


def test_scan_forbidden_leaks_detects_home_path_and_postgres_url() -> None:
    hits = scan_forbidden_leaks({"detail": "/home/ops/file", "dsn": "postgresql://u:p@h/db"})
    assert "/home/" in hits
    assert "postgresql://" in hits


def test_scan_forbidden_leaks_empty_when_safe() -> None:
    assert scan_forbidden_leaks({"ok": True, "meta": {"read_only": True}}) == []


def test_scan_forbidden_leaks_detects_home_in_legacy_path_field() -> None:
    hits = scan_forbidden_leaks(
        {
            "sqlite_path": "emails.sqlite",
            "active_current_dir": "/home/ops/reports/out/active/current",
        }
    )
    assert "/home/" in hits

