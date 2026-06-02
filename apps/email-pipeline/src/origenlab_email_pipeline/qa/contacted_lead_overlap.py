"""Read-only contacted-lead overlap audit (SQLite → CSV rows; no writes)."""

from __future__ import annotations

import csv
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from origenlab_email_pipeline.business_mart import domain_of, emails_in
from origenlab_email_pipeline.candidate_export_gate import (
    email_domain_under_operator_domain_suppression,
    normalize_export_email,
)
from origenlab_email_pipeline.contact_domain_suppression import load_suppressed_contact_domain_norms
from origenlab_email_pipeline.lead_export_queries import sql_upstream_active_lead_master
from origenlab_email_pipeline.marketing_export_context import (
    load_sent_recipient_norms,
    load_suppressed_norms,
)
from origenlab_email_pipeline.org_normalize import normalize_domain, normalize_org_name

CONTACTED_LEAD_OVERLAP_FIELDNAMES = [
    "lead_id",
    "organization_name",
    "organization_domain",
    "fit_bucket",
    "lead_email",
    "researched_email",
    "pending_research_email",
    "matched_email",
    "matched_domain",
    "match_type",
    "already_contacted",
    "blocked_by_sent",
    "blocked_by_outreach_state",
    "outreach_state",
    "blocked_by_email_suppression",
    "blocked_by_domain_suppression",
    "sent_source",
    "last_contacted_at",
    "outreach_source",
    "confidence",
    "recommended_action",
    "notes",
]

_FREE_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "hotmail.com",
        "outlook.com",
        "yahoo.com",
        "icloud.com",
        "live.com",
        "protonmail.com",
    }
)

_MATCH_PRIORITY: dict[str, int] = {
    "suppression_email": 0,
    "suppression_domain": 1,
    "exact_lead_email_sent": 2,
    "exact_researched_email_sent": 3,
    "exact_pending_email_sent": 4,
    "exact_lead_email_state": 5,
    "exact_researched_email_state": 6,
    "exact_pending_email_state": 7,
    "same_domain_contacted": 8,
    "possible_org_name_match": 9,
    "": 99,
}

_CSV_EMAIL_COLUMNS = (
    "contact_email",
    "resolved_contact_email",
    "email",
    "to",
    "recipient",
    "real_to",
)
_CSV_ORG_COLUMNS = (
    "institution_name",
    "org_name",
    "organization_name",
    "nombre_organizacion",
)
_CSV_SOURCE_COLUMNS = (
    "resolved_domain",
    "organization_domain",
    "domain",
    "source_url",
)


@dataclass
class PendingResearchCsvStats:
    rows_scanned: int = 0
    malformed_rows: int = 0


@dataclass
class ContactedLeadOverlapSummary:
    total: int = 0
    exact_sent: int = 0
    exact_state: int = 0
    any_outreach_block: int = 0
    same_dom: int = 0
    supp: int = 0
    safe: int = 0
    pending_scanned: int = 0
    pending_exact_sent: int = 0
    pending_exact_state: int = 0
    pending_suppressed: int = 0
    pending_malformed_rows: int = 0
    top_organizations: list[tuple[str, int]] = field(default_factory=list)


@dataclass(frozen=True)
class ContactedLeadOverlapBuildResult:
    rows: list[dict[str, object]]
    summary: ContactedLeadOverlapSummary


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def load_sent_norms_and_last_dates(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
) -> tuple[set[str], dict[str, str]]:
    if not table_exists(conn, "emails"):
        return set(), {}
    user = gmail_user.strip()
    folders = tuple(f.strip() for f in sent_folders if f.strip())
    if not user or not folders:
        return set(), {}
    like_pat = f"gmail:{user}/%".lower()
    ph = ",".join("?" * len(folders))
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(emails)").fetchall()}
    date_expr = (
        "COALESCE(NULLIF(TRIM(date_iso), ''), NULLIF(TRIM(date_raw), ''), '')"
        if "date_raw" in cols
        else "COALESCE(NULLIF(TRIM(date_iso), ''), '')"
    )
    cur = conn.execute(
        f"""
        SELECT recipients, {date_expr} AS dts
        FROM emails
        WHERE lower(source_file) LIKE ?
          AND folder IN ({ph})
        """,
        (like_pat, *folders),
    )
    norms: set[str] = set()
    last: dict[str, str] = {}
    for recipients, dts in cur:
        d = str(dts or "").strip()
        if not recipients:
            continue
        for e in emails_in(recipients):
            norms.add(e)
            prev = last.get(e)
            if not prev or d > prev:
                last[e] = d
    return norms, last


def load_outreach_details(conn: sqlite3.Connection) -> dict[str, dict[str, object]]:
    if not table_exists(conn, "outreach_contact_state"):
        return {}
    rows = conn.execute(
        """
        SELECT lower(trim(contact_email_norm)) AS e,
               lower(trim(state)) AS st,
               last_contacted_at,
               first_contacted_at,
               source,
               lead_id
        FROM outreach_contact_state
        WHERE length(trim(contact_email_norm)) > 0
        """
    ).fetchall()
    out: dict[str, dict[str, object]] = {}
    for e, st, last_ts, first_ts, src, lid in rows:
        if not e:
            continue
        out[str(e)] = {
            "state": str(st or ""),
            "last_contacted_at": str(last_ts or "").strip(),
            "first_contacted_at": str(first_ts or "").strip(),
            "source": str(src or "").strip(),
            "lead_id": lid,
        }
    return out


def blocking_outreach_emails(detail: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    block = {"contacted", "replied", "snoozed"}
    return {e: d for e, d in detail.items() if str(d.get("state", "")).lower() in block}


def domains_from_emails(emails: set[str]) -> set[str]:
    out: set[str] = set()
    for em in emails:
        d = domain_of(em)
        if d and d not in _FREE_EMAIL_DOMAINS:
            out.add(d)
    return out


def candidate_domains(
    org_domain: str,
    lead_em: str | None,
    res_em: str | None,
    pend_em: str | None,
) -> set[str]:
    out: set[str] = set()
    if org_domain:
        out.add(org_domain.lower())
    for em in (lead_em, res_em, pend_em):
        if em:
            d = domain_of(em)
            if d:
                out.add(d)
    return {d for d in out if d not in _FREE_EMAIL_DOMAINS}


def build_ref_org_norms(
    conn: sqlite3.Connection,
    *,
    contacted_emails: set[str],
    outreach_block: dict[str, dict[str, object]],
    min_len: int = 10,
) -> set[str]:
    ref: set[str] = set()
    if not table_exists(conn, "lead_master"):
        return ref
    for _em, od in outreach_block.items():
        lid = od.get("lead_id")
        if lid is None:
            continue
        row = conn.execute(
            "SELECT org_name FROM lead_master WHERE id = ?",
            (int(lid),),
        ).fetchone()
        if row and row[0]:
            n = normalize_org_name(str(row[0]))
            if len(n) >= min_len:
                ref.add(n)
    cur = conn.execute(
        """
        SELECT org_name, email, email_norm FROM lead_master
        WHERE org_name IS NOT NULL AND trim(org_name) != ''
        """
    )
    for org_name, email, email_norm in cur:
        raw = (str(email_norm or "").strip() or str(email or "").strip()).lower()
        em = normalize_export_email(raw) if raw else None
        if em and em in contacted_emails:
            n = normalize_org_name(str(org_name))
            if len(n) >= min_len:
                ref.add(n)
    return ref


def norm_csv_header(raw: object) -> str:
    if not isinstance(raw, str):
        return ""
    collapsed = " ".join(raw.strip().lower().split())
    return collapsed.replace(" ", "_")


def norm_csv_scalar_value(raw: object) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if raw is None:
        return ""
    if isinstance(raw, (int, float, bool)):
        return str(raw).strip()
    return ""


def norm_csv_row(raw_row: dict[object, object]) -> tuple[dict[str, str], bool]:
    out: dict[str, str] = {}
    malformed = False
    for k, v in raw_row.items():
        if k is None:
            malformed = True
            continue
        nk = norm_csv_header(k)
        if not nk:
            continue
        if isinstance(v, list):
            malformed = True
            continue
        out[nk] = norm_csv_scalar_value(v)
    return out, malformed


def first_nonempty_csv_value(row: dict[str, str], columns: tuple[str, ...]) -> str:
    for col in columns:
        v = row.get(col)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def domain_from_source_url(url_raw: str) -> str:
    s = str(url_raw or "").strip()
    if not s:
        return ""
    if "://" not in s:
        s = f"https://{s}"
    return normalize_domain(s) or ""


def load_input_research_csv(path: Path) -> tuple[dict[str, str], list[dict[str, str]], PendingResearchCsvStats]:
    """Returns (pending_email_by_lead_id, raw_rows for csv-only keys, stats)."""
    by_lead: dict[str, str] = {}
    raw_rows: list[dict[str, str]] = []
    stats = PendingResearchCsvStats()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for line in reader:
            stats.rows_scanned += 1
            r, malformed = norm_csv_row(dict(line))
            if malformed:
                stats.malformed_rows += 1
            if not r:
                continue
            raw_rows.append(r)
            lid = (r.get("lead_id") or "").strip()
            pem = normalize_export_email(first_nonempty_csv_value(r, _CSV_EMAIL_COLUMNS))
            if lid and pem:
                by_lead[lid] = pem
    return by_lead, raw_rows, stats


def prepare_csv_only_rows(
    raw_csv: list[dict[str, str]],
    db_path: Path,
) -> list[dict[str, str]]:
    db_ids: set[str] = set()
    conn_tmp = connect_readonly(db_path)
    try:
        if table_exists(conn_tmp, "lead_master"):
            for (lid,) in conn_tmp.execute("SELECT id FROM lead_master"):
                db_ids.add(str(int(lid)))
    finally:
        conn_tmp.close()
    csv_only: list[dict[str, str]] = []
    for r in raw_csv:
        lid = (r.get("lead_id") or "").strip()
        if not lid or lid not in db_ids:
            csv_only.append(r)
    return csv_only


def org_domain_for_lead(domain_norm: str | None, domain: str | None) -> str:
    for raw in (domain_norm, domain):
        if raw and str(raw).strip():
            nd = normalize_domain(str(raw).strip())
            if nd:
                return nd.lower()
    return ""


def classify_overlap_row(
    *,
    org_domain: str,
    lead_em: str | None,
    res_em: str | None,
    pend_em: str | None,
    suppressed_norms: set[str],
    suppressed_domains: frozenset[str],
    sent_norms: set[str],
    sent_last: dict[str, str],
    outreach_block: dict[str, dict[str, object]],
    contacted_domains: set[str],
    ref_org_norms: set[str],
    org_name_norm: str,
) -> dict[str, object]:
    cand_domains = candidate_domains(org_domain, lead_em, res_em, pend_em)

    blocked_by_email_suppression = 0
    if lead_em and lead_em in suppressed_norms:
        blocked_by_email_suppression = 1
    if res_em and res_em in suppressed_norms:
        blocked_by_email_suppression = 1
    if pend_em and pend_em in suppressed_norms:
        blocked_by_email_suppression = 1

    supp_dom_hit = ""
    for d in sorted(cand_domains):
        if email_domain_under_operator_domain_suppression(d, suppressed_domains):
            supp_dom_hit = d
            break
    blocked_by_domain_suppression = 1 if supp_dom_hit else 0

    emails_to_check = [e for e in (lead_em, res_em, pend_em) if e]
    blocked_by_sent = 1 if any(e in sent_norms for e in emails_to_check) else 0
    blocked_by_outreach_state = 1 if any(e in outreach_block for e in emails_to_check) else 0
    already_contacted = 1 if (blocked_by_sent or blocked_by_outreach_state) else 0

    match_type = ""
    matched_email = ""
    matched_domain = ""
    confidence = ""
    recommended_action = "safe_for_gate_check"
    notes = ""
    sent_source = ""
    last_contacted_at = ""
    outreach_state = ""
    outreach_source = ""

    chain: list[tuple[int, str, str, str]] = []

    if lead_em and lead_em in suppressed_norms:
        chain.append((_MATCH_PRIORITY["suppression_email"], "suppression_email", lead_em, ""))
    elif res_em and res_em in suppressed_norms:
        chain.append((_MATCH_PRIORITY["suppression_email"], "suppression_email", res_em, ""))
    elif pend_em and pend_em in suppressed_norms:
        chain.append((_MATCH_PRIORITY["suppression_email"], "suppression_email", pend_em, ""))
    elif supp_dom_hit:
        chain.append((_MATCH_PRIORITY["suppression_domain"], "suppression_domain", "", supp_dom_hit))
    elif lead_em and lead_em in sent_norms:
        chain.append((_MATCH_PRIORITY["exact_lead_email_sent"], "exact_lead_email_sent", lead_em, ""))
    elif res_em and res_em in sent_norms:
        chain.append(
            (_MATCH_PRIORITY["exact_researched_email_sent"], "exact_researched_email_sent", res_em, "")
        )
    elif pend_em and pend_em in sent_norms:
        chain.append(
            (_MATCH_PRIORITY["exact_pending_email_sent"], "exact_pending_email_sent", pend_em, "")
        )
    elif lead_em and lead_em in outreach_block:
        chain.append((_MATCH_PRIORITY["exact_lead_email_state"], "exact_lead_email_state", lead_em, ""))
    elif res_em and res_em in outreach_block:
        chain.append(
            (_MATCH_PRIORITY["exact_researched_email_state"], "exact_researched_email_state", res_em, "")
        )
    elif pend_em and pend_em in outreach_block:
        chain.append(
            (_MATCH_PRIORITY["exact_pending_email_state"], "exact_pending_email_state", pend_em, "")
        )

    if chain:
        _pri, match_type, matched_email, matched_domain = min(chain, key=lambda x: x[0])
        confidence = "high"
        if match_type.startswith("suppression"):
            recommended_action = "suppressed_do_not_contact"
            already_contacted = 0
            notes = (
                "On suppression list."
                if "email" in match_type
                else "Domain matches contact_domain_suppression."
            )
        else:
            recommended_action = "skip_already_contacted"
            notes = f"Strong overlap ({match_type})."

        for em in emails_to_check:
            if em in sent_norms:
                sent_source = "gmail_sent"
                lt = sent_last.get(em, "")
                if lt > last_contacted_at:
                    last_contacted_at = lt
            if em in outreach_block:
                od = outreach_block[em]
                outreach_state = str(od.get("state", ""))
                outreach_source = str(od.get("source", ""))
                lt = str(od.get("last_contacted_at", ""))
                if lt > last_contacted_at:
                    last_contacted_at = lt
    else:
        hit_dom = ""
        for d in cand_domains:
            if d in contacted_domains:
                hit_dom = d
                break
        if hit_dom:
            if not emails_to_check or not any(
                e in sent_norms or e in outreach_block for e in emails_to_check
            ):
                match_type = "same_domain_contacted"
                matched_domain = hit_dom
                confidence = "medium"
                recommended_action = "review_same_domain"
                notes = (
                    "Another address on this domain appears in Sent or blocking outreach; "
                    "not necessarily the same person."
                )
            else:
                confidence = "high"
                recommended_action = "safe_for_gate_check"
                notes = "Domain overlap only; emails not in Sent/state (unexpected — check data)."
        elif org_name_norm and org_name_norm in ref_org_norms and len(org_name_norm) >= 10:
            match_type = "possible_org_name_match"
            matched_domain = org_domain
            confidence = "low"
            recommended_action = "review_possible_duplicate_org"
            notes = "Organization name matches a contacted lead (hint only)."
        else:
            confidence = "high"
            recommended_action = "safe_for_gate_check"
            notes = "No Sent/outreach/suppression overlap in this audit scope."

    return {
        "matched_email": matched_email,
        "matched_domain": matched_domain,
        "match_type": match_type,
        "already_contacted": already_contacted,
        "blocked_by_sent": blocked_by_sent,
        "blocked_by_outreach_state": blocked_by_outreach_state,
        "outreach_state": outreach_state,
        "blocked_by_email_suppression": blocked_by_email_suppression,
        "blocked_by_domain_suppression": blocked_by_domain_suppression,
        "sent_source": sent_source,
        "last_contacted_at": last_contacted_at,
        "outreach_source": outreach_source,
        "confidence": confidence,
        "recommended_action": recommended_action,
        "notes": notes,
    }


def action_rank(action: str) -> int:
    return {
        "suppressed_do_not_contact": 0,
        "skip_already_contacted": 1,
        "review_same_domain": 2,
        "review_possible_duplicate_org": 3,
        "safe_for_gate_check": 4,
    }.get(action, 5)


def build_contacted_lead_overlap_audit(
    conn: sqlite3.Connection,
    *,
    fit_buckets: tuple[str, ...],
    pending_by_lead: dict[str, str],
    csv_only_rows: list[dict[str, str]],
    gmail_user: str,
    sent_folders: tuple[str, ...],
) -> list[dict[str, object]]:
    """Build audit rows (read-only SQLite). Caller owns connection lifecycle."""
    suppressed_norms = load_suppressed_norms(conn)
    suppressed_domains = load_suppressed_contact_domain_norms(conn)
    sent_norms, sent_last = load_sent_norms_and_last_dates(
        conn, gmail_user=gmail_user, sent_folders=sent_folders
    )
    if not sent_norms:
        sent_norms = load_sent_recipient_norms(
            conn, gmail_user=gmail_user, sent_folders=sent_folders
        )
    outreach_all = load_outreach_details(conn)
    outreach_block = blocking_outreach_emails(outreach_all)
    contacted_emails = set(sent_norms) | set(outreach_block.keys())
    contacted_domains = domains_from_emails(contacted_emails)
    ref_org_norms = build_ref_org_norms(
        conn, contacted_emails=contacted_emails, outreach_block=outreach_block
    )

    rows_out: list[dict[str, object]] = []
    seen_lead_keys: set[str] = set()
    if not table_exists(conn, "lead_master"):
        print("lead_master missing; CSV-only / empty audit.", file=sys.stderr)
    else:
        up = sql_upstream_active_lead_master("lm")
        ph = ",".join("?" * len(fit_buckets))
        has_r = table_exists(conn, "lead_contact_research")
        join = "LEFT JOIN lead_contact_research r ON r.lead_id = lm.id" if has_r else ""
        r_email = "r.resolved_contact_email" if has_r else "NULL"
        r_dom = "r.resolved_domain" if has_r else "NULL"

        sql = f"""
            SELECT lm.id, lm.org_name, lm.domain, lm.domain_norm, lm.email, lm.email_norm,
                   lm.fit_bucket, {r_email}, {r_dom}
            FROM lead_master lm
            {join}
            WHERE {up} AND lm.fit_bucket IN ({ph})
            ORDER BY lm.id
            """
        cur = conn.execute(sql, tuple(fit_buckets))
        lead_rows = cur.fetchall()

        for lid, org_name, domain, domain_norm, email, email_norm, fit_bucket, r_em, r_dom in lead_rows:
            lead_id_s = str(int(lid))
            seen_lead_keys.add(lead_id_s)
            org_domain = org_domain_for_lead(
                str(domain_norm) if domain_norm else None,
                str(domain) if domain else None,
            )
            lead_em = normalize_export_email(
                str(email_norm or "").strip() or str(email or "").strip()
            )
            res_em = normalize_export_email(str(r_em or "").strip()) if r_em else None
            pend_raw = pending_by_lead.get(lead_id_s)
            pend_em = normalize_export_email(pend_raw) if pend_raw else None

            org_name_norm = normalize_org_name(str(org_name or ""))
            cls = classify_overlap_row(
                org_domain=org_domain,
                lead_em=lead_em,
                res_em=res_em,
                pend_em=pend_em,
                suppressed_norms=suppressed_norms,
                suppressed_domains=suppressed_domains,
                sent_norms=sent_norms,
                sent_last=sent_last,
                outreach_block=outreach_block,
                contacted_domains=contacted_domains,
                ref_org_norms=ref_org_norms,
                org_name_norm=org_name_norm,
            )
            rows_out.append(
                {
                    "lead_id": lead_id_s,
                    "organization_name": str(org_name or "").strip(),
                    "organization_domain": org_domain,
                    "fit_bucket": str(fit_bucket or "").strip(),
                    "lead_email": lead_em or "",
                    "researched_email": res_em or "",
                    "pending_research_email": pend_em or "",
                    **cls,
                }
            )

    for r in csv_only_rows:
        lid_s = (r.get("lead_id") or "").strip()
        if lid_s and lid_s in seen_lead_keys:
            continue
        org = first_nonempty_csv_value(r, _CSV_ORG_COLUMNS)
        source_val = first_nonempty_csv_value(r, _CSV_SOURCE_COLUMNS)
        org_domain = org_domain_for_lead(
            r.get("resolved_domain") or r.get("organization_domain") or r.get("domain"),
            domain_from_source_url(source_val),
        )
        pend_em = normalize_export_email(first_nonempty_csv_value(r, _CSV_EMAIL_COLUMNS))
        org_name_norm = normalize_org_name(org)
        cls = classify_overlap_row(
            org_domain=org_domain,
            lead_em=None,
            res_em=None,
            pend_em=pend_em,
            suppressed_norms=suppressed_norms,
            suppressed_domains=suppressed_domains,
            sent_norms=sent_norms,
            sent_last=sent_last,
            outreach_block=outreach_block,
            contacted_domains=contacted_domains,
            ref_org_norms=ref_org_norms,
            org_name_norm=org_name_norm,
        )
        rows_out.append(
            {
                "lead_id": lid_s,
                "organization_name": org,
                "organization_domain": org_domain,
                "fit_bucket": "",
                "lead_email": "",
                "researched_email": "",
                "pending_research_email": pend_em or "",
                **cls,
            }
        )

    return rows_out


def summarize_contacted_lead_overlap(
    rows: list[dict[str, object]],
    *,
    pending_stats: PendingResearchCsvStats,
    sample_limit: int,
) -> ContactedLeadOverlapSummary:
    total = len(rows)
    exact_sent = sum(
        1
        for r in rows
        if str(r.get("match_type", "")).endswith("_sent")
        and int(r.get("blocked_by_sent", 0) or 0) == 1
    )
    exact_state = sum(
        1
        for r in rows
        if str(r.get("match_type", "")).endswith("_state")
        and int(r.get("blocked_by_outreach_state", 0) or 0) == 1
    )
    any_outreach_block = sum(
        1 for r in rows if int(r.get("blocked_by_outreach_state", 0) or 0) == 1
    )
    same_dom = sum(1 for r in rows if r.get("match_type") == "same_domain_contacted")
    supp = sum(
        1
        for r in rows
        if str(r.get("match_type", "")).startswith("suppression")
        or int(r.get("blocked_by_email_suppression", 0) or 0) == 1
        or int(r.get("blocked_by_domain_suppression", 0) or 0) == 1
    )
    safe = sum(1 for r in rows if r.get("recommended_action") == "safe_for_gate_check")
    pending_exact_sent = sum(
        1
        for r in rows
        if str(r.get("pending_research_email", "")).strip()
        and r.get("match_type") == "exact_pending_email_sent"
    )
    pending_exact_state = sum(
        1
        for r in rows
        if str(r.get("pending_research_email", "")).strip()
        and r.get("match_type") == "exact_pending_email_state"
    )
    pending_suppressed = sum(
        1
        for r in rows
        if str(r.get("pending_research_email", "")).strip()
        and (
            int(r.get("blocked_by_email_suppression", 0) or 0) == 1
            or int(r.get("blocked_by_domain_suppression", 0) or 0) == 1
        )
    )
    overlap_counter: Counter[str] = Counter()
    for r in rows:
        if r.get("recommended_action") != "safe_for_gate_check":
            nm = str(r.get("organization_name") or "").strip() or str(r.get("organization_domain") or "")
            if nm:
                overlap_counter[nm] += 1
    topn = overlap_counter.most_common(int(sample_limit))
    return ContactedLeadOverlapSummary(
        total=total,
        exact_sent=exact_sent,
        exact_state=exact_state,
        any_outreach_block=any_outreach_block,
        same_dom=same_dom,
        supp=supp,
        safe=safe,
        pending_scanned=pending_stats.rows_scanned,
        pending_exact_sent=pending_exact_sent,
        pending_exact_state=pending_exact_state,
        pending_suppressed=pending_suppressed,
        pending_malformed_rows=pending_stats.malformed_rows,
        top_organizations=topn,
    )


def write_contacted_lead_overlap_csv(
    out_path: Path,
    rows: list[dict[str, object]],
    *,
    limit: int,
) -> int:
    """Sort, trim, and write CSV; returns number of rows written."""
    sorted_rows = sorted(
        rows,
        key=lambda r: (
            action_rank(str(r.get("recommended_action", ""))),
            str(r.get("organization_name", "")),
            str(r.get("lead_id", "")),
        ),
    )
    trimmed = sorted_rows[: int(limit)]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CONTACTED_LEAD_OVERLAP_FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for r in trimmed:
            out = {k: r.get(k, "") for k in CONTACTED_LEAD_OVERLAP_FIELDNAMES}
            for bkey in (
                "already_contacted",
                "blocked_by_sent",
                "blocked_by_outreach_state",
                "blocked_by_email_suppression",
                "blocked_by_domain_suppression",
            ):
                out[bkey] = int(out[bkey] or 0) if isinstance(out[bkey], (int, bool)) else int(out[bkey] or 0)
            w.writerow(out)
    return len(trimmed)


def print_contacted_lead_overlap_summary(
    summary: ContactedLeadOverlapSummary,
    *,
    out_path: Path,
    rows_written: int,
    sample_limit: int,
) -> None:
    top_s = (
        ", ".join(f"{n}({c})" for n, c in summary.top_organizations)
        if summary.top_organizations
        else "(none)"
    )
    print(f"Wrote {rows_written} rows to {out_path}")
    print(f"total leads/research rows scanned: {summary.total}")
    print(f"exact email already sent (match_type *_sent): {summary.exact_sent}")
    print(f"exact email already in outreach_contact_state (match_type *_state): {summary.exact_state}")
    print(f"rows with any outreach_contact_state block (contacted/replied/snoozed): {summary.any_outreach_block}")
    print(f"same-domain contacted hints: {summary.same_dom}")
    print(f"suppression hits: {summary.supp}")
    print(f"likely safe / no overlap: {summary.safe}")
    print(f"pending CSV rows scanned: {summary.pending_scanned}")
    print(f"pending exact sent hits: {summary.pending_exact_sent}")
    print(f"pending exact outreach state hits: {summary.pending_exact_state}")
    print(f"pending suppressed hits: {summary.pending_suppressed}")
    if summary.pending_scanned:
        print(f"pending malformed CSV rows ignored: {summary.pending_malformed_rows}")
    print(f"top {sample_limit} organizations with overlap: {top_s}")
