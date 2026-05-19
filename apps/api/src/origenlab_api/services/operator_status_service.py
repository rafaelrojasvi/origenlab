"""Operator status — delegates to email-pipeline (read-only)."""

from __future__ import annotations

from origenlab_email_pipeline.operator_status_report import build_operator_status_report
from origenlab_email_pipeline.outbound_core import (
    resolve_outbound_gmail_user,
    resolve_outbound_sent_folders,
)

from origenlab_api.schemas.operator import OperatorStatusResponse
from origenlab_api.settings import Settings


def build_operator_status_response(
    settings: Settings,
    *,
    max_staleness_days: float = 14.0,
) -> OperatorStatusResponse:
    """Build API response using ``origenlab_email_pipeline.operator_status_report``."""
    sqlite_path = settings.resolved_sqlite_path()
    active_current = settings.resolved_active_current()
    manifest_path = settings.resolved_manifest_path()

    from origenlab_email_pipeline.config import load_settings

    ep_settings = load_settings()
    gmail_user = resolve_outbound_gmail_user(ep_settings, explicit=None)
    sent_folders = resolve_outbound_sent_folders(None)

    report = build_operator_status_report(
        sqlite_path=sqlite_path,
        active_current=active_current,
        manifest_path=manifest_path,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        max_staleness_days=max_staleness_days,
    )

    readiness = report.outbound_readiness or {}
    readiness_verdict = readiness.get("verdict")
    if readiness_verdict is None:
        outbound_readiness = "n/a"
    else:
        outbound_readiness = str(readiness_verdict)

    return OperatorStatusResponse(
        verdict=report.verdict,
        sqlite_path=report.sqlite_path,
        campaign_mode=report.campaign_mode,
        operator_focus=report.current_operator_focus,
        outbound_readiness=outbound_readiness,
        warnings=list(report.warnings),
    )
