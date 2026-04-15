"""Commercial intelligence v1 (physical package grouping).

Implementation modules:

- ``commercial_intel_schema`` — DDL and ``ensure_commercial_intel_tables``
- ``commercial_intel_queries`` — read helpers for the builder
- ``commercial_intel_rules`` — deterministic signal derivation
- ``commercial_intel_review`` — candidate queue export and review actions

**Compatibility:** root-level ``origenlab_email_pipeline.commercial_intel_*`` modules
remain as thin re-export shims. Prefer ``origenlab_email_pipeline.commercial.commercial_intel_*``
(or the shims) for imports; behavior is identical.
"""
