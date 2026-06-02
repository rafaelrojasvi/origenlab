"""Phase 4: stderr deprecation banners on deprecated/compatibility script entrypoints."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from removal_evidence import DEPRECATED_REMOVAL_TARGETS

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"

_PYTHON_HELP_TARGETS: tuple[tuple[str, str, str], ...] = (
    (
        "scripts/qa/build_buyer_opportunity_queue.py",
        "DEPRECATED",
        "build_equipment_first_opportunity_queue.py",
    ),
    (
        "scripts/tools/flag_reported_non_delivery_from_contacto.py",
        "DEPRECATED",
        "flag_ndr_bounces_from_contacto.py",
    ),
    (
        "scripts/leads/advanced/export_archive_outreach_candidates.py",
        "DEPRECATED",
        "build_archive_send_batch.py --audit-only",
    ),
)

_WRAPPER_HELP_TARGETS: tuple[tuple[str, str], ...] = (
    ("scripts/build_lead_account_rollup.py", "scripts/leads/advanced/build_lead_account_rollup.py"),
    (
        "scripts/match_lead_accounts_to_existing_orgs.py",
        "scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py",
    ),
    (
        "scripts/validate_lead_account_rollup.py",
        "scripts/leads/advanced/validate_lead_account_rollup.py",
    ),
    ("scripts/audit_lead_org_quality.py", "scripts/leads/advanced/audit_lead_org_quality.py"),
)

_SHELL_BANNER_TARGETS: tuple[tuple[str, str], ...] = ()

def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(_SRC)}


def _run_help(rel: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO / rel), "--help"],
        cwd=str(REPO),
        env=_env(),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


@pytest.mark.parametrize("rel,category,replacement_needle", _PYTHON_HELP_TARGETS)
def test_deprecated_python_scripts_warn_on_help(
    rel: str, category: str, replacement_needle: str,
) -> None:
    r = _run_help(rel)
    assert r.returncode == 0, r.stderr + r.stdout
    err = r.stderr
    assert category in err, err
    assert replacement_needle in err, err
    assert "not for new operator work" in err.lower() or "not preferred" in err.lower(), err


@pytest.mark.parametrize("wrapper,canonical", _WRAPPER_HELP_TARGETS)
def test_compatibility_wrappers_warn_on_help(wrapper: str, canonical: str) -> None:
    r = _run_help(wrapper)
    assert r.returncode == 0, r.stderr + r.stdout
    err = r.stderr
    assert "COMPATIBILITY_WRAPPER" in err, err
    assert wrapper in err, err
    assert canonical in err, err
    assert "not preferred" in err.lower(), err


@pytest.mark.parametrize("rel,replacement_needle", _SHELL_BANNER_TARGETS)
def test_deprecated_shell_scripts_print_banner_near_top(rel: str, replacement_needle: str) -> None:
    text = (REPO / rel).read_text(encoding="utf-8")
    head = text[:2_000]
    assert "*** DEPRECATED:" in head, rel
    assert replacement_needle in head, rel
    assert "cat >&2 <<'DEPREC'" in head, rel


def test_phase5a_removed_shells_no_longer_expect_deprecation_banner() -> None:
    """Phase 5A deleted dated orchestrators; POST_SEND_SAFE_LOOP.md is canonical."""
    for rel in (
        "scripts/ops/run_post_send_2026_06_01_refresh.sh",
        "scripts/ops/run_manual_outreach_2026_06_01_post_send_refresh.sh",
    ):
        assert not (REPO / rel).is_file(), rel


def test_all_phase2_deprecated_targets_have_runtime_or_shell_banner() -> None:
    """Every DEPRECATED_REMOVAL_TARGETS path is covered by Phase 4 stderr/banner tests."""
    covered = {t[0] for t in _PYTHON_HELP_TARGETS}
    covered |= {t[0] for t in _WRAPPER_HELP_TARGETS}
    covered |= {t[0] for t in _SHELL_BANNER_TARGETS}
    for row in DEPRECATED_REMOVAL_TARGETS:
        assert row["path"] in covered, row["path"]
