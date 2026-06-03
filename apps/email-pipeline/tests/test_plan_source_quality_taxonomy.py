"""Phase 6F taxonomy unit tests for plan_source_quality.classify_vertical (path-only)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "plan_source_quality.py"


def _classify(rel: str) -> str:
    name = "plan_source_quality_taxonomy_pytest"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.classify_vertical(rel)


def test_phase6f_src_verticals() -> None:
    assert _classify("src/origenlab_email_pipeline/campaigns/cyber_outreach_campaign.py") == "campaigns"
    assert _classify("src/origenlab_email_pipeline/qa/outreach_volume_rollup.py") == "qa"
    assert _classify("src/origenlab_email_pipeline/postgres_dashboard_api/schemas.py") == "postgres_api"
    assert _classify("src/origenlab_email_pipeline/catalog/catalog_builder.py") == "catalog"
    assert _classify("src/origenlab_email_pipeline/core/mart/build_runner.py") == "mart"
    assert _classify("src/origenlab_email_pipeline/business_mart.py") == "mart"
    assert _classify("src/origenlab_email_pipeline/validation/attachment_validation.py") == "validation"
    assert _classify("src/origenlab_email_pipeline/ingest/gmail_imap.py") == "ingest"


def test_phase6f_warm_cases_and_ndr() -> None:
    assert _classify("src/origenlab_email_pipeline/warm_case_sender_rules.py") == "warm_cases"
    assert _classify("src/origenlab_email_pipeline/ndr_contacto_scan.py") == "ndr"
    assert _classify("src/origenlab_email_pipeline/reported_non_delivery_contacto_scan.py") == "ndr"


def test_phase6f_script_verticals() -> None:
    assert _classify("scripts/qa/plan_source_quality.py") == "planners"
    assert _classify("scripts/qa/plan_script_consolidation.py") == "planners"
    assert _classify("scripts/tools/check_system.py") == "tooling"
    assert _classify("scripts/tools/inspect_sqlite.py") == "tooling"
    assert _classify("scripts/qa/verify_dashboard_postgres_mirror.py") == "postgres_verify"
    assert _classify("scripts/sync/sync_lead_research_postgres_mirror.py") == "migration"
    assert _classify("scripts/migrate/sqlite_archive_to_postgres.py") == "migration"
    assert _classify("scripts/ingest/04_imap_to_sqlite.py") == "ingest"
    assert _classify("scripts/mart/build_business_mart.py") == "mart"
    assert _classify("scripts/qa/build_ndr_review_queue.py") == "ndr"
