"""Phase 1 simplification: file banners and Makefile DATE_SUFFIX (no subprocess mutations)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_HEAD = 8_000

_EQUIPMENT_FIRST_BUILDER = REPO / "scripts/qa/build_equipment_first_opportunity_queue.py"
_EQUIPMENT_FIRST_OPERATOR = REPO / "scripts/qa/build_equipment_first_operator_queue.py"
_LEGACY_BUYER_QUEUE = REPO / "scripts/qa/build_buyer_opportunity_queue.py"
_PARKED_MIGRATE = (
    "scripts/migrate/sqlite_archive_to_postgres.py",
    "scripts/migrate/sqlite_document_master_to_postgres.py",
    "scripts/migrate/sqlite_outbound_sidecars_to_postgres.py",
    "scripts/migrate/sqlite_mart_core_to_postgres.py",
)
_PARKED_SYNC_OPS = (
    "scripts/sync/sync_dashboard_postgres_mirror.py",
    "scripts/ops/refresh_operational_dashboard_stack.py",
)
_DEDUPE = REPO / "scripts/maintenance/dedupe_canonical_gmail_messages.py"
_MAKEFILE = REPO / "Makefile"
_EXPERIMENTAL_PARKED_DOC = REPO / "docs/EXPERIMENTAL_PARKED.md"

_PARKED_RE = re.compile(r"EXPERIMENTAL_PARKED|DASHBOARD_ONLY", re.IGNORECASE)
_SAFETY_RE = re.compile(
    r"(?i)(BREAK-?GLASS|#+\s*SAFETY|SAFETY\s*[\(—:])",
)


def test_phase5c_legacy_buyer_queue_removed() -> None:
    assert not _LEGACY_BUYER_QUEUE.is_file(), "Phase 5C removed build_buyer_opportunity_queue.py"


def test_equipment_first_replacement_scripts_exist() -> None:
    assert _EQUIPMENT_FIRST_BUILDER.is_file()
    assert _EQUIPMENT_FIRST_OPERATOR.is_file()


def test_parked_migrate_scripts_header_contains_experimental_parked() -> None:
    for rel in _PARKED_MIGRATE:
        head = (REPO / rel).read_text(encoding="utf-8")[:_HEAD]
        assert _PARKED_RE.search(head), f"expected EXPERIMENTAL_PARKED in {rel}"
        assert _SAFETY_RE.search(head), f"expected SAFETY break-glass in {rel}"


def test_parked_sync_and_ops_headers() -> None:
    sync_head = (REPO / _PARKED_SYNC_OPS[0]).read_text(encoding="utf-8")[:_HEAD]
    assert _PARKED_RE.search(sync_head)
    ops_head = (REPO / _PARKED_SYNC_OPS[1]).read_text(encoding="utf-8")[:_HEAD]
    assert _PARKED_RE.search(ops_head)
    assert re.search(r"DASHBOARD_ONLY", ops_head, re.IGNORECASE)


def test_dedupe_canonical_gmail_has_safety_header() -> None:
    head = _DEDUPE.read_text(encoding="utf-8")[:_HEAD]
    assert _SAFETY_RE.search(head), "dedupe_canonical_gmail_messages should have SAFETY header"


def test_makefile_supports_date_suffix_override() -> None:
    text = _MAKEFILE.read_text(encoding="utf-8")
    assert "DATE_SUFFIX ?=" in text
    assert "--date-suffix $(DATE_SUFFIX)" in text
    assert "20260518" not in text.split("equipment-queue")[1].split("audit")[0], (
        "equipment-queue should not hard-code a single date suffix"
    )


def test_makefile_help_documents_operator_targets() -> None:
    text = _MAKEFILE.read_text(encoding="utf-8")
    help_block = text.split("help:")[1].split("doctor:")[0]
    for needle in (
        "make doctor",
        "make operator-status",
        "make audit",
        "make equipment-queue",
        "DATE_SUFFIX=YYYYMMDD",
        "make safety-refresh",
        "does not run",
    ):
        assert needle in help_block, f"missing in Makefile help: {needle}"


def test_experimental_parked_doc_exists_and_covers_parked_areas() -> None:
    assert _EXPERIMENTAL_PARKED_DOC.is_file()
    body = _EXPERIMENTAL_PARKED_DOC.read_text(encoding="utf-8").lower()
    for needle in (
        "postgres",
        "apps/api",
        "react",
        "tatiana",
        "scripts/ml",
        "campaigns",
        "equipment-first",
        "explicit approval",
    ):
        assert needle in body, f"missing topic in EXPERIMENTAL_PARKED.md: {needle}"
