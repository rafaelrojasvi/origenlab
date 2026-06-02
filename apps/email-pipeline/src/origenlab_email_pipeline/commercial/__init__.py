"""Commercial intelligence v1 (physical package grouping).

Implementation modules:

- ``commercial_intel_schema`` — DDL and ``ensure_commercial_intel_tables``
- ``commercial_intel_queries`` — read helpers for the builder
- ``commercial_intel_rules`` — deterministic signal derivation
- ``commercial_intel_review`` — candidate queue export and review actions

**Compatibility:** import from ``origenlab_email_pipeline.commercial.commercial_intel_*``
(or ``from origenlab_email_pipeline.commercial import commercial_intel_schema``).
Root-level ``commercial_intel_*`` shims were removed in Phase 5I (2026-06).
"""
