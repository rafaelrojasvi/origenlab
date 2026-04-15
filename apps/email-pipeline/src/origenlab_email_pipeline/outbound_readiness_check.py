"""Read-only assessment of SQLite + mart state before outbound batch builds (preflight)."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.marketing_export_context import (
    DEFAULT_SENT_FOLDERS,
    load_sent_recipient_norms,
)


def object_exists(conn: sqlite3.Connection, name: str) -> bool:
    """True if a table or view with ``name`` exists."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name=? AND type IN ('table','view') LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _parse_flexible_ts(raw: str | None) -> datetime | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _days_since(dt: datetime | None, now: datetime) -> float | None:
    if dt is None:
        return None
    return (now - dt).total_seconds() / 86400.0


@dataclass
class OutboundReadinessReport:
    """Structured result from :func:`assess_outbound_readiness`."""

    verdict: str  # ready | ready_with_warnings | not_ready
    sqlite_path: str
    sqlite_exists: bool
    sqlite_read_only: bool
    required_tables: dict[str, bool] = field(default_factory=dict)
    sent: dict[str, Any] = field(default_factory=dict)
    sidecars: dict[str, Any] = field(default_factory=dict)
    mart: dict[str, Any] = field(default_factory=dict)
    commercial: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_json_obj(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def assess_outbound_readiness(
    conn: sqlite3.Connection,
    *,
    sqlite_path: Path,
    sqlite_exists: bool,
    gmail_user: str,
    sent_folders: tuple[str, ...],
    max_staleness_days: float,
    strict_commercial_required: bool,
) -> OutboundReadinessReport:
    """Run all checks; mutate no data. ``conn`` should be read-only when possible."""

    warnings: list[str] = []
    errors: list[str] = []
    now = datetime.now(timezone.utc)

    if not sqlite_exists:
        errors.append(f"SQLite file does not exist: {sqlite_path}")
        return OutboundReadinessReport(
            verdict="not_ready",
            sqlite_path=str(sqlite_path),
            sqlite_exists=False,
            sqlite_read_only=True,
            errors=errors,
            warnings=warnings,
        )

    required = (
        "emails",
        "contact_email_suppression",
        "outreach_contact_state",
        "supplier_master",
        "contact_master",
        "organization_master",
        "opportunity_signals",
    )
    req_status: dict[str, bool] = {t: table_exists(conn, t) for t in required}
    for t, ok in req_status.items():
        if not ok:
            errors.append(f"Required table missing: {t}")

    sent_info: dict[str, Any] = {
        "gmail_user": gmail_user.strip(),
        "sent_folders": list(sent_folders),
        "sent_email_rows": 0,
        "sent_recipient_norm_count": 0,
        "max_sent_message_at": None,
        "max_sent_message_age_days": None,
    }

    if req_status.get("emails"):
        user = gmail_user.strip()
        folders = tuple(f.strip() for f in sent_folders if f.strip())
        like_pat = f"gmail:{user.lower()}/%"
        if folders:
            ph = ",".join("?" * len(folders))
            row = conn.execute(
                f"""
                SELECT COUNT(*), MAX(COALESCE(NULLIF(trim(date_iso), ''), date_raw))
                FROM emails
                WHERE lower(source_file) LIKE ?
                  AND folder IN ({ph})
                """,
                (like_pat, *folders),
            ).fetchone()
            sent_info["sent_email_rows"] = int(row[0] or 0)
            sent_info["max_sent_message_at"] = row[1]
            max_dt = _parse_flexible_ts(row[1] if row else None)
            age = _days_since(max_dt, now)
            sent_info["max_sent_message_age_days"] = age
            if sent_info["sent_email_rows"] == 0:
                warnings.append(
                    "No rows in `emails` for configured Gmail user + Sent folders — "
                    "Sent-history blocking in the export gate may be ineffective until ingest runs."
                )
            elif age is not None and age > max_staleness_days:
                warnings.append(
                    f"Newest Sent message for this mailbox is ~{age:.1f} days old "
                    f"(threshold {max_staleness_days}): refresh Gmail ingest if you expect recent sends."
                )

        norms = load_sent_recipient_norms(conn, gmail_user=gmail_user, sent_folders=sent_folders)
        sent_info["sent_recipient_norm_count"] = len(norms)
        if req_status.get("emails") and sent_info["sent_email_rows"] > 0 and len(norms) == 0:
            warnings.append(
                "Sent folder rows exist but no normalized recipient addresses were parsed — "
                "check `recipients` column / encoding."
            )

    side: dict[str, Any] = {
        "suppression_rows": 0,
        "outreach_blocking_rows": 0,
        "outreach_by_state": {},
    }
    if table_exists(conn, "contact_email_suppression"):
        side["suppression_rows"] = int(
            conn.execute("SELECT COUNT(*) FROM contact_email_suppression").fetchone()[0]
        )
    elif not errors:
        # Already reported missing as required table
        pass

    if table_exists(conn, "outreach_contact_state"):
        side["outreach_blocking_rows"] = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM outreach_contact_state
                WHERE state IN ('contacted', 'replied', 'snoozed')
                  AND length(trim(contact_email_norm)) > 0
                """
            ).fetchone()[0]
        )
        cur = conn.execute(
            """
            SELECT lower(trim(state)), COUNT(*)
            FROM outreach_contact_state
            WHERE state IN ('contacted', 'replied', 'snoozed')
              AND length(trim(contact_email_norm)) > 0
            GROUP BY 1
            """
        )
        side["outreach_by_state"] = {str(r[0]): int(r[1]) for r in cur if r[0]}

    mart: dict[str, Any] = {
        "contact_master_rows": 0,
        "organization_master_rows": 0,
        "opportunity_signals_rows": 0,
        "contact_master_max_last_seen": None,
        "organization_master_max_last_seen": None,
        "opportunity_signals_max_created_at": None,
        "contact_master_last_seen_age_days": None,
        "organization_master_last_seen_age_days": None,
        "opportunity_signals_created_age_days": None,
    }
    if table_exists(conn, "contact_master"):
        mart["contact_master_rows"] = int(
            conn.execute("SELECT COUNT(*) FROM contact_master").fetchone()[0]
        )
        r = conn.execute("SELECT MAX(last_seen_at) FROM contact_master").fetchone()
        mart["contact_master_max_last_seen"] = r[0]
        mart["contact_master_last_seen_age_days"] = _days_since(
            _parse_flexible_ts(r[0] if r else None), now
        )
        if mart["contact_master_rows"] == 0:
            warnings.append("`contact_master` is empty — rebuild business mart if you expect archive traffic.")

    if table_exists(conn, "organization_master"):
        mart["organization_master_rows"] = int(
            conn.execute("SELECT COUNT(*) FROM organization_master").fetchone()[0]
        )
        r = conn.execute("SELECT MAX(last_seen_at) FROM organization_master").fetchone()
        mart["organization_master_max_last_seen"] = r[0]
        mart["organization_master_last_seen_age_days"] = _days_since(
            _parse_flexible_ts(r[0] if r else None), now
        )
        if mart["organization_master_rows"] == 0:
            warnings.append("`organization_master` is empty — rebuild business mart if you expect org rollups.")

    if table_exists(conn, "opportunity_signals"):
        mart["opportunity_signals_rows"] = int(
            conn.execute("SELECT COUNT(*) FROM opportunity_signals").fetchone()[0]
        )
        r = conn.execute("SELECT MAX(created_at) FROM opportunity_signals").fetchone()
        mart["opportunity_signals_max_created_at"] = r[0]
        mart["opportunity_signals_created_age_days"] = _days_since(
            _parse_flexible_ts(r[0] if r else None), now
        )

    for label, age_key in (
        ("contact_master.last_seen_at", "contact_master_last_seen_age_days"),
        ("organization_master.last_seen_at", "organization_master_last_seen_age_days"),
    ):
        age = mart.get(age_key)
        if isinstance(age, (int, float)) and age > max_staleness_days:
            warnings.append(
                f"{label} is ~{age:.1f} days old (threshold {max_staleness_days}) — consider refreshing the mart."
            )

    opp_age = mart.get("opportunity_signals_created_age_days")
    if (
        mart.get("opportunity_signals_rows", 0) > 0
        and isinstance(opp_age, (int, float))
        and opp_age > max_staleness_days
    ):
        warnings.append(
            f"opportunity_signals newest created_at is ~{opp_age:.1f} days old "
            f"(threshold {max_staleness_days})."
        )

    commercial: dict[str, Any] = {
        "opportunity_candidate_table": table_exists(conn, "opportunity_candidate"),
        "v_commercial_candidate_queue": object_exists(conn, "v_commercial_candidate_queue"),
        "opportunity_candidate_rows": 0,
        "strict_mode": strict_commercial_required,
    }
    if commercial["opportunity_candidate_table"]:
        commercial["opportunity_candidate_rows"] = int(
            conn.execute("SELECT COUNT(*) FROM opportunity_candidate").fetchone()[0]
        )

    if strict_commercial_required:
        if not commercial["opportunity_candidate_table"]:
            errors.append(
                "Strict commercial precheck: `opportunity_candidate` table is missing — "
                "run commercial intel migration / build."
            )
        elif not commercial["v_commercial_candidate_queue"]:
            errors.append(
                "Strict commercial precheck: view `v_commercial_candidate_queue` is missing."
            )
        elif commercial["opportunity_candidate_rows"] == 0:
            warnings.append(
                "Strict commercial mode: `opportunity_candidate` has zero rows — "
                "archive commercial precheck may treat everything as review-only."
            )

    verdict = "ready"
    if errors:
        verdict = "not_ready"
    elif warnings:
        verdict = "ready_with_warnings"

    return OutboundReadinessReport(
        verdict=verdict,
        sqlite_path=str(sqlite_path),
        sqlite_exists=True,
        sqlite_read_only=True,
        required_tables=req_status,
        sent=sent_info,
        sidecars=side,
        mart=mart,
        commercial=commercial,
        warnings=warnings,
        errors=errors,
    )


def print_human_report(r: OutboundReadinessReport) -> None:
    """Stdout summary for operators."""

    print("=== Outbound readiness ===")
    print(f"Verdict: {r.verdict}")
    print(f"SQLite: {r.sqlite_path}")
    print(f"  exists: {r.sqlite_exists}")
    if not r.sqlite_exists:
        for e in r.errors:
            print(f"  ERROR: {e}")
        return

    print("Required tables:")
    for name, ok in sorted(r.required_tables.items()):
        print(f"  {'OK ' if ok else 'MISS'} {name}")

    s = r.sent
    print("Sent history (export gate conventions):")
    print(f"  gmail_user: {s.get('gmail_user')}")
    print(f"  folders: {s.get('sent_folders')}")
    print(f"  matching Sent rows in `emails`: {s.get('sent_email_rows')}")
    print(f"  normalized recipient count: {s.get('sent_recipient_norm_count')}")
    print(f"  newest message timestamp: {s.get('max_sent_message_at')}")
    if s.get("max_sent_message_age_days") is not None:
        print(f"  newest Sent age (days): {s['max_sent_message_age_days']:.2f}")

    sc = r.sidecars
    print("Sidecars:")
    print(f"  contact_email_suppression rows: {sc.get('suppression_rows')}")
    print(f"  outreach blocking rows: {sc.get('outreach_blocking_rows')}")
    if sc.get("outreach_by_state"):
        print(f"  outreach by state: {sc['outreach_by_state']}")

    m = r.mart
    print("Mart:")
    print(f"  contact_master rows: {m.get('contact_master_rows')}")
    print(f"  organization_master rows: {m.get('organization_master_rows')}")
    print(f"  opportunity_signals rows: {m.get('opportunity_signals_rows')}")
    print(f"  contact_master max last_seen_at: {m.get('contact_master_max_last_seen')}")
    print(f"  organization_master max last_seen_at: {m.get('organization_master_max_last_seen')}")
    print(f"  opportunity_signals max created_at: {m.get('opportunity_signals_max_created_at')}")

    c = r.commercial
    print("Commercial precheck layer:")
    print(f"  opportunity_candidate table: {c.get('opportunity_candidate_table')}")
    print(f"  v_commercial_candidate_queue: {c.get('v_commercial_candidate_queue')}")
    print(f"  opportunity_candidate rows: {c.get('opportunity_candidate_rows')}")
    print(f"  strict mode requested: {c.get('strict_mode')}")

    for w in r.warnings:
        print(f"WARNING: {w}")
    for e in r.errors:
        print(f"ERROR: {e}")
