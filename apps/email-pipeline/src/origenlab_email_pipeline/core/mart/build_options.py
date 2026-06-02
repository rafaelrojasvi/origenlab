"""CLI-equivalent options for ``run_business_mart_build``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MartBuildOptions:
    internal_domains: frozenset[str]
    limit_emails: int | None
    dashboard_fast: bool
    canonical_only: bool
    since_days: int | None
    skip_document_master_if_unchanged: bool
    mart_date_slack_days: int
