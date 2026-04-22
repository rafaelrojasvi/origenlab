from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from origenlab_email_pipeline.csv_contracts import normalize_header_name, normalize_row_dict, validate_email_syntax

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "csv_contracts"


def _load_cli():
    p = ROOT / "scripts" / "qa" / "validate_campaign_csvs.py"
    spec = importlib.util.spec_from_file_location("validate_campaign_csvs", p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_header_normalization() -> None:
    assert normalize_header_name(" Contact Email ") == "contact_email"
    assert normalize_header_name("lead-id") == "lead_id"
    assert normalize_header_name("ORG   NAME") == "org_name"


def test_row_normalization_ignores_none_and_lists() -> None:
    row = {None: ["x"], " Lead ID ": " 10 ", "notes": ["a", "b"], "Org Name": "  H " }
    out = normalize_row_dict(row)
    assert "lead_id" in out and out["lead_id"] == "10"
    assert "org_name" in out and out["org_name"] == "H"
    assert "notes" not in out


def test_reviewed_good_passes_strict(tmp_path: Path) -> None:
    mod = _load_cli()
    out_json = tmp_path / "v.json"
    rc = mod.main(
        [
            "--file",
            str(FIX / "reviewed_deepsearch_good.csv"),
            "--kind",
            "reviewed_deepsearch",
            "--strict",
            "--json-out",
            str(out_json),
        ]
    )
    assert rc == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["results"][0]["errors"] == []


def test_markdown_or_summary_contamination_detected(tmp_path: Path) -> None:
    mod = _load_cli()
    rc1 = mod.main(
        [
            "--file",
            str(FIX / "reviewed_deepsearch_with_markdown_fence.csv"),
            "--kind",
            "reviewed_deepsearch",
        ]
    )
    rc2 = mod.main(
        [
            "--file",
            str(FIX / "reviewed_deepsearch_with_summary_line.csv"),
            "--kind",
            "reviewed_deepsearch",
        ]
    )
    assert rc1 == 0
    assert rc2 == 0


def test_invalid_email_and_confidence_fail_strict() -> None:
    mod = _load_cli()
    rc_email = mod.main(
        [
            "--file",
            str(FIX / "reviewed_deepsearch_invalid_email.csv"),
            "--kind",
            "reviewed_deepsearch",
            "--strict",
        ]
    )
    rc_conf = mod.main(
        [
            "--file",
            str(FIX / "reviewed_deepsearch_bad_confidence.csv"),
            "--kind",
            "reviewed_deepsearch",
            "--strict",
        ]
    )
    assert rc_email == 1
    assert rc_conf == 1


def test_high_confidence_bad_source_strict_fails() -> None:
    mod = _load_cli()
    rc = mod.main(
        [
            "--file",
            str(FIX / "reviewed_deepsearch_high_confidence_bad_source.csv"),
            "--kind",
            "reviewed_deepsearch",
            "--strict",
        ]
    )
    assert rc == 1


def test_marketing_contacts_padded_headers_accepted() -> None:
    mod = _load_cli()
    rc = mod.main(
        [
            "--file",
            str(FIX / "marketing_contacts_padded_headers.csv"),
            "--kind",
            "marketing_contacts",
            "--strict",
        ]
    )
    assert rc == 0


def test_send_ready_duplicate_email_fails_strict() -> None:
    mod = _load_cli()
    rc = mod.main(
        [
            "--file",
            str(FIX / "send_ready_duplicate_email.csv"),
            "--kind",
            "send_ready",
            "--strict",
        ]
    )
    assert rc == 1


def test_reviewed_deepsearch_duplicate_email_warns_not_error() -> None:
    mod = _load_cli()
    rc = mod.main(
        [
            "--file",
            str(FIX / "reviewed_deepsearch_duplicate_email.csv"),
            "--kind",
            "reviewed_deepsearch",
            "--strict",
        ]
    )
    assert rc == 0


def test_send_ready_control_chars_warns_but_valid() -> None:
    mod = _load_cli()
    rc = mod.main(
        [
            "--file",
            str(FIX / "send_ready_control_chars.csv"),
            "--kind",
            "send_ready",
            "--strict",
        ]
    )
    assert rc == 0


def test_gate_audit_inconsistent_flags_fails_strict() -> None:
    mod = _load_cli()
    rc = mod.main(
        [
            "--file",
            str(FIX / "gate_audit_inconsistent_flags.csv"),
            "--kind",
            "gate_audit",
            "--strict",
        ]
    )
    assert rc == 1


def test_email_validator_basics() -> None:
    assert validate_email_syntax("a@b.cl") == "a@b.cl"
    assert validate_email_syntax("bad@@b.cl") == ""

