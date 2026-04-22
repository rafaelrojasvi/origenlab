"""Operator-contract tests: daily/planner CLIs --help, break-glass headers, compatibility wrappers.

No production DB, Gmail, or --apply. Subprocess is limited to ``--help`` on safe entrypoints.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"

# Daily / core / planner entrypoints: must respond to --help and exit 0 (argparse or equivalent).
_HELP_ENTRYPOINTS: tuple[str, ...] = (
    "scripts/qa/export_do_not_repeat_master.py",
    "scripts/qa/validate_campaign_csvs.py",
    "scripts/leads/process_broad_marketing_contacts.py",
    "scripts/leads/run_current_campaign_pipeline.py",
    "scripts/leads/mark_sent_batch_contacted.py",
    "scripts/ingest/05_workspace_gmail_imap_to_sqlite.py",
    "scripts/qa/check_reproducibility.py",
    "scripts/qa/plan_reports_out_cleanup.py",
    "scripts/qa/plan_script_consolidation.py",
    "scripts/qa/plan_source_quality.py",
    "scripts/tools/archive_reports_out_generated.py",
)

# Break-glass: file header / top-of-file must warn (do not execute).
_BREAK_GLASS_PATHS: tuple[str, ...] = (
    "scripts/qa/send_inline_html_email_via_gmail_api.py",
    "scripts/qa/sync_outreach_batch_from_ingested_bounces.py",
    "scripts/tools/purge_contact_emails_from_sqlite.py",
    "scripts/tools/purge_email_domain_from_sqlite.py",
    "scripts/tools/purge_mailbox_from_sqlite.py",
    "scripts/tools/apply_sqlite_schema.py",
    "scripts/mart/build_business_mart.py",
    "scripts/commercial/build_commercial_intel_v1.py",
    "scripts/leads/advanced/build_lead_account_rollup.py",
    "scripts/validation/extract_attachment_text.py",
    "scripts/tools/archive_reports_out_generated.py",
    "scripts/migrate/sqlite_archive_to_postgres.py",
    "scripts/migrate/sqlite_document_master_to_postgres.py",
    "scripts/migrate/sqlite_outbound_sidecars_to_postgres.py",
)

# Top-of-file operator warning (Stage 1.5 banners and equivalents)
_BREAK_HEADER = re.compile(
    r"(?i)(BREAK-?GLASS|DANGEROUS|#+\s*SAFETY|SAFETY\s*[\(—:]|^#\s*[- ]*SAFETY)",
)

_COMPAT_WRAPPERS: tuple[str, ...] = (
    "scripts/audit_lead_org_quality.py",
    "scripts/build_lead_account_rollup.py",
    "scripts/match_lead_accounts_to_existing_orgs.py",
    "scripts/validate_lead_account_rollup.py",
)


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(_SRC)}


def _run_help(rel: str) -> subprocess.CompletedProcess[str]:
    p = REPO / rel
    return subprocess.run(
        [sys.executable, str(p), "--help"],
        cwd=str(REPO),
        env=_env(),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def test_operator_entrypoints_help_exits_zero() -> None:
    for rel in _HELP_ENTRYPOINTS:
        p = REPO / rel
        assert p.is_file(), f"missing: {p}"
        r = _run_help(rel)
        assert r.returncode == 0, f"{rel}: {r.stderr!r} {r.stdout!r}"


def test_break_glass_files_contain_safety_mention() -> None:
    for rel in _BREAK_GLASS_PATHS:
        p = REPO / rel
        assert p.is_file()
        text = p.read_text(encoding="utf-8", errors="replace")
        head = text[: 25_000]  # noqa: SIM201
        assert _BREAK_HEADER.search(head), f"expected SAFETY / break-glass / DANGEROUS in top of {rel}"


def test_compatibility_wrappers_text_and_path() -> None:
    for rel in _COMPAT_WRAPPERS:
        p = REPO / rel
        assert p.is_file()
        t = p.read_text(encoding="utf-8", errors="replace").lower()
        assert "compatibility" in t or "wrapper" in t, rel
        assert "leads/advanced" in t or "leads\\advanced" in t, rel
        # Docstrings say delegation / no new behavior; lenient
        assert "no behavior" in t or "delegate" in t or "runpy" in t or "implementation" in t, rel
