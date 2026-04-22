from __future__ import annotations

import csv
from pathlib import Path

from origenlab_email_pipeline.candidate_export_gate import GateContext
from origenlab_email_pipeline.core.outbound.broad_marketing_contacts import (
    SEND_READY_FIELDS,
    load_master_norms_from_csv,
    process_reviewed_marketing_rows,
    review_output_fieldnames,
    row_schema_errors,
    safe_output_fieldnames,
)


def _empty_ctx() -> GateContext:
    return GateContext(
        sent_recipient_norms=frozenset(),
        suppressed_norms=frozenset(),
        outreach_state_by_email={},
        supplier_domains=frozenset(),
        blocked_domains=frozenset(),
    )


def test_load_master_norms(tmp_path: Path) -> None:
    p = tmp_path / "m.csv"
    p.write_text(
        "email_norm,note\n"
        "a@b.example,x\n"
        "c@d.example,y\n",
        encoding="utf-8",
    )
    s = load_master_norms_from_csv(p)
    assert s == {"a@b.example", "c@d.example"}


def test_load_master_norms_missing_returns_empty(tmp_path: Path) -> None:
    assert load_master_norms_from_csv(tmp_path / "nope.csv") == set()


def test_row_schema_errors_invalid_email() -> None:
    r = {k: "" for k in ("institution_name", "region", "city", "type", "contact_email", "contact_label", "source_url", "confidence", "fit_signal")}
    r["contact_email"] = "not-an-email"
    r["source_url"] = "https://a.example"
    r["confidence"] = "high"
    assert "invalid_email" in row_schema_errors(r)


def test_process_minimal_send_ready_and_columns(tmp_path: Path) -> None:
    rows = [
        {
            "institution_name": "H",
            "region": "R",
            "city": "C",
            "type": "hospital",
            "contact_email": "ok@example.com",
            "contact_label": "Dir",
            "source_url": "https://h.example/contact",
            "confidence": "high",
            "fit_signal": "x" * 10,
        }
    ]
    res = process_reviewed_marketing_rows(
        rows,
        master_email_norms=set(),
        ctx=_empty_ctx(),
        variant_type="broad_marketing",
    )
    assert len(res.safe_rows) == 1
    assert res.safe_rows[0]["case_id"] == "MKT-00001"
    assert len(res.send_ready_rows) == 1
    assert list(res.send_ready_rows[0].keys()) == list(SEND_READY_FIELDS)
    assert res.send_ready_rows[0]["email_source"] == "marketing_contacts"
    assert res.send_ready_rows[0]["variant_type"] == "broad_marketing"


def test_process_duplicate_in_batch() -> None:
    row = {
        "institution_name": "H",
        "region": "R",
        "city": "C",
        "type": "hospital",
        "contact_email": "dup@example.com",
        "contact_label": "Dir",
        "source_url": "https://h.example/",
        "confidence": "high",
        "fit_signal": "enough",
    }
    res = process_reviewed_marketing_rows(
        [row, dict(row)],
        master_email_norms=set(),
        ctx=_empty_ctx(),
    )
    assert any(b.get("block_reason") == "duplicate_input" for b in res.blocked_rows)
    assert len(res.safe_rows) == 1


def test_process_master_block() -> None:
    row = {
        "institution_name": "H",
        "region": "R",
        "city": "C",
        "type": "hospital",
        "contact_email": "m@y.example",
        "contact_label": "Dir",
        "source_url": "https://h.example/",
        "confidence": "high",
        "fit_signal": "enough",
    }
    res = process_reviewed_marketing_rows(
        [row],
        master_email_norms={"m@y.example"},
        ctx=_empty_ctx(),
    )
    assert not res.safe_rows
    assert res.blocked_rows and "do_not_repeat_master" in res.blocked_rows[0].get("block_reason", "")


def test_output_fieldname_lists_include_expected() -> None:
    assert "case_id" in safe_output_fieldnames()
    assert "review_reason" in review_output_fieldnames()


def test_write_safe_csv_shape(tmp_path: Path) -> None:
    """Round-trip: fieldnames from helpers match a minimal safe row."""
    rows = [
        {
            "institution_name": "H",
            "region": "R",
            "city": "C",
            "type": "hospital",
            "contact_email": "w@example.com",
            "contact_label": "Dir",
            "source_url": "https://h.example/",
            "confidence": "high",
            "fit_signal": "enough text",
        }
    ]
    res = process_reviewed_marketing_rows(rows, master_email_norms=set(), ctx=_empty_ctx())
    p = tmp_path / "s.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=safe_output_fieldnames(), lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in res.safe_rows:
            w.writerow(r)
    with p.open(encoding="utf-8", newline="") as f:
        r = list(csv.DictReader(f))
    assert r[0]["case_id"] == "MKT-00001"
    assert r[0]["contact_email"] == "w@example.com"
