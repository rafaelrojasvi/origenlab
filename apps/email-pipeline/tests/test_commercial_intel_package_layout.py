"""Phase 5I: commercial intel root shims removed; canonical package is ``commercial/``."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "src" / "origenlab_email_pipeline"
SHIM_NAMES = (
    "commercial_intel_schema.py",
    "commercial_intel_queries.py",
    "commercial_intel_rules.py",
    "commercial_intel_review.py",
)


@pytest.mark.parametrize("name", SHIM_NAMES)
def test_phase5i_root_commercial_intel_shim_files_removed(name: str) -> None:
    assert not (PKG / name).is_file()


def test_commercial_subpackage_modules_exist() -> None:
    for name in SHIM_NAMES:
        assert (PKG / "commercial" / name).is_file()


def test_canonical_imports_expose_public_api() -> None:
    from origenlab_email_pipeline.commercial import commercial_intel_queries as pkg_queries
    from origenlab_email_pipeline.commercial import commercial_intel_review as pkg_review
    from origenlab_email_pipeline.commercial import commercial_intel_rules as pkg_rules
    from origenlab_email_pipeline.commercial import commercial_intel_schema as pkg_schema

    assert callable(pkg_schema.ensure_commercial_intel_tables)
    assert callable(pkg_queries.table_exists)
    assert callable(pkg_review.apply_review_action)
    assert callable(pkg_rules.derive_email_signal_facts)
    assert pkg_schema.REBUILDABLE_SQL
    assert pkg_review.QueueFilters is not None


def test_sqlite_migrate_imports_canonical_commercial_schema() -> None:
    text = (PKG / "sqlite_migrate.py").read_text(encoding="utf-8")
    assert "commercial.commercial_intel_schema" in text
    assert "commercial_intel_schema import" in text
    assert "origenlab_email_pipeline.commercial_intel_" not in text
