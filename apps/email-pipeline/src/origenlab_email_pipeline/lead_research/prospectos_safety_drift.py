"""Read-only Prospectos safety drift audit (raw lead_research vs operational sidecars)."""

from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import domain_of
from origenlab_email_pipeline.lead_research.lead_research_operational_overlay import (
    CLASS_BOUNCED_SUPPRESSED,
    CLASS_MANUAL_OUTREACH_SENT,
    apply_operational_overlay_to_prospect,
    is_bounce_suppression_reason,
    load_operational_indexes_from_sqlite,
    summarize_prospects_for_dashboard,
)
from origenlab_email_pipeline.lead_research.lead_research_operational_overlay import (
    normalize_prospect_email,
)

BLOCKED_CLASS = frozenset({
    "bounced_block",
    "suppressed_block",
    "already_contacted_block",
    "supplier_or_internal_block",
    CLASS_BOUNCED_SUPPRESSED,
})
BLOCKED_STATUS = frozenset({"blocked", "bounced_suppressed"})
REVIEWABLE_CLASS = frozenset({
    "net_new_safe_review",
    "same_domain_contacted_review",
    "public_tender_review",
    "research_only_contact_needed",
    "revision_individual",
})
CONTACTED_CLASS = frozenset({CLASS_MANUAL_OUTREACH_SENT, "already_contacted_block"})
CONTACTED_STATES = frozenset({"contacted", "replied", "snoozed"})

SUPPRESSED_CSV_FIELDS = [
    "prospect_key",
    "email",
    "domain",
    "source_type",
    "dataset_label",
    "raw_classification",
    "raw_status",
    "raw_is_blocked",
    "suppression_reason_code",
    "suppression_source",
    "recommended_overlay_state",
    "notes",
]
CONTACTED_CSV_FIELDS = [
    "prospect_key",
    "email",
    "domain",
    "source_type",
    "dataset_label",
    "raw_classification",
    "raw_status",
    "raw_is_blocked",
    "outreach_state",
    "first_contacted_at",
    "latest_contacted_at",
    "recommended_overlay_state",
    "notes",
]
NET_NEW_CSV_FIELDS = [
    "prospect_key",
    "email",
    "domain",
    "source_type",
    "dataset_label",
    "raw_classification",
    "raw_status",
    "raw_is_blocked",
    "operational_blockers",
    "overlay_classification",
    "overlay_is_blocked",
    "notes",
]
MISSING_EMAIL_CSV_FIELDS = [
    "prospect_key",
    "organization_name",
    "contact_name",
    "domain",
    "source_type",
    "dataset_label",
    "raw_classification",
    "raw_status",
    "raw_is_blocked",
    "recommended_bucket",
    "notes",
]
SAME_DOMAIN_CSV_FIELDS = [
    "prospect_key",
    "email",
    "domain",
    "raw_classification",
    "raw_is_blocked",
    "exact_email_suppressed",
    "exact_email_contacted_outreach",
    "gmail_history_on_row",
    "domain_suppressed",
    "recommended_bucket",
    "notes",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect_sqlite_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def raw_blocked_clearly(prospect: dict[str, Any]) -> bool:
    if prospect.get("is_blocked"):
        return True
    classification = str(prospect.get("classification") or "")
    status = str(prospect.get("status") or "")
    return classification in BLOCKED_CLASS or status in BLOCKED_STATUS


def raw_contacted_clearly(prospect: dict[str, Any]) -> bool:
    classification = str(prospect.get("classification") or "")
    status = str(prospect.get("status") or "")
    return classification in CONTACTED_CLASS or status == "manual_outreach_contacted"


def raw_reviewable(prospect: dict[str, Any]) -> bool:
    if prospect.get("is_blocked"):
        return False
    return str(prospect.get("classification") or "") in REVIEWABLE_CLASS


def _row_to_dict(row: sqlite3.Row | tuple[Any, ...], columns: tuple[str, ...]) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}  # type: ignore[union-attr]
    return dict(zip(columns, row, strict=True))


def load_raw_active_prospects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    prospects: list[dict[str, Any]] = []
    sql = """
        SELECT prospect_key, organization_name, contact_name, email, domain,
               classification, status, is_blocked, source_type, dataset_label,
               campaign_bucket, block_or_review_reason,
               gmail_first_contacted_at, gmail_last_contacted_at,
               gmail_sent_count, gmail_received_count
        FROM lead_research_prospect
        WHERE is_active = 1
        ORDER BY prospect_key
    """
    cur = conn.execute(sql)
    columns = tuple(desc[0] for desc in cur.description or ())
    for row in cur:
        record = _row_to_dict(row, columns)
        record["is_blocked"] = bool(int(record.get("is_blocked") or 0))
        prospects.append(record)
    return prospects


def _load_suppression_detail(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contact_email_suppression'"
    ).fetchone():
        return out
    for row in conn.execute(
        "SELECT email, suppression_reason_code, suppression_source FROM contact_email_suppression"
    ):
        email = normalize_prospect_email(row[0])
        if email:
            out[email] = {"code": str(row[1] or ""), "source": str(row[2] or "")}
    return out


def _load_domain_suppression(conn: sqlite3.Connection) -> dict[str, str]:
    out: dict[str, str] = {}
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contact_domain_suppression'"
    ).fetchone():
        return out
    for row in conn.execute(
        "SELECT domain_norm, suppression_reason_text FROM contact_domain_suppression"
    ):
        out[str(row[0]).lower()] = str(row[1] or "")
    return out


def _load_outreach_detail(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='outreach_contact_state'"
    ).fetchone():
        return out
    for row in conn.execute(
        """
        SELECT contact_email_norm, state, source, first_contacted_at, last_contacted_at
        FROM outreach_contact_state
        """
    ):
        email = normalize_prospect_email(row[0])
        if email:
            out[email] = {
                "state": str(row[1] or ""),
                "source": str(row[2] or ""),
                "first_contacted_at": row[3],
                "latest_contacted_at": row[4],
            }
    return out


def _sort_rows(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: tuple(str(r.get(k) or "").lower() for k in keys))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


@dataclass(frozen=True)
class ProspectosSafetyDriftResult:
    summary: dict[str, Any]
    out_dir: Path
    suppressed_not_raw_blocked: list[dict[str, Any]]
    contacted_not_raw_contacted: list[dict[str, Any]]
    net_new_raw_but_blocked_by_safety: list[dict[str, Any]]
    missing_email: list[dict[str, Any]]
    same_domain_review_check: list[dict[str, Any]]

    @property
    def exit_code_default(self) -> int:
        return 0

    def exit_code_strict(
        self,
        *,
        max_suppressed_raw_mismatch: int,
        max_net_new_blocked: int,
    ) -> int:
        if self.summary["suppressed_not_raw_blocked_count"] > max_suppressed_raw_mismatch:
            return 2
        if self.summary["net_new_raw_but_safety_blocked_count"] > max_net_new_blocked:
            return 2
        return 0


def run_prospectos_safety_drift_audit(
    conn: sqlite3.Connection,
    *,
    sqlite_path: Path,
    out_dir: Path,
    generated_at: str | None = None,
) -> ProspectosSafetyDriftResult:
    """Compare raw active prospects to operational sidecars; write report artifacts."""
    generated = generated_at or _utc_now_iso()
    raw_prospects = load_raw_active_prospects(conn)
    indexes = load_operational_indexes_from_sqlite(conn)
    suppression_detail = _load_suppression_detail(conn)
    domain_suppression = _load_domain_suppression(conn)
    outreach_detail = _load_outreach_detail(conn)

    suppressed_not_raw_blocked: list[dict[str, Any]] = []
    contacted_not_raw_contacted: list[dict[str, Any]] = []
    net_new_raw_but_blocked_by_safety: list[dict[str, Any]] = []
    missing_email: list[dict[str, Any]] = []
    same_domain_review_check: list[dict[str, Any]] = []
    overlaid: list[dict[str, Any]] = []
    mismatch_count = 0

    for prospect in raw_prospects:
        email = normalize_prospect_email(prospect.get("email"))
        domain = (str(prospect.get("domain") or "").strip().lower()) or (
            domain_of(email) if email else ""
        )
        overlay = apply_operational_overlay_to_prospect(dict(prospect), indexes)
        overlaid.append(overlay)

        if email and (
            overlay.get("classification") != prospect.get("classification")
            or overlay.get("is_blocked") != prospect.get("is_blocked")
            or overlay.get("status") != prospect.get("status")
        ):
            mismatch_count += 1

        if email and email in suppression_detail and not raw_blocked_clearly(prospect):
            code = suppression_detail[email]["code"]
            suppressed_not_raw_blocked.append(
                {
                    "prospect_key": prospect["prospect_key"],
                    "email": email,
                    "domain": domain,
                    "source_type": prospect.get("source_type"),
                    "dataset_label": prospect.get("dataset_label"),
                    "raw_classification": prospect.get("classification"),
                    "raw_status": prospect.get("status"),
                    "raw_is_blocked": prospect.get("is_blocked"),
                    "suppression_reason_code": code,
                    "suppression_source": suppression_detail[email]["source"],
                    "recommended_overlay_state": (
                        "bounced_suppressed"
                        if is_bounce_suppression_reason(code)
                        else "suppressed_block"
                    ),
                    "notes": "exact email in contact_email_suppression; raw not blocked/bounced",
                }
            )

        if email and email in outreach_detail:
            outreach_state = str(outreach_detail[email]["state"])
            if outreach_state in CONTACTED_STATES and not raw_contacted_clearly(prospect):
                contacted_not_raw_contacted.append(
                    {
                        "prospect_key": prospect["prospect_key"],
                        "email": email,
                        "domain": domain,
                        "source_type": prospect.get("source_type"),
                        "dataset_label": prospect.get("dataset_label"),
                        "raw_classification": prospect.get("classification"),
                        "raw_status": prospect.get("status"),
                        "raw_is_blocked": prospect.get("is_blocked"),
                        "outreach_state": outreach_state,
                        "first_contacted_at": outreach_detail[email].get("first_contacted_at"),
                        "latest_contacted_at": outreach_detail[email].get("latest_contacted_at"),
                        "recommended_overlay_state": CLASS_MANUAL_OUTREACH_SENT,
                        "notes": f"outreach_contact_state={outreach_state}; raw not contacted",
                    }
                )

        if email and raw_reviewable(prospect):
            blockers: list[str] = []
            if email in suppression_detail:
                blockers.append(f"email_suppression:{suppression_detail[email]['code']}")
            outreach = outreach_detail.get(email)
            if outreach and str(outreach.get("state")) in {"contacted", "replied"}:
                blockers.append(f"outreach:{outreach['state']}")
            if domain and domain in domain_suppression:
                blockers.append(f"domain_suppression:{domain}")
            if blockers:
                net_new_raw_but_blocked_by_safety.append(
                    {
                        "prospect_key": prospect["prospect_key"],
                        "email": email,
                        "domain": domain,
                        "source_type": prospect.get("source_type"),
                        "dataset_label": prospect.get("dataset_label"),
                        "raw_classification": prospect.get("classification"),
                        "raw_status": prospect.get("status"),
                        "raw_is_blocked": prospect.get("is_blocked"),
                        "operational_blockers": "; ".join(blockers),
                        "overlay_classification": overlay.get("classification"),
                        "overlay_is_blocked": overlay.get("is_blocked"),
                        "notes": "raw reviewable; operational truth blocks send",
                    }
                )

        if not email:
            missing_email.append(
                {
                    "prospect_key": prospect["prospect_key"],
                    "organization_name": prospect.get("organization_name"),
                    "contact_name": prospect.get("contact_name"),
                    "domain": domain,
                    "source_type": prospect.get("source_type"),
                    "dataset_label": prospect.get("dataset_label"),
                    "raw_classification": prospect.get("classification"),
                    "raw_status": prospect.get("status"),
                    "raw_is_blocked": prospect.get("is_blocked"),
                    "recommended_bucket": "missing_email_review",
                    "notes": "no email on prospect row",
                }
            )

        if email and str(prospect.get("classification") or "") == "same_domain_contacted_review":
            outreach = outreach_detail.get(email)
            same_domain_review_check.append(
                {
                    "prospect_key": prospect["prospect_key"],
                    "email": email,
                    "domain": domain,
                    "raw_classification": prospect.get("classification"),
                    "raw_is_blocked": prospect.get("is_blocked"),
                    "exact_email_suppressed": email in suppression_detail,
                    "exact_email_contacted_outreach": bool(
                        outreach and str(outreach.get("state")) in {"contacted", "replied"}
                    ),
                    "gmail_history_on_row": int(prospect.get("gmail_sent_count") or 0) > 0
                    or bool(prospect.get("gmail_last_contacted_at")),
                    "domain_suppressed": bool(domain and domain in domain_suppression),
                    "recommended_bucket": "review_history",
                    "notes": "same-domain review; not exact block unless suppressed/contacted",
                }
            )

    sort_keys = ("email", "domain", "source_type", "dataset_label", "prospect_key")
    suppressed_not_raw_blocked = _sort_rows(suppressed_not_raw_blocked, sort_keys)
    contacted_not_raw_contacted = _sort_rows(contacted_not_raw_contacted, sort_keys)
    net_new_raw_but_blocked_by_safety = _sort_rows(net_new_raw_but_blocked_by_safety, sort_keys)
    missing_email = _sort_rows(missing_email, ("prospect_key", "domain", "source_type", "dataset_label"))
    same_domain_review_check = _sort_rows(same_domain_review_check, sort_keys)

    dash_raw = summarize_prospects_for_dashboard(raw_prospects)
    dash_overlay = summarize_prospects_for_dashboard(overlaid)

    def _scalar_count(sql: str) -> int:
        try:
            row = conn.execute(sql).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error:
            return 0

    summary: dict[str, Any] = {
        "total_prospects": len(raw_prospects),
        "prospects_with_email": sum(
            1 for prospect in raw_prospects if normalize_prospect_email(prospect.get("email"))
        ),
        "prospects_missing_email": sum(
            1 for prospect in raw_prospects if not normalize_prospect_email(prospect.get("email"))
        ),
        "suppressed_email_count": _scalar_count("SELECT COUNT(*) FROM contact_email_suppression"),
        "suppressed_domain_count": _scalar_count("SELECT COUNT(*) FROM contact_domain_suppression"),
        "contacted_exact_count": _scalar_count(
            """
            SELECT COUNT(*) FROM outreach_contact_state
            WHERE LOWER(TRIM(state)) IN ('contacted', 'replied', 'snoozed')
            """
        ),
        "raw_bounced_block_count": sum(
            1 for prospect in raw_prospects if prospect.get("classification") == "bounced_block"
        ),
        "raw_already_contacted_block_count": sum(
            1
            for prospect in raw_prospects
            if prospect.get("classification") == "already_contacted_block"
        ),
        "raw_is_blocked_count": sum(1 for prospect in raw_prospects if prospect.get("is_blocked")),
        "overlay_should_block_count": sum(1 for prospect in overlaid if prospect.get("is_blocked")),
        "overlay_should_contacted_wait_count": sum(
            1
            for prospect in overlaid
            if prospect.get("classification") == CLASS_MANUAL_OUTREACH_SENT
        ),
        "net_new_safe_raw_count": sum(
            1
            for prospect in raw_prospects
            if prospect.get("classification") == "net_new_safe_review" and not prospect.get("is_blocked")
        ),
        "net_new_safe_after_safety_overlay_count": int(dash_overlay.get("net_new_safe") or 0),
        "mismatches_count": mismatch_count,
        "suppressed_not_raw_blocked_count": len(suppressed_not_raw_blocked),
        "contacted_not_raw_contacted_count": len(contacted_not_raw_contacted),
        "net_new_raw_but_safety_blocked_count": len(net_new_raw_but_blocked_by_safety),
        "dashboard_kpi_raw": dash_raw,
        "dashboard_kpi_after_overlay": dash_overlay,
        "generated_at": generated,
        "sqlite_path": str(sqlite_path.resolve()),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "suppressed_prospects_not_raw_blocked.csv", SUPPRESSED_CSV_FIELDS, suppressed_not_raw_blocked)
    _write_csv(out_dir / "contacted_prospects_not_raw_contacted.csv", CONTACTED_CSV_FIELDS, contacted_not_raw_contacted)
    _write_csv(out_dir / "net_new_raw_but_blocked_by_safety.csv", NET_NEW_CSV_FIELDS, net_new_raw_but_blocked_by_safety)
    _write_csv(out_dir / "missing_email_review.csv", MISSING_EMAIL_CSV_FIELDS, missing_email)
    _write_csv(out_dir / "same_domain_review_check.csv", SAME_DOMAIN_CSV_FIELDS, same_domain_review_check)
    (out_dir / "prospectos_safety_drift_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "vocabulary_snapshot.md").write_text(
        _build_vocabulary_snapshot(conn, summary),
        encoding="utf-8",
    )
    (out_dir / "EXECUTIVE_SUMMARY.md").write_text(
        _build_executive_summary(summary, out_dir),
        encoding="utf-8",
    )

    return ProspectosSafetyDriftResult(
        summary=summary,
        out_dir=out_dir,
        suppressed_not_raw_blocked=suppressed_not_raw_blocked,
        contacted_not_raw_contacted=contacted_not_raw_contacted,
        net_new_raw_but_blocked_by_safety=net_new_raw_but_blocked_by_safety,
        missing_email=missing_email,
        same_domain_review_check=same_domain_review_check,
    )


def _build_vocabulary_snapshot(conn: sqlite3.Connection, summary: dict[str, Any]) -> str:
    lines = ["# Vocabulary snapshot — Prospectos / lead_research (active prospects)\n"]
    queries = {
        "source_type": "SELECT source_type, COUNT(*) FROM lead_research_prospect WHERE is_active=1 GROUP BY 1 ORDER BY 2 DESC, 1",
        "dataset_label": "SELECT dataset_label, COUNT(*) FROM lead_research_prospect WHERE is_active=1 GROUP BY 1 ORDER BY 2 DESC, 1",
        "classification": "SELECT classification, COUNT(*) FROM lead_research_prospect WHERE is_active=1 GROUP BY 1 ORDER BY 2 DESC, 1",
        "status": "SELECT status, COUNT(*) FROM lead_research_prospect WHERE is_active=1 GROUP BY 1 ORDER BY 2 DESC, 1",
        "is_blocked": "SELECT is_blocked, COUNT(*) FROM lead_research_prospect WHERE is_active=1 GROUP BY 1 ORDER BY 2 DESC, 1",
        "campaign_bucket": "SELECT campaign_bucket, COUNT(*) FROM lead_research_prospect WHERE is_active=1 GROUP BY 1 ORDER BY 2 DESC, 1",
    }
    for title, sql in queries.items():
        lines.append(f"\n## {title}\n")
        try:
            for value, count in conn.execute(sql):
                lines.append(f"- `{value}`: {count}")
        except sqlite3.Error:
            lines.append("- (table unavailable)")
    lines.append("\n## block_reason codes (active prospects)\n")
    try:
        for value, count in conn.execute(
            """
            SELECT br.reason_code, COUNT(*) FROM lead_research_block_reason br
            JOIN lead_research_prospect p ON p.id = br.prospect_id
            WHERE p.is_active = 1
            GROUP BY 1 ORDER BY 2 DESC, 1
            """
        ):
            lines.append(f"- `{value}`: {count}")
    except sqlite3.Error:
        lines.append("- (table unavailable)")
    lines.extend(
        [
            "\n## Mirror segment counts (computed)\n",
            f"- raw is_blocked: {summary['raw_is_blocked_count']}",
            f"- overlay blocked: {summary['overlay_should_block_count']}",
            f"- overlay contacted-wait: {summary['overlay_should_contacted_wait_count']}",
            f"- raw net_new_safe_review: {summary['net_new_safe_raw_count']}",
            f"- overlay net_new_safe: {summary['net_new_safe_after_safety_overlay_count']}",
            "",
        ]
    )
    return "\n".join(lines)


def _build_executive_summary(summary: dict[str, Any], out_dir: Path) -> str:
    return f"""# Prospectos safety drift — executive summary

Generated: {summary['generated_at']}  
SQLite: `{summary['sqlite_path']}`  
Canonical model: [`SCHEMA_CLASSIFICATION_MODEL.md`](../../../docs/pipeline/SCHEMA_CLASSIFICATION_MODEL.md)

## Is Prospectos safe for review?

**Yes**, for prioritization and messaging angles, if you treat rows as campaign queue hints. Raw SQLite can lag suppressions/contacted state; dashboard mirror applies operational overlay at load time.

## Is Prospectos safe for sending?

**No from Prospectos fields alone.** Use export gates + `contact_email_suppression` + `contact_domain_suppression` + `outreach_contact_state` + refreshed exclusion CSVs + Sent preflight.

## Headline drift counts

| Metric | Count |
| --- | ---: |
| Active prospects | {summary['total_prospects']} |
| With / without email | {summary['prospects_with_email']} / {summary['prospects_missing_email']} |
| Email / domain suppressions (global) | {summary['suppressed_email_count']} / {summary['suppressed_domain_count']} |
| Outreach contacted+replied+snoozed | {summary['contacted_exact_count']} |
| Raw `bounced_block` | {summary['raw_bounced_block_count']} |
| Raw `already_contacted_block` | {summary['raw_already_contacted_block_count']} |
| Raw `is_blocked=1` | {summary['raw_is_blocked_count']} |
| Overlay should block | {summary['overlay_should_block_count']} |
| Overlay contacted-wait | {summary['overlay_should_contacted_wait_count']} |
| Raw vs overlay mismatches | **{summary['mismatches_count']}** |
| Suppressed email, raw not blocked | **{summary['suppressed_not_raw_blocked_count']}** |
| Contacted in sidecar, raw not contacted | **{summary['contacted_not_raw_contacted_count']}** |
| Raw reviewable, operational blocks | **{summary['net_new_raw_but_safety_blocked_count']}** |
| Net-new safe (raw / after overlay) | {summary['net_new_safe_raw_count']} / {summary['net_new_safe_after_safety_overlay_count']} |

## P0 safety issue?

**No P0** when operators use documented send gates (not `classification` alone). Drift here is **representation** (raw vs overlay), not missing suppression rows in sidecars.

## Recommended next step

1. Use mirrored Prospectos for review; never send from `classification` alone.  
2. After bulk NDR/contacted refreshes, re-run `scripts/qa/audit_prospectos_safety_drift.py`.  
3. P1: rebuild `lead_research_prospect` if raw/overlay parity is required in SQLite.

## Artifacts

Written to `{out_dir.name}/` (under `reports/out/active/current/`).
"""


def print_headline_counts(summary: dict[str, Any], *, out_dir: Path) -> None:
  print("Prospectos safety drift audit (read-only)")
  print(f"  sqlite: {summary['sqlite_path']}")
  print(f"  out:    {out_dir}")
  print(f"  total_prospects: {summary['total_prospects']}")
  print(f"  mismatches_count: {summary['mismatches_count']}")
  print(f"  suppressed_not_raw_blocked_count: {summary['suppressed_not_raw_blocked_count']}")
  print(f"  contacted_not_raw_contacted_count: {summary['contacted_not_raw_contacted_count']}")
  print(f"  net_new_raw_but_safety_blocked_count: {summary['net_new_raw_but_safety_blocked_count']}")
