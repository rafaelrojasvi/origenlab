"""Next cold-outreach recipients from ``lead_master`` (ranked SQL + shared export gate).

Eligibility uses ``candidate_export_gate.evaluate_export_eligibility`` (Sent parse, suppression,
``outreach_contact_state`` including ``snoozed``, supplier domains, noise). Not a fallback to
``contact_master``—that path lives in ``export_marketing_from_contact_master.py``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.candidate_export_gate import (
    GateContext,
    evaluate_export_eligibility,
)
from origenlab_email_pipeline.lead_export_queries import (
    sql_left_join_best_org_match,
    sql_upstream_active_lead_master,
)
from origenlab_email_pipeline.tatiana_copilot.marketing_outreach import (
    MARKETING_VARIANT_GENERAL,
    MARKETING_VARIANT_TYPES,
)

DEFAULT_SENT_FOLDERS: tuple[str, ...] = ("[Gmail]/Enviados", "[Gmail]/Sent Mail")
DEFAULT_EXCLUDE_DOMAINS: tuple[str, ...] = ("origenlab.cl", "labdelivery.cl")

_LM_UPSTREAM_ACTIVE = sql_upstream_active_lead_master("lm")
_JOIN_BEST_ORG = sql_left_join_best_org_match(variant="org_and_archive")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def norm_lead_email(email_norm: str | None, email: str | None) -> str | None:
    raw = (email_norm or "").strip() or (email or "").strip()
    if not raw:
        return None
    found = emails_in(raw)
    if not found:
        return None
    return found[0]


def load_sent_recipient_norms(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
) -> set[str]:
    if not _table_exists(conn, "emails"):
        return set()
    user = gmail_user.strip()
    folders = tuple(f.strip() for f in sent_folders if f.strip())
    if not user or not folders:
        return set()
    like_pat = f"gmail:{user}/%".lower()
    out: set[str] = set()
    ph = ",".join("?" * len(folders))
    cur = conn.execute(
        f"""
        SELECT recipients FROM emails
        WHERE lower(source_file) LIKE ?
          AND folder IN ({ph})
        """,
        (like_pat, *folders),
    )
    for (recipients,) in cur:
        if not recipients:
            continue
        for e in emails_in(recipients):
            out.add(e)
    return out


def load_suppressed_norms(conn: sqlite3.Connection) -> set[str]:
    if not _table_exists(conn, "contact_email_suppression"):
        return set()
    rows = conn.execute(
        "SELECT lower(trim(email)) AS e FROM contact_email_suppression WHERE e != ''"
    ).fetchall()
    return {str(r[0]) for r in rows if r[0]}


def load_outreach_state_map(conn: sqlite3.Connection) -> dict[str, str]:
    """email_norm -> state for rows that block cold export (contacted, replied, snoozed)."""
    if not _table_exists(conn, "outreach_contact_state"):
        return {}
    rows = conn.execute(
        """
        SELECT lower(trim(contact_email_norm)) AS e, lower(trim(state)) AS s
        FROM outreach_contact_state
        WHERE state IN ('contacted', 'replied', 'snoozed')
          AND length(trim(contact_email_norm)) > 0
        """
    ).fetchall()
    out: dict[str, str] = {}
    for e, s in rows:
        if e and s:
            out[str(e)] = str(s)
    return out


def load_outreach_contacted_norms(conn: sqlite3.Connection) -> frozenset[str]:
    """Set of emails blocked by outreach state (contacted, replied, snoozed)."""
    return frozenset(load_outreach_state_map(conn).keys())


def build_marketing_export_gate_context(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
    extra_exclude_domains: tuple[str, ...] = (),
    skip_noise_filter: bool = False,
    skip_supplier_domain_filter: bool = False,
) -> GateContext:
    """Load DB-backed sets once per export; same context for lead and contact_master paths."""
    from origenlab_email_pipeline.marketing_supplier_domains import supplier_email_domains

    supplier_dom = frozenset() if skip_supplier_domain_filter else supplier_email_domains(conn)
    blocked = frozenset(
        d.strip().lower()
        for d in (list(DEFAULT_EXCLUDE_DOMAINS) + list(extra_exclude_domains))
        if d.strip()
    )
    return GateContext(
        sent_recipient_norms=frozenset(
            load_sent_recipient_norms(conn, gmail_user=gmail_user, sent_folders=sent_folders)
        ),
        suppressed_norms=frozenset(load_suppressed_norms(conn)),
        outreach_state_by_email=load_outreach_state_map(conn),
        supplier_domains=supplier_dom,
        blocked_domains=blocked,
        skip_noise_filter=skip_noise_filter,
        skip_supplier_domain_filter=skip_supplier_domain_filter,
    )


@dataclass(frozen=True)
class NextMarketingQueueStats:
    n_scanned: int
    n_kept: int
    n_sent_folder_recipients: int
    n_suppressed: int
    n_outreach_state: int
    gmail_user: str


def compute_next_marketing_recipients(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...] = DEFAULT_SENT_FOLDERS,
    limit: int = 40,
    fetch_cap: int = 4000,
    include_low_fit: bool = False,
    min_priority: float | None = None,
    extra_exclude_domains: tuple[str, ...] = (),
    variant_type: str = MARKETING_VARIANT_GENERAL,
) -> tuple[list[dict[str, object]], NextMarketingQueueStats]:
    """Return outreach-ready rows and exclusion stats. Read-only on ``conn``."""
    sent_norms = load_sent_recipient_norms(conn, gmail_user=gmail_user, sent_folders=sent_folders)
    suppressed = load_suppressed_norms(conn)
    outreach_map = load_outreach_state_map(conn)
    gate_ctx = build_marketing_export_gate_context(
        conn,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        extra_exclude_domains=extra_exclude_domains,
        skip_noise_filter=False,
        skip_supplier_domain_filter=False,
    )

    variant = str(variant_type).strip()
    if variant not in MARKETING_VARIANT_TYPES:
        variant = MARKETING_VARIANT_GENERAL

    min_pri_sql = ""
    params_tail: list[object] = []
    if min_priority is not None:
        min_pri_sql = " AND COALESCE(lm.priority_score, 0) >= ? "
        params_tail.append(min_priority)

    low_fit_sql = ""
    if not include_low_fit:
        low_fit_sql = " AND COALESCE(lm.fit_bucket, 'low_fit') != 'low_fit' "

    cur = conn.execute(
        f"""
        SELECT
          lm.id AS id_lead,
          lm.source_name,
          lm.org_name,
          lm.contact_name,
          lm.email,
          lm.email_norm,
          lm.region,
          lm.city,
          lm.lead_type,
          lm.priority_score,
          COALESCE(lm.fit_bucket, 'low_fit') AS fit_bucket,
          lm.evidence_summary,
          lm.website,
          m.matched_org_name,
          COALESCE(m.already_in_archive_flag, 0) AS already_in_archive_flag
        FROM lead_master lm
        {_JOIN_BEST_ORG}
        WHERE
          {_LM_UPSTREAM_ACTIVE}
          {low_fit_sql}
          {min_pri_sql}
          AND NULLIF(TRIM(COALESCE(lm.email_norm, lm.email)), '') IS NOT NULL
        ORDER BY
          CASE COALESCE(lm.fit_bucket, 'low_fit')
            WHEN 'high_fit' THEN 0
            WHEN 'medium_fit' THEN 1
            ELSE 2
          END,
          COALESCE(m.already_in_archive_flag, 0) ASC,
          COALESCE(lm.priority_score, 0) DESC,
          CASE WHEN lm.equipment_match_tags IS NOT NULL AND length(trim(lm.equipment_match_tags)) > 0 THEN 0 ELSE 1 END,
          COALESCE(lm.lab_context_score, 0) DESC,
          lm.last_seen_at DESC
        LIMIT ?
        """,
        (*params_tail, int(fetch_cap)),
    )
    cols = [d[0] for d in cur.description]
    export_rows: list[dict[str, object]] = []
    seen_email: set[str] = set()
    n_scanned = 0

    for row in cur:
        n_scanned += 1
        d = dict(zip(cols, row))
        em = norm_lead_email(
            str(d["email_norm"]) if d["email_norm"] else None,
            str(d["email"]) if d["email"] else None,
        )
        if not em or em in seen_email:
            continue
        inst_name = (str(d["org_name"] or "").strip() or str(d["matched_org_name"] or "").strip())
        gres = evaluate_export_eligibility(
            contact_email=em,
            institution_name=inst_name or None,
            ctx=gate_ctx,
        )
        if not gres.eligible:
            continue
        seen_email.add(em)
        sector = next(
            (str(d[k] or "").strip() for k in ("region", "city", "lead_type") if str(d.get(k) or "").strip()),
            "",
        )
        export_rows.append(
            {
                "case_id": f"lead_{d['id_lead']}",
                "id_lead": d["id_lead"],
                "contact_email": em,
                "recipient_name": (str(d["contact_name"] or "").strip()),
                "institution_name": inst_name,
                "sector": sector,
                "fit_bucket": d["fit_bucket"],
                "priority_score": d["priority_score"],
                "already_in_archive_flag": d["already_in_archive_flag"],
                "source_name": d["source_name"],
                "website": str(d["website"] or "").strip(),
                "evidence_summary": str(d["evidence_summary"] or "").strip(),
                "variant_type": variant,
            }
        )
        if len(export_rows) >= int(limit):
            break

    stats = NextMarketingQueueStats(
        n_scanned=n_scanned,
        n_kept=len(export_rows),
        n_sent_folder_recipients=len(sent_norms),
        n_suppressed=len(suppressed),
        n_outreach_state=len(outreach_map),
        gmail_user=gmail_user.strip(),
    )
    return export_rows, stats
