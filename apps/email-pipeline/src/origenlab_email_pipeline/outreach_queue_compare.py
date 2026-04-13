"""Read-only comparison between archive-based and lead-based outreach queues."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from origenlab_email_pipeline.archive_outreach_queue import (
    ArchiveOutreachAuditResult,
    audit_archive_outreach_candidates,
)
from origenlab_email_pipeline.marketing_export_context import DEFAULT_SENT_FOLDERS
from origenlab_email_pipeline.next_marketing_queue import compute_next_marketing_recipients
from origenlab_email_pipeline.tatiana_copilot.marketing_outreach import MARKETING_VARIANT_GENERAL

SOURCE_LABEL_ARCHIVE = "archive_contact_master"
SOURCE_LABEL_LEAD = "lead_master"


def _norm_text(v: object) -> str:
    return str(v or "").strip().lower()


def _domain_from_email(email: str) -> str:
    e = _norm_text(email)
    if "@" not in e:
        return ""
    return e.rsplit("@", 1)[-1]


@dataclass(frozen=True)
class OutreachCompareRow:
    source_label: str
    case_id: str
    contact_email: str
    institution_name: str
    domain: str
    score: float
    warmth_band: str
    quality_flags: str
    eligible: bool
    reject_reason_code: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OutreachComparison:
    archive_top: list[OutreachCompareRow]
    lead_top: list[OutreachCompareRow]
    overlap_summary: dict[str, int]
    blocked_archive_by_reason: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive_top": [r.to_dict() for r in self.archive_top],
            "lead_top": [r.to_dict() for r in self.lead_top],
            "overlap_summary": dict(self.overlap_summary),
            "blocked_archive_by_reason": dict(self.blocked_archive_by_reason),
        }


def _archive_rows_from_audit(audit: ArchiveOutreachAuditResult, *, top_n: int) -> list[OutreachCompareRow]:
    rows: list[OutreachCompareRow] = []
    for r in audit.rows:
        c = r.candidate
        rows.append(
            OutreachCompareRow(
                source_label=SOURCE_LABEL_ARCHIVE,
                case_id=c.case_id,
                contact_email=c.contact_email,
                institution_name=c.institution_name,
                domain=_domain_from_email(c.contact_email) or c.domain,
                score=float(c.warmth_score),
                warmth_band=c.warmth_band,
                quality_flags=c.quality_flags,
                eligible=bool(r.eligible),
                reject_reason_code=str(r.reject_reason_code or ""),
            )
        )
    eligible_sorted = [x for x in rows if x.eligible]
    return eligible_sorted[: max(1, top_n)]


def _lead_rows(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
    limit: int,
    fetch_cap: int,
) -> list[OutreachCompareRow]:
    rows, _ = compute_next_marketing_recipients(
        conn,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        limit=int(limit),
        fetch_cap=int(fetch_cap),
        variant_type=MARKETING_VARIANT_GENERAL,
    )
    out: list[OutreachCompareRow] = []
    for r in rows:
        email = str(r.get("contact_email") or "").strip().lower()
        score_raw = r.get("priority_score")
        try:
            score = float(score_raw) if score_raw is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        out.append(
            OutreachCompareRow(
                source_label=SOURCE_LABEL_LEAD,
                case_id=str(r.get("case_id") or ""),
                contact_email=email,
                institution_name=str(r.get("institution_name") or ""),
                domain=_domain_from_email(email),
                score=score,
                warmth_band="n/a",
                quality_flags="lead_queue",
                eligible=True,
                reject_reason_code="",
            )
        )
    return out


def compare_archive_vs_lead_outreach(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...] = DEFAULT_SENT_FOLDERS,
    archive_fetch_cap: int = 20000,
    archive_limit: int = 500,
    lead_fetch_cap: int = 4000,
    lead_limit: int = 500,
    top_n: int = 20,
) -> OutreachComparison:
    """Compare top actionable rows from archive and lead queues with overlap summary."""
    top_cap = max(1, min(int(top_n), 200))
    audit = audit_archive_outreach_candidates(
        conn,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        fetch_cap=int(archive_fetch_cap),
        limit=int(archive_limit),
        strict_contact_graph_noise=True,
    )
    archive_top = _archive_rows_from_audit(audit, top_n=top_cap)
    lead_top = _lead_rows(
        conn,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        limit=max(top_cap, int(lead_limit)),
        fetch_cap=int(lead_fetch_cap),
    )[:top_cap]

    arch_email = {_norm_text(r.contact_email) for r in archive_top if r.contact_email}
    lead_email = {_norm_text(r.contact_email) for r in lead_top if r.contact_email}
    arch_domain = {_norm_text(r.domain) for r in archive_top if r.domain}
    lead_domain = {_norm_text(r.domain) for r in lead_top if r.domain}
    arch_inst = {_norm_text(r.institution_name) for r in archive_top if r.institution_name}
    lead_inst = {_norm_text(r.institution_name) for r in lead_top if r.institution_name}

    overlap = {
        "archive_top_count": len(archive_top),
        "lead_top_count": len(lead_top),
        "overlap_email_count": len(arch_email & lead_email),
        "overlap_domain_count": len(arch_domain & lead_domain),
        "overlap_institution_count": len(arch_inst & lead_inst),
        "archive_unique_email_count": len(arch_email - lead_email),
        "lead_unique_email_count": len(lead_email - arch_email),
    }

    return OutreachComparison(
        archive_top=archive_top,
        lead_top=lead_top,
        overlap_summary=overlap,
        blocked_archive_by_reason=dict(sorted(audit.blocked_by_reason.items())),
    )


__all__ = [
    "SOURCE_LABEL_ARCHIVE",
    "SOURCE_LABEL_LEAD",
    "OutreachCompareRow",
    "OutreachComparison",
    "compare_archive_vs_lead_outreach",
]
