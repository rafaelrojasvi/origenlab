"""Shared operational trust checks for QA scripts and tests.

Implementation is split across ``operational_trust_*`` modules; this file re-exports
the public API so imports stay ``from origenlab_email_pipeline.operational_trust import ...``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.request import urlopen

from origenlab_email_pipeline.operational_trust_cohort import (
    check_cohort_partition,
    check_readiness_critical_fields,
    check_taxonomy_hunt,
    verify_top20_and_readiness,
)
from origenlab_email_pipeline.operational_trust_csv import (
    dedupe_urls,
    duplicate_ids,
    id_leads_from_rows,
    load_client_pack_summary,
    parse_iso_utc,
    read_csv_rows,
)
from origenlab_email_pipeline.operational_trust_evidence import (
    check_evidence_url_formats,
    check_urls_batch,
    collect_urls_from_csvs,
    is_valid_http_url,
    probe_url,
)
from origenlab_email_pipeline.operational_trust_pack import (
    db_lead_totals,
    normalized_fit_bucket_counts,
    verify_client_pack_against_db,
)
from origenlab_email_pipeline.operational_trust_paths import LeadsActivePaths, leads_active_paths
from origenlab_email_pipeline.operational_trust_provenance import (
    check_provenance_db_path,
    check_stale_client_pack,
)
from origenlab_email_pipeline.operational_trust_types import (
    ALLOWED_BUYER_KINDS,
    ALLOWED_FIT_BUCKETS,
    AUDIT_DB_LINE_RE,
    TrustCheck,
)

__all__ = [
    "ALLOWED_BUYER_KINDS",
    "ALLOWED_FIT_BUCKETS",
    "AUDIT_DB_LINE_RE",
    "LeadsActivePaths",
    "TrustCheck",
    "any_critical_failed",
    "check_cohort_partition",
    "check_evidence_url_formats",
    "check_provenance_db_path",
    "check_readiness_critical_fields",
    "check_stale_client_pack",
    "check_taxonomy_hunt",
    "check_urls_batch",
    "collect_urls_from_csvs",
    "db_lead_totals",
    "dedupe_urls",
    "duplicate_ids",
    "id_leads_from_rows",
    "is_valid_http_url",
    "leads_active_paths",
    "load_client_pack_summary",
    "normalized_fit_bucket_counts",
    "parse_iso_utc",
    "probe_url",
    "read_csv_rows",
    "trust_summary",
    "urlopen",
    "verify_client_pack_against_db",
    "verify_top20_and_readiness",
]


def any_critical_failed(checks: Iterable[TrustCheck]) -> bool:
    return any(not c.ok and c.critical for c in checks)


def trust_summary(checks: list[TrustCheck]) -> dict[str, Any]:
    crit_fail = sum(1 for c in checks if c.critical and not c.ok)
    non_fail = sum(1 for c in checks if not c.critical and not c.ok)
    return {
        "total": len(checks),
        "critical_failed": crit_fail,
        "noncritical_failed": non_fail,
        "all_ok": crit_fail == 0,
    }
