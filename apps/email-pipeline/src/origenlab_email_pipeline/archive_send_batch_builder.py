"""Archive-first outbound batch orchestration (single-run, reviewable artifacts)."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.archive_outreach_queue import (
    ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO,
    ARCHIVE_OUTREACH_COLUMN_NAMES,
    ArchiveOutreachAuditResult,
    audit_archive_outreach_candidates,
)
from origenlab_email_pipeline.archive_shortlist_commercial_precheck import (
    COMMERCIAL_DROP_STATUSES,
    run_precheck_csv,
)
from origenlab_email_pipeline.candidate_export_gate import evaluate_export_eligibility
from origenlab_email_pipeline.marketing_export_context import DEFAULT_SENT_FOLDERS
from origenlab_email_pipeline.outbound_core import (
    build_outbound_run_envelope,
    gate_context_for_archive_batch,
)
from origenlab_email_pipeline.outbound_sent_preflight import (
    SentHistoryPreflightFailed,
    evaluate_sent_history_preflight,
    probe_sent_history,
    sent_preflight_summary_dict,
)

AUDIT_CSV_NAME = "archive_outreach_audit.csv"
AUDIT_SUMMARY_JSON_NAME = "archive_outreach_audit_summary.json"
SHORTLIST_CSV_NAME = "archive_outreach_shortlist.csv"
SHORTLIST_GATE_AUDIT_CSV_NAME = "archive_outreach_shortlist_gate_audit.csv"
SHORTLIST_COMMERCIAL_PRECHECK_CSV_NAME = "archive_outreach_shortlist_commercial_precheck.csv"
SEND_READY_CSV_NAME = "archive_outreach_send_ready.csv"
REVIEW_REQUIRED_CSV_NAME = "archive_outreach_review_required.csv"
BUILD_SUMMARY_JSON_NAME = "archive_outreach_build_summary.json"


@dataclass(frozen=True)
class BuildResult:
    summary: dict[str, Any]
    out_dir: Path


def _write_csv(path: Path, rows: list[dict[str, Any]], *, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _domain_key_for_shortlist_row(row: dict[str, Any]) -> str:
    dom = str(row.get("domain") or "").strip().lower()
    if dom:
        return dom
    em = str(row.get("contact_email") or "").strip().lower()
    if "@" in em:
        return em.rsplit("@", 1)[-1].strip().lower()
    return ""


def _build_archive_shortlist(
    *,
    audit_rows: list[dict[str, Any]],
    shortlist_limit: int,
    allow_weak_warmth: bool,
    shortlist_one_per_domain: bool = False,
) -> list[dict[str, Any]]:
    eligible = [r for r in audit_rows if bool(r.get("eligible"))]
    if not allow_weak_warmth:
        eligible = [r for r in eligible if str(r.get("warmth_band") or "") != "weak"]
    cap = max(1, int(shortlist_limit))
    if not shortlist_one_per_domain:
        return eligible[:cap]
    seen_domains: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in eligible:
        dk = _domain_key_for_shortlist_row(r)
        if dk and dk in seen_domains:
            continue
        if dk:
            seen_domains.add(dk)
        out.append(r)
        if len(out) >= cap:
            break
    return out


def _run_gate_audit_rows(
    *,
    shortlist_rows: list[dict[str, Any]],
    gate_ctx: Any,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in shortlist_rows:
        email = str(row.get("contact_email") or "").strip().lower()
        institution = str(row.get("institution_name") or "").strip()
        gate = evaluate_export_eligibility(
            contact_email=email,
            institution_name=institution or None,
            ctx=gate_ctx,
        )
        out.append(
            {
                "case_id": str(row.get("case_id") or "").strip(),
                "contact_email": email,
                "gate_eligible": "yes" if gate.eligible else "no",
                "gate_reason": gate.reasons[0] if gate.reasons else "",
            }
        )
    return out


def _is_commercially_suppressed(precheck_row: dict[str, str]) -> bool:
    statuses = (
        str(precheck_row.get("contact_candidate_status") or "").strip().lower(),
        str(precheck_row.get("organization_candidate_status") or "").strip().lower(),
        str(precheck_row.get("opportunity_candidate_status") or "").strip().lower(),
    )
    return any(st in COMMERCIAL_DROP_STATUSES for st in statuses)


def _is_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _to_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _is_personal_domain_with_client_signal(shortlist_row: dict[str, Any]) -> bool:
    if not _is_truthy(shortlist_row.get("is_free_personal_domain")):
        return False
    return (
        _to_int(shortlist_row.get("contact_invoice_email_count"))
        + _to_int(shortlist_row.get("contact_purchase_email_count"))
    ) > 0


def _final_classification(
    precheck_row: dict[str, str],
    shortlist_row: dict[str, Any],
    *,
    route_personal_domain_with_client_signals_to_review: bool = False,
    strict_commercial_drop: bool = False,
) -> tuple[str, str]:
    # Deterministic policy for archive-origin rows:
    # 1) shared gate block => drop (hard; same as candidate_export_gate)
    # 2) commercial precheck recommendation drop =>
    #    strict_commercial_drop => drop; else review_required (advisory)
    # 3) ambiguous/missing intel (review) => review_required
    # 4) weak warmth quality => review_required
    # 5) otherwise => send_ready
    if str(precheck_row.get("gate_eligible") or "").strip().lower() != "yes":
        return "drop", "final_gate_blocked"
    recommendation = str(precheck_row.get("recommendation") or "").strip().lower()
    if recommendation == "drop":
        if strict_commercial_drop:
            return "drop", "final_commercial_drop"
        return "review_required", "advisory_commercial_drop"
    if recommendation == "review":
        return "review_required", "final_commercial_review"
    if route_personal_domain_with_client_signals_to_review and _is_personal_domain_with_client_signal(
        shortlist_row
    ):
        return "review_required", "policy_personal_domain_review"
    if str(shortlist_row.get("warmth_band") or "").strip().lower() == "weak":
        return "review_required", "final_weak_warmth_review"
    return "send_ready", "final_send_ready"


def refresh_sent_mailbox(
    *,
    project_root: Path,
    db_path: Path,
    sent_folder: str,
    since_days: int,
) -> None:
    cmd = [
        sys.executable,
        "scripts/ingest/05_workspace_gmail_imap_to_sqlite.py",
        "--folder",
        sent_folder,
        "--since-days",
        str(int(since_days)),
        "--db",
        str(db_path),
    ]
    subprocess.run(cmd, cwd=str(project_root), check=True)


def run_archive_outreach_audit(
    conn: Any,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...] = DEFAULT_SENT_FOLDERS,
    extra_exclude_domains: tuple[str, ...] = (),
    fetch_cap: int,
    audit_limit: int,
    strict_contact_graph_noise: bool = True,
    archive_candidate_sort: str = ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO,
) -> ArchiveOutreachAuditResult:
    """Shared archive audit used by full batch build, ``--audit-only``, and thin export wrappers."""
    return audit_archive_outreach_candidates(
        conn,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        extra_exclude_domains=extra_exclude_domains,
        fetch_cap=int(fetch_cap),
        limit=int(audit_limit),
        strict_contact_graph_noise=bool(strict_contact_graph_noise),
        archive_candidate_sort=archive_candidate_sort,
    )


def write_archive_audit_csv_and_summary(
    *,
    audit: ArchiveOutreachAuditResult,
    audit_csv_path: Path,
    audit_summary_json_path: Path | None,
    gmail_user: str,
    db_path: Path,
    outbound_run: dict[str, Any] | None = None,
    sent_preflight: dict[str, object] | None = None,
) -> dict[str, Any]:
    """Write audit CSV and optionally JSON summary (same shape as full batch first stage)."""
    audit_csv_path = Path(audit_csv_path)
    audit_csv_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [r.to_dict() for r in audit.rows]
    fieldnames = (
        list(rows[0].keys())
        if rows
        else list(ARCHIVE_OUTREACH_COLUMN_NAMES) + ["eligible", "reject_reason_code"]
    )
    _write_csv(audit_csv_path, rows, fieldnames=fieldnames)
    summary = {
        "rows": len(rows),
        "eligible_count": audit.eligible_count,
        "blocked_count": audit.blocked_count,
        "blocked_by_reason": dict(sorted(audit.blocked_by_reason.items())),
        "gmail_user": gmail_user,
        "db_path": str(db_path),
    }
    if outbound_run is not None:
        summary["outbound_run"] = outbound_run
    if sent_preflight is not None:
        summary["sent_preflight"] = sent_preflight
    if audit_summary_json_path is not None:
        p = Path(audit_summary_json_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def build_archive_send_batch(
    *,
    conn: Any,
    db_path: Path,
    out_dir: Path,
    gmail_user: str,
    fetch_cap: int,
    audit_limit: int,
    shortlist_limit: int,
    sent_folders: tuple[str, ...] = DEFAULT_SENT_FOLDERS,
    strict_contact_graph_noise: bool = True,
    allow_weak_warmth: bool = False,
    skip_commercial_precheck: bool = False,
    route_personal_domain_with_client_signals_to_review: bool = False,
    audit_only: bool = False,
    strict_commercial_drop: bool = False,
    extra_exclude_domains: tuple[str, ...] = (),
    manual_suppress_emails: tuple[str, ...] = (),
    manual_suppress_domains: tuple[str, ...] = (),
    sent_folder_defaults_used: bool = False,
    archive_candidate_sort: str = ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO,
    shortlist_one_per_domain: bool = False,
    allow_empty_sent_history: bool = False,
) -> BuildResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    created_at_utc = datetime.now(timezone.utc).isoformat()

    probe = probe_sent_history(conn, gmail_user=gmail_user, sent_folders=sent_folders)
    preflight_outcome = evaluate_sent_history_preflight(
        probe, allow_empty=bool(allow_empty_sent_history)
    )
    if not preflight_outcome.ok:
        raise SentHistoryPreflightFailed(preflight_outcome)
    sent_preflight_block = sent_preflight_summary_dict(preflight_outcome)

    audit = run_archive_outreach_audit(
        conn,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        extra_exclude_domains=extra_exclude_domains,
        fetch_cap=int(fetch_cap),
        audit_limit=int(audit_limit),
        strict_contact_graph_noise=bool(strict_contact_graph_noise),
        archive_candidate_sort=archive_candidate_sort,
    )
    audit_rows = [r.to_dict() for r in audit.rows]
    audit_outbound_run = build_outbound_run_envelope(
        lane="archive",
        gmail_user=gmail_user,
        sqlite_path=str(db_path),
        sent_folders=sent_folders,
        sent_folder_defaults_used=sent_folder_defaults_used,
        strict_contact_graph_noise=bool(strict_contact_graph_noise),
        extra_exclude_domains=extra_exclude_domains,
        created_at_utc=created_at_utc,
        artifact_paths={
            "audit_csv": str(out_dir / AUDIT_CSV_NAME),
            "audit_summary_json": str(out_dir / AUDIT_SUMMARY_JSON_NAME),
        },
        counts={
            "archive_audited_rows": len(audit_rows),
            "archive_eligible_rows": int(audit.eligible_count),
            "archive_blocked_rows": int(audit.blocked_count),
        },
    )
    write_archive_audit_csv_and_summary(
        audit=audit,
        audit_csv_path=out_dir / AUDIT_CSV_NAME,
        audit_summary_json_path=out_dir / AUDIT_SUMMARY_JSON_NAME,
        gmail_user=gmail_user,
        db_path=db_path,
        outbound_run=audit_outbound_run,
        sent_preflight=sent_preflight_block,
    )

    if audit_only:
        summary = {
            "audit_only": True,
            "archive_audited_rows": len(audit_rows),
            "archive_eligible_rows": audit.eligible_count,
            "archive_blocked_rows": audit.blocked_count,
            "archive_candidate_sort": archive_candidate_sort,
            "gmail_user": gmail_user,
            "db_path": str(db_path),
            "out_dir": str(out_dir),
            "commercial_precheck_policy": "n/a_audit_only",
            "note": (
                "Audit-only run: wrote archive_outreach_audit.csv and "
                "archive_outreach_audit_summary.json only. "
                "For a full batch (shortlist, precheck, send_ready), run without --audit-only."
            ),
            "outbound_run": audit_outbound_run,
            "sent_preflight": sent_preflight_block,
        }
        (out_dir / BUILD_SUMMARY_JSON_NAME).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return BuildResult(summary=summary, out_dir=out_dir)

    if not audit.rows:
        raise ValueError("Archive audit produced 0 rows; cannot build outbound batch.")

    shortlist_rows = _build_archive_shortlist(
        audit_rows=audit_rows,
        shortlist_limit=int(shortlist_limit),
        allow_weak_warmth=bool(allow_weak_warmth),
        shortlist_one_per_domain=bool(shortlist_one_per_domain),
    )
    if not shortlist_rows:
        raise ValueError("Shortlist produced 0 rows; check gate/quality constraints.")
    _write_csv(
        out_dir / SHORTLIST_CSV_NAME,
        shortlist_rows,
        fieldnames=list(shortlist_rows[0].keys()),
    )

    gate_ctx = gate_context_for_archive_batch(
        conn,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        extra_exclude_domains=extra_exclude_domains,
        strict_contact_graph_noise=bool(strict_contact_graph_noise),
    )
    gate_rows = _run_gate_audit_rows(shortlist_rows=shortlist_rows, gate_ctx=gate_ctx)
    _write_csv(
        out_dir / SHORTLIST_GATE_AUDIT_CSV_NAME,
        gate_rows,
        fieldnames=["case_id", "contact_email", "gate_eligible", "gate_reason"],
    )

    precheck_path = out_dir / SHORTLIST_COMMERCIAL_PRECHECK_CSV_NAME
    if skip_commercial_precheck:
        fallback_precheck_rows = []
        for row in gate_rows:
            fallback_precheck_rows.append(
                {
                    "case_id": row["case_id"],
                    "contact_email": row["contact_email"],
                    "domain": "",
                    "institution_name": "",
                    "gate_eligible": row["gate_eligible"],
                    "gate_reason": row["gate_reason"],
                    "contact_candidate_status": "",
                    "organization_candidate_status": "",
                    "opportunity_candidate_status": "",
                    "contact_suppression_flags": "",
                    "organization_suppression_flags": "",
                    "opportunity_suppression_flags": "",
                    "v_commercial_candidate_queue_summary": "",
                    "recommendation": "review" if row["gate_eligible"] == "yes" else "drop",
                    "decision_path": (
                        "review_missing_commercial_intel"
                        if row["gate_eligible"] == "yes"
                        else "drop_gate_blocked"
                    ),
                    "decision_source": "fallback_precheck",
                    "trigger_layer": "none" if row["gate_eligible"] == "yes" else "gate",
                    "trigger_status": "missing_intel" if row["gate_eligible"] == "yes" else "ineligible",
                    "trigger_reason_codes": row["gate_reason"] if row["gate_eligible"] != "yes" else "",
                }
            )
        _write_csv(
            precheck_path,
            fallback_precheck_rows,
            fieldnames=list(fallback_precheck_rows[0].keys()) if fallback_precheck_rows else [],
        )
    else:
        run_precheck_csv(
            conn=conn,
            input_path=out_dir / SHORTLIST_CSV_NAME,
            out_path=precheck_path,
            gate_ctx=gate_ctx,
        )
    precheck_rows = _read_csv(precheck_path)

    shortlist_by_email = {
        str(r.get("contact_email") or "").strip().lower(): r for r in shortlist_rows
    }
    send_ready_rows: list[dict[str, Any]] = []
    review_required_rows: list[dict[str, Any]] = []
    commercially_suppressed_rows = 0
    commercial_review_rows = 0
    final_drop_rows = 0
    manual_suppressed_rows = 0
    policy_personal_domain_review_rows = 0
    weak_warmth_review_rows = 0
    advisory_commercial_drop_rows = 0

    def _truthy_lab_flag(row: dict[str, Any]) -> bool:
        v = row.get("last_contacted_by_labdelivery")
        if isinstance(v, bool):
            return v
        return str(v or "").strip().lower() in {"1", "true", "yes", "y"}

    suppress_emails = {str(e or "").strip().lower() for e in manual_suppress_emails if str(e or "").strip()}
    suppress_domains = {str(d or "").strip().lower() for d in manual_suppress_domains if str(d or "").strip()}

    def _is_manually_suppressed(*, email: str, shortlist_row: dict[str, Any]) -> bool:
        em = str(email or "").strip().lower()
        if not em:
            return False
        if em in suppress_emails:
            return True
        dom = str(shortlist_row.get("domain") or "").strip().lower()
        if not dom and "@" in em:
            dom = em.split("@", 1)[1].strip().lower()
        if not dom:
            return False
        if dom in suppress_domains:
            return True
        return any(dom.endswith("." + d) for d in suppress_domains)

    for pre in precheck_rows:
        email = str(pre.get("contact_email") or "").strip().lower()
        shortlist_row = shortlist_by_email.get(email, {})
        if _is_manually_suppressed(email=email, shortlist_row=shortlist_row):
            manual_suppressed_rows += 1
            continue
        final, final_decision_path = _final_classification(
            pre,
            shortlist_row,
            route_personal_domain_with_client_signals_to_review=bool(
                route_personal_domain_with_client_signals_to_review
            ),
            strict_commercial_drop=bool(strict_commercial_drop),
        )
        merged = dict(shortlist_row)
        merged.update(pre)
        merged["final_classification"] = final
        merged["final_decision_path"] = final_decision_path
        if _is_commercially_suppressed(pre):
            commercially_suppressed_rows += 1
        if str(pre.get("recommendation") or "").strip().lower() == "review":
            commercial_review_rows += 1
        if final == "drop":
            final_drop_rows += 1
        if final_decision_path == "policy_personal_domain_review":
            policy_personal_domain_review_rows += 1
        if final_decision_path == "final_weak_warmth_review":
            weak_warmth_review_rows += 1
        if final_decision_path == "advisory_commercial_drop":
            advisory_commercial_drop_rows += 1
        if final == "send_ready":
            send_ready_rows.append(merged)
        elif final == "review_required":
            review_required_rows.append(merged)

    send_fields = list(send_ready_rows[0].keys()) if send_ready_rows else [
        "contact_email",
        "final_classification",
    ]
    review_fields = list(review_required_rows[0].keys()) if review_required_rows else [
        "contact_email",
        "final_classification",
    ]
    _write_csv(out_dir / SEND_READY_CSV_NAME, send_ready_rows, fieldnames=send_fields)
    _write_csv(
        out_dir / REVIEW_REQUIRED_CSV_NAME,
        review_required_rows,
        fieldnames=review_fields,
    )

    gate_blocked_rows = sum(1 for r in gate_rows if r["gate_eligible"] != "yes")
    shortlist_labdelivery_touch_rows = sum(1 for r in shortlist_rows if _truthy_lab_flag(r))
    send_ready_labdelivery_touch_rows = sum(1 for r in send_ready_rows if _truthy_lab_flag(r))
    review_required_labdelivery_touch_rows = sum(1 for r in review_required_rows if _truthy_lab_flag(r))
    summary = {
        "archive_audited_rows": len(audit_rows),
        "archive_eligible_rows": audit.eligible_count,
        "archive_blocked_rows": audit.blocked_count,
        "archive_candidate_sort": archive_candidate_sort,
        "shortlist_rows": len(shortlist_rows),
        "shortlist_labdelivery_touch_rows": shortlist_labdelivery_touch_rows,
        "send_ready_labdelivery_touch_rows": send_ready_labdelivery_touch_rows,
        "review_required_labdelivery_touch_rows": review_required_labdelivery_touch_rows,
        "gate_ok_rows": len(gate_rows) - gate_blocked_rows,
        "gate_blocked_rows": gate_blocked_rows,
        "commercially_suppressed_rows": commercially_suppressed_rows,
        "commercial_review_rows": commercial_review_rows,
        "manual_suppressed_rows": manual_suppressed_rows,
        "policy_personal_domain_review_rows": policy_personal_domain_review_rows,
        "weak_warmth_review_rows": weak_warmth_review_rows,
        "advisory_commercial_drop_rows": advisory_commercial_drop_rows,
        "final_drop_rows": final_drop_rows,
        "send_ready_rows": len(send_ready_rows),
        "review_required_rows": len(review_required_rows),
        "gmail_user": gmail_user,
        "db_path": str(db_path),
        "out_dir": str(out_dir),
        "skip_commercial_precheck": bool(skip_commercial_precheck),
        "route_personal_domain_with_client_signals_to_review": bool(
            route_personal_domain_with_client_signals_to_review
        ),
        "strict_commercial_drop": bool(strict_commercial_drop),
        "commercial_precheck_policy": "strict_drop" if strict_commercial_drop else "advisory",
        "manual_suppress_emails": sorted(suppress_emails),
        "manual_suppress_domains": sorted(suppress_domains),
        "shortlist_one_per_domain": bool(shortlist_one_per_domain),
        "sent_preflight": sent_preflight_block,
        "outbound_run": build_outbound_run_envelope(
            lane="archive",
            gmail_user=gmail_user,
            sqlite_path=str(db_path),
            sent_folders=sent_folders,
            sent_folder_defaults_used=sent_folder_defaults_used,
            strict_contact_graph_noise=bool(strict_contact_graph_noise),
            extra_exclude_domains=extra_exclude_domains,
            created_at_utc=created_at_utc,
            artifact_paths={
                "out_dir": str(out_dir),
                "audit_csv": str(out_dir / AUDIT_CSV_NAME),
                "shortlist_csv": str(out_dir / SHORTLIST_CSV_NAME),
                "send_ready_csv": str(out_dir / SEND_READY_CSV_NAME),
                "review_required_csv": str(out_dir / REVIEW_REQUIRED_CSV_NAME),
                "build_summary_json": str(out_dir / BUILD_SUMMARY_JSON_NAME),
            },
            counts={
                "archive_audited_rows": len(audit_rows),
                "archive_eligible_rows": int(audit.eligible_count),
                "archive_blocked_rows": int(audit.blocked_count),
                "shortlist_rows": len(shortlist_rows),
                "gate_ok_rows": len(gate_rows) - gate_blocked_rows,
                "gate_blocked_rows": gate_blocked_rows,
                "send_ready_rows": len(send_ready_rows),
                "review_required_rows": len(review_required_rows),
                "final_drop_rows": final_drop_rows,
                "shortlist_labdelivery_touch_rows": shortlist_labdelivery_touch_rows,
            },
        ),
    }
    (out_dir / BUILD_SUMMARY_JSON_NAME).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return BuildResult(summary=summary, out_dir=out_dir)

