"""Structural tests: commercial intel lives under ``commercial/``; root shims stay wired."""

from __future__ import annotations

import origenlab_email_pipeline.commercial_intel_queries as shim_queries
import origenlab_email_pipeline.commercial_intel_review as shim_review
import origenlab_email_pipeline.commercial_intel_rules as shim_rules
import origenlab_email_pipeline.commercial_intel_schema as shim_schema
from origenlab_email_pipeline.commercial import commercial_intel_queries as pkg_queries
from origenlab_email_pipeline.commercial import commercial_intel_review as pkg_review
from origenlab_email_pipeline.commercial import commercial_intel_rules as pkg_rules
from origenlab_email_pipeline.commercial import commercial_intel_schema as pkg_schema


def test_root_shims_reexport_same_callables_as_subpackage() -> None:
    assert shim_schema.ensure_commercial_intel_tables is pkg_schema.ensure_commercial_intel_tables
    assert shim_schema.REBUILDABLE_SQL is pkg_schema.REBUILDABLE_SQL
    assert shim_queries.table_exists is pkg_queries.table_exists
    assert shim_review.apply_review_action is pkg_review.apply_review_action
    assert shim_review.QueueFilters is pkg_review.QueueFilters
    assert shim_rules.derive_email_signal_facts is pkg_rules.derive_email_signal_facts


def test_ensure_commercial_intel_tables_same_object_on_both_import_paths() -> None:
    from origenlab_email_pipeline.commercial.commercial_intel_schema import (
        ensure_commercial_intel_tables as ensure_new,
    )
    from origenlab_email_pipeline.commercial_intel_schema import ensure_commercial_intel_tables as ensure_shim

    assert ensure_new is ensure_shim


def test_subpackage_sql_constants_visible_from_shim() -> None:
    from origenlab_email_pipeline.commercial.commercial_intel_queries import (
        SQL_COMMERCIAL_EMAIL_SIGNAL_FACT_FOR_ROLLUP as sql_pkg,
    )
    from origenlab_email_pipeline.commercial_intel_queries import (
        SQL_COMMERCIAL_EMAIL_SIGNAL_FACT_FOR_ROLLUP as sql_shim,
    )

    assert sql_pkg is sql_shim
