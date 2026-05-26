"""Tests for read-only commercial deal list CLI."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.commercial.commercial_deal_list import (
    DealListFilters,
    deal_list_to_json_payload,
    fetch_deal_list,
    format_deal_list_human,
    list_deals,
)
from origenlab_email_pipeline.commercial.commercial_deal_inspector import connect_readonly
from origenlab_email_pipeline.commercial.commercial_deal_promotion import (
    apply_deal_promotion_plan,
    build_serva_ceaf_plan_from_default_preview,
)
from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    ensure_commercial_deal_tables,
)
from origenlab_email_pipeline.commercial.serva_ceaf_deal_confirmed import DEAL_KEY

_REPO = Path(__file__).resolve().parents[1]
_PREVIEW = _REPO / "reports/out/active/current/commercial_deals_preview/serva-ceaf-oc-26172-po-174-26.json"
_SCRIPT = _REPO / "scripts/commercial/list_commercial_deals.py"

_FORBIDDEN_SUBSTRINGS = ("body", "full_body", "body_text", "full_text", "attachment_extract")


@pytest.fixture
def serva_preview_exists() -> None:
    if not _PREVIEW.is_file():
        pytest.skip(f"preview fixture missing: {_PREVIEW}")


@pytest.fixture
def applied_db(tmp_path: Path, serva_preview_exists: None) -> Path:
    db = tmp_path / "backup" / "ledger-test.sqlite"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_commercial_deal_tables(conn)
    plan = build_serva_ceaf_plan_from_default_preview(pipeline_root=_REPO)
    apply_deal_promotion_plan(conn, plan)
    conn.close()
    return db


def test_list_shows_serva_ceaf(applied_db: Path) -> None:
    deals = list_deals(applied_db)
    assert len(deals) == 1
    row = deals[0]
    assert row["deal_key"] == DEAL_KEY
    assert "CEAF" in (row.get("client_org_name") or "")
    assert "SERVA" in (row.get("supplier_org_name") or "")
    assert row["deal_status"] == "logistics_pending"
    assert row["client_sale_net_clp"] == 1_260_000
    assert row["client_sale_gross_clp"] == 1_499_400
    assert row["supplier_amount_paid_decimal"] == "218.00"


def test_needs_margin_review_filter(applied_db: Path) -> None:
    conn = connect_readonly(applied_db)
    deals = fetch_deal_list(conn, DealListFilters(needs_margin_review=True))
    conn.close()
    assert len(deals) == 1
    assert deals[0]["margin_status"] == "needs_review"


def test_human_format_includes_key_fields(applied_db: Path) -> None:
    deals = list_deals(applied_db)
    text = format_deal_list_human(deals)
    assert DEAL_KEY in text
    assert "logistics_pending" in text
    assert "needs_review" in text
    assert "1,260,000" in text
    assert "1,499,400" in text


def test_json_payload_safe(applied_db: Path) -> None:
    deals = list_deals(applied_db)
    payload = deal_list_to_json_payload(deals)
    raw = json.dumps(payload)
    assert "source_preview_path" not in raw
    assert "notes_json" not in raw
    assert "transfer_id" not in raw
    for sub in _FORBIDDEN_SUBSTRINGS:
        assert f'"{sub}"' not in raw


def test_cli_json_parses(applied_db: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--sqlite-db", str(applied_db), "--json"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["count"] == 1
    assert payload["deals"][0]["deal_key"] == DEAL_KEY


def test_cli_needs_margin_review(applied_db: Path) -> None:
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--sqlite-db",
            str(applied_db),
            "--needs-margin-review",
            "--json",
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert all(d["margin_status"] == "needs_review" for d in payload["deals"])


def test_cli_missing_db_exits_nonzero(tmp_path: Path) -> None:
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--sqlite-db",
            str(tmp_path / "missing.sqlite"),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode != 0
    assert "ERROR" in r.stderr


def test_cli_no_writes(applied_db: Path) -> None:
    before = applied_db.stat().st_mtime_ns
    subprocess.run(
        [sys.executable, str(_SCRIPT), "--sqlite-db", str(applied_db)],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert applied_db.stat().st_mtime_ns == before


def test_cli_output_has_no_body_fields(applied_db: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--sqlite-db", str(applied_db), "--json"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    for sub in _FORBIDDEN_SUBSTRINGS:
        assert sub not in r.stdout
