"""Structural tests: operational trust is package-only (no root ``operational_trust_*.py`` shims)."""

from __future__ import annotations

import importlib.util

import origenlab_email_pipeline.operational_trust as ot_facade
from origenlab_email_pipeline.operational_trust import operational_trust_cohort as pkg_cohort
from origenlab_email_pipeline.operational_trust import operational_trust_types as pkg_types


def test_facade_reexports_align_with_subpackage_modules() -> None:
    assert ot_facade.check_cohort_partition is pkg_cohort.check_cohort_partition
    assert ot_facade.TrustCheck is pkg_types.TrustCheck


def test_facade_trust_summary_empty_checks() -> None:
    checks: list = []
    assert ot_facade.trust_summary(checks) == {
        "total": 0,
        "critical_failed": 0,
        "noncritical_failed": 0,
        "all_ok": True,
    }


def test_root_operational_trust_shim_modules_removed() -> None:
    """Regression: legacy root shims were deleted after grep showed no non-test callers."""
    for mod in (
        "operational_trust_cohort",
        "operational_trust_csv",
        "operational_trust_evidence",
        "operational_trust_pack",
        "operational_trust_paths",
        "operational_trust_provenance",
        "operational_trust_types",
    ):
        spec = importlib.util.find_spec(f"origenlab_email_pipeline.{mod}")
        assert spec is None, f"expected {mod!r} to be absent from package root"
