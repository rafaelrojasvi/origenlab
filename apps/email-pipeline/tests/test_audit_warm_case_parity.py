"""Tests for read-only warm-case SQLite/Postgres parity audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from origenlab_email_pipeline.qa.warm_case_parity import (
    compare_warm_case_exports,
    format_parity_summary,
    load_warm_cases_json,
    run_warm_case_parity_audit,
)


def _payload(*items: dict) -> dict:
    return {"meta": {"data_source": "test", "count": len(items)}, "items": list(items)}


def test_category_count_differences_detected() -> None:
    sqlite = _payload(
        {"contact_email": "a@x.cl", "subject": "One", "category": "waiting_client"},
        {"contact_email": "b@x.cl", "subject": "Two", "category": "quote_sent"},
    )
    postgres = _payload(
        {"contact_email": "a@x.cl", "subject": "One", "category": "waiting_client"},
        {"contact_email": "c@x.cl", "subject": "Three", "category": "waiting_client"},
        {"contact_email": "d@x.cl", "subject": "Four", "category": "payment_admin"},
    )
    result = compare_warm_case_exports(sqlite["items"], postgres["items"])
    assert result.sqlite_row_count == 2
    assert result.postgres_row_count == 3
    assert result.sqlite_category_counts == {"quote_sent": 1, "waiting_client": 1}
    assert result.postgres_category_counts == {
        "payment_admin": 1,
        "waiting_client": 2,
    }
    assert result.category_count_deltas["waiting_client"] == 1
    assert result.category_count_deltas["quote_sent"] == -1
    assert result.category_count_deltas["payment_admin"] == 1


def test_same_contact_subject_different_category_detected() -> None:
    sqlite = _payload(
        {
            "case_id": "sqlite-1",
            "contact_email": "Buyer@Lab.cl",
            "subject": "  Quote follow-up  ",
            "category": "quote_sent",
            "last_seen_at": "2026-06-01T10:00:00+00:00",
        }
    )
    postgres = _payload(
        {
            "case_id": "pg-1",
            "contact_email": "buyer@lab.cl",
            "subject": "quote follow-up",
            "category": "waiting_client",
            "last_seen_at": "2026-06-01T11:00:00+00:00",
        }
    )
    result = compare_warm_case_exports(sqlite["items"], postgres["items"])
    assert len(result.category_mismatches) == 1
    mismatch = result.category_mismatches[0]
    assert mismatch["sqlite_category"] == "quote_sent"
    assert mismatch["postgres_category"] == "waiting_client"
    assert mismatch["match_by"] == "contact_email+subject"
    assert mismatch["contact_email"] == "Buyer@Lab.cl"


def test_sqlite_only_and_postgres_only_rows_detected() -> None:
    sqlite = _payload(
        {"contact_email": "only@sqlite.cl", "subject": "SQLite row", "category": "waiting_client"},
        {"contact_email": "shared@x.cl", "subject": "Shared", "category": "quote_sent"},
    )
    postgres = _payload(
        {"contact_email": "only@postgres.cl", "subject": "Postgres row", "category": "supplier_followup"},
        {"contact_email": "shared@x.cl", "subject": "Shared", "category": "quote_sent"},
    )
    result = compare_warm_case_exports(sqlite["items"], postgres["items"])
    assert len(result.sqlite_only) == 1
    assert result.sqlite_only[0]["contact_email"] == "only@sqlite.cl"
    assert len(result.postgres_only) == 1
    assert result.postgres_only[0]["contact_email"] == "only@postgres.cl"
    assert result.matched_count == 1


def test_empty_and_missing_items_handled_cleanly(tmp_path: Path) -> None:
    result = compare_warm_case_exports([], [])
    assert result.sqlite_row_count == 0
    assert result.postgres_row_count == 0
    assert result.category_mismatches == []
    assert result.sqlite_only == []
    assert result.postgres_only == []

    meta, items = load_warm_cases_json(_write_json(tmp_path, {"meta": {"count": 0}}))
    assert meta == {"count": 0}
    assert items == []


def test_output_files_written_under_tmp_path(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "sqlite.json"
    postgres_path = tmp_path / "postgres.json"
    out_dir = tmp_path / "parity_out"
    sqlite_path.write_text(
        json.dumps(
            _payload(
                {"contact_email": "a@x.cl", "subject": "A", "category": "waiting_client"},
                {"contact_email": "b@x.cl", "subject": "B", "category": "quote_sent"},
            )
        ),
        encoding="utf-8",
    )
    postgres_path.write_text(
        json.dumps(
            _payload(
                {"contact_email": "a@x.cl", "subject": "A", "category": "waiting_client"},
                {"contact_email": "c@x.cl", "subject": "C", "category": "payment_admin"},
            )
        ),
        encoding="utf-8",
    )

    result = run_warm_case_parity_audit(
        sqlite_json=sqlite_path,
        postgres_json=postgres_path,
        out_dir=out_dir,
    )
    assert (out_dir / "warm_case_parity_summary.json").is_file()
    assert (out_dir / "warm_case_category_counts.csv").is_file()
    assert (out_dir / "warm_case_category_mismatches.csv").is_file()
    assert (out_dir / "warm_case_sqlite_only.csv").is_file()
    assert (out_dir / "warm_case_postgres_only.csv").is_file()
    summary = json.loads((out_dir / "warm_case_parity_summary.json").read_text(encoding="utf-8"))
    assert summary["sqlite_row_count"] == 2
    assert summary["postgres_row_count"] == 2
    assert len(result.sqlite_only) == 1
    assert len(result.postgres_only) == 1

    text = format_parity_summary(result)
    assert "sqlite rows: 2" in text
    assert "postgres rows: 2" in text
    assert "not send approval" in text


def test_load_warm_cases_json_rejects_invalid_items(tmp_path: Path) -> None:
    bad_path = _write_json(tmp_path, {"meta": {}, "items": "not-a-list"})
    with pytest.raises(ValueError, match="items must be a list"):
        load_warm_cases_json(bad_path)


def _write_json(path: Path, payload: dict) -> Path:
    if path.is_dir():
        path = path / "payload.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
