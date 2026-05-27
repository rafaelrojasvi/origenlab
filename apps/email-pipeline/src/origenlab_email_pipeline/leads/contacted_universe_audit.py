"""Read-only contacted-universe audit for no-repeat prospecting (Phase 10A)."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import domain_of, emails_in
from origenlab_email_pipeline.candidate_export_gate import (
    REASON_DOMAIN_SUPPRESSION,
    REASON_INTERNAL_DOMAIN,
    REASON_INVALID_EMAIL,
    REASON_NOISE_EMAIL,
    REASON_OUTREACH_CONTACTED,
    REASON_OUTREACH_REPLIED,
    REASON_OUTREACH_SNOOZED,
    REASON_SENT_HISTORY,
    REASON_SUPPRESSION,
    REASON_SUPPLIER_DOMAIN,
    GateContext,
    email_domain_under_operator_domain_suppression,
    evaluate_export_eligibility,
    normalize_export_email,
)
from origenlab_email_pipeline.marketing_export_context import (
    DEFAULT_EXCLUDE_DOMAINS,
    build_marketing_export_gate_context,
    load_sent_recipient_norms,
    load_suppressed_norms,
)
from origenlab_email_pipeline.marketing_supplier_domains import is_supplier_email_domain

CONTACT_CSV_FIELDS: tuple[str, ...] = (
    "normalized_email",
    "domain",
    "display_name",
    "organization_name",
    "first_contacted_at",
    "last_contacted_at",
    "sent_count",
    "received_count",
    "replied_bool",
    "bounced_bool",
    "suppressed_bool",
    "outreach_state",
    "role_guess",
    "buyer_type_guess",
    "product_interest_guess",
    "latest_subject_safe",
    "recommended_status",
    "reason_codes",
)

DOMAIN_CSV_FIELDS: tuple[str, ...] = (
    "domain",
    "organization_name",
    "sent_count",
    "received_count",
    "unique_contacts",
    "bounced_count",
    "suppressed_bool",
    "supplier_bool",
    "internal_bool",
    "buyer_type_guess",
    "latest_contacted_at",
    "recommended_status",
    "reason_codes",
)

RECOMMENDED_ALREADY_CONTACTED = "already_contacted"
RECOMMENDED_FOLLOW_UP = "follow_up_candidate"
RECOMMENDED_BOUNCED = "bounced_do_not_contact"
RECOMMENDED_SUPPLIER = "supplier_do_not_market"
RECOMMENDED_INTERNAL = "internal_do_not_market"
RECOMMENDED_UNKNOWN = "unknown_review"

NET_NEW_SAFE = "net_new_safe"
NET_NEW_ALREADY_CONTACTED = "already_contacted"
NET_NEW_SAME_DOMAIN_REVIEW = "same_domain_contacted_review"
NET_NEW_BOUNCED_BLOCK = "bounced_block"
NET_NEW_SUPPRESSED_BLOCK = "suppressed_block"
NET_NEW_SUPPLIER_BLOCK = "supplier_block"
NET_NEW_INTERNAL_BLOCK = "internal_block"
NET_NEW_INVALID = "invalid_or_noise"

_BOUNCE_REASON_PREFIX = "bounce_"
_MAX_SUBJECT_LEN = 160

EXACT_EMAIL_EXCLUSION_FIELDS: tuple[str, ...] = (
    "normalized_email",
    "domain",
    "organization_name",
    "last_contacted_at",
    "sent_count",
    "received_count",
    "recommended_status",
    "reason_codes",
)

DOMAIN_EXCLUSION_FIELDS: tuple[str, ...] = (
    "domain",
    "organization_name",
    "sent_count",
    "received_count",
    "unique_contacts",
    "bounced_count",
    "recommended_status",
    "reason_codes",
)

BOUNCED_EMAIL_EXCLUSION_FIELDS: tuple[str, ...] = (
    "normalized_email",
    "domain",
    "organization_name",
    "last_contacted_at",
    "recommended_status",
    "reason_codes",
)

SUPPRESSED_CONTACT_EXCLUSION_FIELDS: tuple[str, ...] = (
    "normalized_email",
    "domain",
    "organization_name",
    "suppressed_bool",
    "recommended_status",
    "reason_codes",
)

FOLLOW_UP_REVIEW_FIELDS: tuple[str, ...] = (
    "normalized_email",
    "domain",
    "organization_name",
    "first_contacted_at",
    "last_contacted_at",
    "sent_count",
    "received_count",
    "latest_subject_safe",
    "buyer_type_guess",
    "product_interest_guess",
    "recommended_follow_up_angle",
    "reason_codes",
)

NOISY_CONTACT_REVIEW_FIELDS: tuple[str, ...] = (
    "normalized_email",
    "domain",
    "display_name",
    "organization_name",
    "role_guess",
    "sent_count",
    "received_count",
    "recommended_status",
    "noise_reason_codes",
)

_NOISE_LOCAL_MARKERS: tuple[str, ...] = (
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "unsubscribe",
    "envioscompilado",
    "mailer-daemon",
    "postmaster",
)

_SUPPLIER_MARKETPLACE_DOMAIN_MARKERS: tuple[str, ...] = (
    "suppliermarketplace",
    "verifiedsupplier",
    "chinalabsupplies",
    "chromatography.ltd",
)

_FREEMAIL_DOMAINS: frozenset[str] = frozenset(
    {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "icloud.com", "live.com"}
)

_CLIENT_SUBJECT_MARKERS: tuple[str, ...] = (
    "cotiz",
    "cotización",
    "quote",
    "presupuesto",
    "equipo",
    "licit",
    "oportunidad",
    "solicitud",
    "re:",
)

_RANDOM_DOMAIN_RE = re.compile(r"^[a-z0-9.-]+$")


@dataclass
class EmailActivity:
    sent_count: int = 0
    received_count: int = 0
    first_contacted_at: str = ""
    last_contacted_at: str = ""
    latest_subject_safe: str = ""


@dataclass
class ContactedUniverseContext:
    """Immutable inputs for eligibility and reporting."""

    gate: GateContext
    bounced_emails: frozenset[str]
    suppression_reason_by_email: dict[str, str]
    all_outreach_state: dict[str, str]
    supplier_domains: frozenset[str]
    blocked_domains: frozenset[str]
    do_not_repeat_emails: frozenset[str]
    domains_with_sent_contact: frozenset[str]
    warm_opportunity_contacts: frozenset[str]


@dataclass
class FilteredUniverseExports:
    exact_emails: list[dict[str, str]]
    domains_exclusion: list[dict[str, str]]
    bounced_emails: list[dict[str, str]]
    suppressed_contacts: list[dict[str, str]]
    follow_up_candidates: list[dict[str, str]]
    noisy_contacts: list[dict[str, str]]


@dataclass
class ContactedUniverseResult:
    summary: dict[str, Any]
    contacts: list[dict[str, str]]
    domains: list[dict[str, str]]
    filtered: FilteredUniverseExports


def _int_field(row: dict[str, str], key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except ValueError:
        return 0


def _bool_field(row: dict[str, str], key: str) -> bool:
    return str(row.get(key) or "").lower() == "true"


def _suspicious_random_domain(domain: str) -> bool:
    d = (domain or "").strip().lower()
    if not d or "." not in d:
        return True
    registrable = d.split(".")[-2] if d.count(".") >= 1 else d
    label = registrable.replace("-", "")
    if len(label) < 10:
        return False
    if not _RANDOM_DOMAIN_RE.match(d):
        return True
    vowels = sum(1 for c in label if c in "aeiou")
    if len(label) >= 12 and vowels / len(label) < 0.15:
        return True
    digits = sum(1 for c in label if c.isdigit())
    if digits >= 4 and digits / len(label) >= 0.35:
        return True
    return False


def classify_contact_noise(row: dict[str, str]) -> tuple[bool, list[str]]:
    """Return (is_noisy, stable noise reason codes) for prospect-review filtering."""
    email = (row.get("normalized_email") or "").strip().lower()
    domain = (row.get("domain") or domain_of(email) or "").strip().lower()
    local = email.split("@", 1)[0] if "@" in email else email
    reasons: list[str] = []

    if not email or "@" not in email:
        reasons.append("noise_invalid_email")
        return True, reasons

    if "mailer-daemon" in email or "postmaster" in email:
        reasons.append("noise_system_mailbox")
    for marker in _NOISE_LOCAL_MARKERS:
        if marker in local:
            reasons.append(f"noise_local_{marker.replace('-', '_')}")
            break

    role = (row.get("role_guess") or "").strip().lower()
    if role in ("noise", "admin"):
        reasons.append(f"noise_role_{role}")

    if len(local) >= 6:
        digits = sum(1 for c in local if c.isdigit())
        if digits / len(local) >= 0.6:
            reasons.append("noise_numeric_local")

    for marker in _SUPPLIER_MARKETPLACE_DOMAIN_MARKERS:
        if marker in domain:
            reasons.append("noise_supplier_marketplace")
            break

    if _suspicious_random_domain(domain):
        reasons.append("noise_suspicious_domain")

    if domain.endswith(".cn") and any(
        x in domain for x in ("supplier", "trade", "export", "ltd", "market")
    ):
        reasons.append("noise_overseas_supplier_spam")

    if domain in _FREEMAIL_DOMAINS:
        has_context = bool((row.get("display_name") or "").strip()) or bool(
            (row.get("organization_name") or "").strip()
        )
        if not has_context and _int_field(row, "sent_count") == 0 and _int_field(row, "received_count") == 0:
            reasons.append("noise_generic_freemail")

    return bool(reasons), list(dict.fromkeys(reasons))


def _subject_suggests_client_thread(subject: str) -> bool:
    s = (subject or "").lower()
    return any(m in s for m in _CLIENT_SUBJECT_MARKERS)


def _follow_up_angle(
    row: dict[str, str],
    *,
    warm_contacts: frozenset[str],
) -> str:
    em = row.get("normalized_email") or ""
    subj = (row.get("latest_subject_safe") or "").lower()
    if em in warm_contacts:
        return "warm_opportunity_signal"
    if _bool_field(row, "replied_bool") and _subject_suggests_client_thread(subj):
        return "reply_to_quote_thread"
    if _subject_suggests_client_thread(subj):
        return "client_request_follow_up"
    if _int_field(row, "sent_count") > 0 and not _bool_field(row, "replied_bool"):
        return "prior_outreach_no_reply"
    if _int_field(row, "received_count") > 0:
        return "inbound_thread_review"
    return "relationship_review"


def _include_exact_email(row: dict[str, str], ctx: ContactedUniverseContext) -> bool:
    if _int_field(row, "sent_count") > 0:
        return True
    state = (row.get("outreach_state") or "").strip().lower()
    if state in ("contacted", "snoozed", "replied"):
        return True
    if _bool_field(row, "bounced_bool") or _bool_field(row, "suppressed_bool"):
        return True
    em = row.get("normalized_email") or ""
    if em in ctx.gate.suppressed_norms:
        return True
    return False


def _include_domain_exclusion(row: dict[str, str]) -> bool:
    if _int_field(row, "sent_count") > 0:
        return True
    if _bool_field(row, "suppressed_bool"):
        return True
    if _bool_field(row, "supplier_bool"):
        return True
    if _bool_field(row, "internal_bool"):
        return True
    if _int_field(row, "bounced_count") > 0:
        return True
    return False


def _is_realistic_follow_up_candidate(
    row: dict[str, str],
    ctx: ContactedUniverseContext,
) -> bool:
    if _int_field(row, "sent_count") == 0 and _int_field(row, "received_count") == 0:
        return False
    if _bool_field(row, "bounced_bool") or _bool_field(row, "suppressed_bool"):
        return False
    role = (row.get("role_guess") or "").lower()
    if role in ("supplier", "internal", "noise", "admin"):
        return False
    if row.get("recommended_status") in (
        RECOMMENDED_BOUNCED,
        RECOMMENDED_SUPPLIER,
        RECOMMENDED_INTERNAL,
    ):
        return False
    noisy, _ = classify_contact_noise(row)
    if noisy:
        return False
    em = row.get("normalized_email") or ""
    if _bool_field(row, "replied_bool"):
        return True
    if em in ctx.warm_opportunity_contacts:
        return True
    if _subject_suggests_client_thread(row.get("latest_subject_safe") or ""):
        return True
    return False


def build_filtered_exports(
    contacts: list[dict[str, str]],
    domains: list[dict[str, str]],
    ctx: ContactedUniverseContext,
) -> FilteredUniverseExports:
    exact_emails: list[dict[str, str]] = []
    bounced_emails: list[dict[str, str]] = []
    suppressed_contacts: list[dict[str, str]] = []
    follow_up_candidates: list[dict[str, str]] = []
    noisy_contacts: list[dict[str, str]] = []

    for row in contacts:
        noisy, noise_reasons = classify_contact_noise(row)
        if noisy:
            noisy_contacts.append(
                {
                    **{k: row.get(k, "") for k in NOISY_CONTACT_REVIEW_FIELDS if k != "noise_reason_codes"},
                    "noise_reason_codes": "|".join(noise_reasons),
                }
            )

        if _include_exact_email(row, ctx):
            exact_emails.append({k: row.get(k, "") for k in EXACT_EMAIL_EXCLUSION_FIELDS})

        if _bool_field(row, "bounced_bool"):
            bounced_emails.append({k: row.get(k, "") for k in BOUNCED_EMAIL_EXCLUSION_FIELDS})

        if _bool_field(row, "suppressed_bool"):
            suppressed_contacts.append(
                {k: row.get(k, "") for k in SUPPRESSED_CONTACT_EXCLUSION_FIELDS}
            )

        if _is_realistic_follow_up_candidate(row, ctx):
            angle = _follow_up_angle(row, warm_contacts=ctx.warm_opportunity_contacts)
            follow_up_candidates.append(
                {
                    **{k: row.get(k, "") for k in FOLLOW_UP_REVIEW_FIELDS if k != "recommended_follow_up_angle"},
                    "recommended_follow_up_angle": angle,
                }
            )

    domains_exclusion = [
        {k: row.get(k, "") for k in DOMAIN_EXCLUSION_FIELDS}
        for row in domains
        if _include_domain_exclusion(row)
    ]

    return FilteredUniverseExports(
        exact_emails=exact_emails,
        domains_exclusion=domains_exclusion,
        bounced_emails=bounced_emails,
        suppressed_contacts=suppressed_contacts,
        follow_up_candidates=follow_up_candidates,
        noisy_contacts=noisy_contacts,
    )


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _emails_date_expr(conn: sqlite3.Connection) -> str:
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(emails)").fetchall()}
    if "date_raw" in cols:
        return "COALESCE(NULLIF(TRIM(date_iso), ''), NULLIF(TRIM(date_raw), ''), '')"
    return "COALESCE(NULLIF(TRIM(date_iso), ''), '')"


def _safe_subject(subject: str | None) -> str:
    s = " ".join(str(subject or "").split())
    if len(s) > _MAX_SUBJECT_LEN:
        return s[: _MAX_SUBJECT_LEN - 3] + "..."
    return s


def load_do_not_repeat_emails_from_csv(path: Path) -> frozenset[str]:
    if not path.is_file():
        return frozenset()
    out: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw = (row.get("email_norm") or row.get("email") or row.get("contact_email") or "").strip()
            if not raw:
                continue
            found = emails_in(raw)
            if found:
                out.add(found[0])
    return frozenset(out)


def _load_sent_activity(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
) -> tuple[dict[str, EmailActivity], int]:
    """Per-recipient Sent stats and total Sent row count."""
    if not _table_exists(conn, "emails"):
        return {}, 0
    user = gmail_user.strip()
    folders = tuple(f.strip() for f in sent_folders if f.strip())
    if not user or not folders:
        return {}, 0
    like_pat = f"gmail:{user}/%".lower()
    ph = ",".join("?" * len(folders))
    date_expr = _emails_date_expr(conn)
    cur = conn.execute(
        f"""
        SELECT recipients, subject, {date_expr} AS dts
        FROM emails
        WHERE lower(source_file) LIKE ?
          AND folder IN ({ph})
        """,
        (like_pat, *folders),
    )
    per_email: dict[str, EmailActivity] = {}
    total_sent_rows = 0
    for recipients, subject, dts in cur:
        total_sent_rows += 1
        ds = str(dts or "").strip()
        subj = _safe_subject(subject)
        if not recipients:
            continue
        for em in emails_in(recipients):
            act = per_email.setdefault(em, EmailActivity())
            act.sent_count += 1
            if ds:
                if not act.first_contacted_at or ds < act.first_contacted_at:
                    act.first_contacted_at = ds
                if not act.last_contacted_at or ds > act.last_contacted_at:
                    act.last_contacted_at = ds
            if subj and (not act.latest_subject_safe or ds >= act.last_contacted_at):
                act.latest_subject_safe = subj
    return per_email, total_sent_rows


def _load_inbound_activity(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
) -> dict[str, EmailActivity]:
    """Inbound messages to contacto mailbox from external senders (non-Sent folders)."""
    if not _table_exists(conn, "emails"):
        return {}
    user = gmail_user.strip()
    folders = tuple(f.strip() for f in sent_folders if f.strip())
    if not user:
        return {}
    like_pat = f"gmail:{user}/%".lower()
    sent_ph = ",".join("?" * len(folders)) if folders else "''"
    date_expr = _emails_date_expr(conn)
    if folders:
        sql = f"""
            SELECT sender, subject, {date_expr} AS dts
            FROM emails
            WHERE lower(source_file) LIKE ?
              AND folder NOT IN ({sent_ph})
        """
        params: tuple[Any, ...] = (like_pat, *folders)
    else:
        sql = f"""
            SELECT sender, subject, {date_expr} AS dts
            FROM emails
            WHERE lower(source_file) LIKE ?
        """
        params = (like_pat,)
    per_email: dict[str, EmailActivity] = {}
    for sender, subject, dts in conn.execute(sql, params):
        em = emails_in(sender)
        if not em:
            continue
        addr = em[0]
        dom = domain_of(addr) or ""
        if dom in DEFAULT_EXCLUDE_DOMAINS:
            continue
        if "mailer-daemon" in addr or "postmaster" in addr:
            continue
        ds = str(dts or "").strip()
        subj = _safe_subject(subject)
        act = per_email.setdefault(addr, EmailActivity())
        act.received_count += 1
        if ds and (not act.last_contacted_at or ds > act.last_contacted_at):
            act.last_contacted_at = ds
            if subj:
                act.latest_subject_safe = subj
    return per_email


def _load_suppression_detail(conn: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(conn, "contact_email_suppression"):
        return {}
    rows = conn.execute(
        """
        SELECT lower(trim(email)) AS e,
               lower(trim(suppression_reason_code)) AS c
        FROM contact_email_suppression
        WHERE length(trim(email)) > 0
        """
    ).fetchall()
    return {str(e): str(c or "") for e, c in rows if e}


def _load_all_outreach_state(conn: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(conn, "outreach_contact_state"):
        return {}
    rows = conn.execute(
        """
        SELECT lower(trim(contact_email_norm)) AS e, lower(trim(state)) AS s
        FROM outreach_contact_state
        WHERE length(trim(contact_email_norm)) > 0
        """
    ).fetchall()
    return {str(e): str(s) for e, s in rows if e and s}


def _load_contact_master(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    if not _table_exists(conn, "contact_master"):
        return {}
    rows = conn.execute(
        """
        SELECT lower(trim(email)) AS e,
               COALESCE(contact_name_best, '') AS name,
               COALESCE(organization_name_guess, '') AS org,
               COALESCE(organization_type_guess, '') AS org_type,
               COALESCE(domain, '') AS dom
        FROM contact_master
        WHERE length(trim(email)) > 0
        """
    ).fetchall()
    return {
        str(e): {
            "display_name": str(name or ""),
            "organization_name": str(org or ""),
            "buyer_type_guess": str(org_type or ""),
            "domain": str(dom or ""),
        }
        for e, name, org, org_type, dom in rows
        if e
    }


def _load_organization_master(conn: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(conn, "organization_master"):
        return {}
    rows = conn.execute(
        """
        SELECT lower(trim(domain)) AS d, COALESCE(organization_name_guess, '') AS org
        FROM organization_master
        WHERE length(trim(domain)) > 0
        """
    ).fetchall()
    return {str(d): str(org or "") for d, org in rows if d}


def _load_warm_opportunity_contacts(conn: sqlite3.Connection) -> frozenset[str]:
    if not _table_exists(conn, "opportunity_signals"):
        return frozenset()
    rows = conn.execute(
        """
        SELECT lower(trim(entity_key)) AS k
        FROM opportunity_signals
        WHERE lower(trim(entity_kind)) = 'contact'
          AND length(trim(entity_key)) > 0
        """
    ).fetchall()
    return frozenset(str(r[0]) for r in rows if r[0])


def _merge_activity(
    sent: dict[str, EmailActivity],
    inbound: dict[str, EmailActivity],
) -> dict[str, EmailActivity]:
    keys = set(sent) | set(inbound)
    out: dict[str, EmailActivity] = {}
    for em in keys:
        s = sent.get(em, EmailActivity())
        i = inbound.get(em, EmailActivity())
        firsts = [d for d in (s.first_contacted_at, i.first_contacted_at) if d]
        lasts = [d for d in (s.last_contacted_at, i.last_contacted_at) if d]
        subj = s.latest_subject_safe or i.latest_subject_safe
        out[em] = EmailActivity(
            sent_count=s.sent_count,
            received_count=i.received_count,
            first_contacted_at=min(firsts) if firsts else "",
            last_contacted_at=max(lasts) if lasts else "",
            latest_subject_safe=subj,
        )
    return out


def _bounced_emails(suppression_detail: dict[str, str]) -> frozenset[str]:
    return frozenset(
        e
        for e, code in suppression_detail.items()
        if code.startswith(_BOUNCE_REASON_PREFIX) or code == "reported_non_delivery"
    )


def _guess_role(
    email: str,
    domain: str,
    *,
    supplier_domains: frozenset[str],
    blocked_domains: frozenset[str],
    sent_count: int,
) -> str:
    if domain in blocked_domains or email.endswith("@origenlab.cl"):
        return "internal"
    if is_supplier_email_domain(email, supplier_domains):
        return "supplier"
    if "mailer-daemon" in email or "postmaster" in email:
        return "noise"
    if any(x in email for x in ("noreply", "no-reply", "donotreply")):
        return "admin"
    if sent_count > 0 or domain not in blocked_domains:
        return "client"
    return "unknown"


def _reason_codes_for_contact(
    email: str,
    domain: str,
    *,
    ctx: ContactedUniverseContext,
    bounced: bool,
    suppressed: bool,
) -> str:
    codes: list[str] = []
    gate = evaluate_export_eligibility(
        contact_email=email,
        institution_name=None,
        ctx=ctx.gate,
    )
    codes.extend(gate.reasons)
    if bounced and REASON_SUPPRESSION not in codes:
        codes.append("bounce_suppression")
    if email in ctx.do_not_repeat_emails:
        codes.append("do_not_repeat_master")
    if email in ctx.warm_opportunity_contacts:
        codes.append("warm_opportunity_signal")
    if suppressed and REASON_DOMAIN_SUPPRESSION not in codes and REASON_SUPPRESSION not in codes:
        codes.append("suppressed")
    return "|".join(dict.fromkeys(codes))


def _recommended_contact_status(
    email: str,
    domain: str,
    *,
    ctx: ContactedUniverseContext,
    bounced: bool,
    suppressed: bool,
    outreach_state: str,
    sent_count: int,
    received_count: int,
) -> str:
    if bounced:
        return RECOMMENDED_BOUNCED
    if email in ctx.gate.suppressed_norms:
        return RECOMMENDED_BOUNCED if email in ctx.bounced_emails else RECOMMENDED_UNKNOWN
    if domain in ctx.blocked_domains:
        return RECOMMENDED_INTERNAL
    if email_domain_under_operator_domain_suppression(
        domain, ctx.gate.suppressed_contact_domains
    ):
        return RECOMMENDED_UNKNOWN
    if is_supplier_email_domain(email, ctx.supplier_domains):
        return RECOMMENDED_SUPPLIER
    if outreach_state == "replied" or (received_count > 0 and sent_count > 0):
        return RECOMMENDED_FOLLOW_UP
    if (
        email in ctx.gate.sent_recipient_norms
        or outreach_state in ("contacted", "snoozed")
        or email in ctx.do_not_repeat_emails
    ):
        return RECOMMENDED_ALREADY_CONTACTED
    if sent_count > 0:
        return RECOMMENDED_ALREADY_CONTACTED
    return RECOMMENDED_UNKNOWN


def classify_net_new_eligibility(
    email: str | None,
    domain: str | None = None,
    *,
    ctx: ContactedUniverseContext,
) -> str:
    """Classify a prospect candidate email/domain before DeepSearch outreach."""
    em = normalize_export_email(email or "")
    if not em:
        return NET_NEW_INVALID
    dom = (domain or domain_of(em) or "").strip().lower()
    if not dom:
        return NET_NEW_INVALID

    if dom in ctx.blocked_domains:
        return NET_NEW_INTERNAL_BLOCK

    gate = evaluate_export_eligibility(contact_email=em, institution_name=None, ctx=ctx.gate)
    if not gate.eligible:
        reason = gate.reasons[0] if gate.reasons else ""
        if reason == REASON_SUPPRESSION and em in ctx.bounced_emails:
            return NET_NEW_BOUNCED_BLOCK
        if reason == REASON_SUPPRESSION:
            return NET_NEW_SUPPRESSED_BLOCK
        if reason == REASON_DOMAIN_SUPPRESSION:
            return NET_NEW_SUPPRESSED_BLOCK
        if reason == REASON_SUPPLIER_DOMAIN:
            return NET_NEW_SUPPLIER_BLOCK
        if reason == REASON_INTERNAL_DOMAIN:
            return NET_NEW_INTERNAL_BLOCK
        if reason in (REASON_SENT_HISTORY, REASON_OUTREACH_CONTACTED, REASON_OUTREACH_SNOOZED):
            return NET_NEW_ALREADY_CONTACTED
        if reason in (REASON_OUTREACH_REPLIED,):
            return NET_NEW_ALREADY_CONTACTED
        if reason in (REASON_INVALID_EMAIL, REASON_NOISE_EMAIL):
            return NET_NEW_INVALID

    if em in ctx.bounced_emails:
        return NET_NEW_BOUNCED_BLOCK
    if em in ctx.do_not_repeat_emails:
        return NET_NEW_ALREADY_CONTACTED

    if dom in ctx.domains_with_sent_contact and em not in ctx.gate.sent_recipient_norms:
        return NET_NEW_SAME_DOMAIN_REVIEW

    return NET_NEW_SAFE


def build_contacted_universe_context(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
    do_not_repeat_csv: Path | None = None,
) -> tuple[ContactedUniverseContext, dict[str, EmailActivity], int]:
    gate = build_marketing_export_gate_context(
        conn, gmail_user=gmail_user, sent_folders=sent_folders
    )
    suppression_detail = _load_suppression_detail(conn)
    bounced = _bounced_emails(suppression_detail)
    all_outreach = _load_all_outreach_state(conn)
    from origenlab_email_pipeline.marketing_supplier_domains import supplier_email_domains

    supplier_domains = supplier_email_domains(conn)
    blocked = frozenset(
        d.strip().lower() for d in DEFAULT_EXCLUDE_DOMAINS if d.strip()
    )
    dnr_emails: frozenset[str] = frozenset()
    if do_not_repeat_csv and do_not_repeat_csv.is_file():
        dnr_emails = load_do_not_repeat_emails_from_csv(do_not_repeat_csv)

    domains_with_sent: set[str] = set()
    for em in gate.sent_recipient_norms:
        d = domain_of(em)
        if d:
            domains_with_sent.add(d)

    warm = _load_warm_opportunity_contacts(conn)
    sent_activity, total_sent_rows = _load_sent_activity(
        conn, gmail_user=gmail_user, sent_folders=sent_folders
    )
    inbound_activity = _load_inbound_activity(
        conn, gmail_user=gmail_user, sent_folders=sent_folders
    )

    ctx = ContactedUniverseContext(
        gate=gate,
        bounced_emails=bounced,
        suppression_reason_by_email=suppression_detail,
        all_outreach_state=all_outreach,
        supplier_domains=supplier_domains,
        blocked_domains=blocked,
        do_not_repeat_emails=dnr_emails | gate.sent_recipient_norms | frozenset(all_outreach.keys()),
        domains_with_sent_contact=frozenset(domains_with_sent),
        warm_opportunity_contacts=warm,
    )
    activity = _merge_activity(sent_activity, inbound_activity)
    return ctx, activity, total_sent_rows


def build_contacted_universe(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
    do_not_repeat_csv: Path | None = None,
) -> ContactedUniverseResult:
    ctx, activity, total_sent_rows = build_contacted_universe_context(
        conn,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        do_not_repeat_csv=do_not_repeat_csv,
    )
    contact_master = _load_contact_master(conn)
    org_by_domain = _load_organization_master(conn)

    universe_emails: set[str] = set()
    universe_emails |= set(activity.keys())
    universe_emails |= set(ctx.gate.suppressed_norms)
    universe_emails |= set(ctx.all_outreach_state.keys())
    universe_emails |= set(ctx.do_not_repeat_emails)
    universe_emails |= set(contact_master.keys())

    contacts_out: list[dict[str, str]] = []
    domain_agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "sent_count": 0,
            "received_count": 0,
            "unique_contacts": 0,
            "bounced_count": 0,
            "suppressed_bool": False,
            "supplier_bool": False,
            "internal_bool": False,
            "latest_contacted_at": "",
            "contacts": set(),
        }
    )

    for em in sorted(universe_emails):
        dom = domain_of(em) or ""
        act = activity.get(em, EmailActivity())
        cm = contact_master.get(em, {})
        org_name = cm.get("organization_name") or org_by_domain.get(dom, "")
        display = cm.get("display_name", "")
        buyer_type = cm.get("buyer_type_guess", "")
        outreach_state = ctx.all_outreach_state.get(em, "")
        bounced = em in ctx.bounced_emails
        suppressed = (
            em in ctx.gate.suppressed_norms
            or email_domain_under_operator_domain_suppression(
                dom, ctx.gate.suppressed_contact_domains
            )
        )
        replied = outreach_state == "replied" or (act.received_count > 0 and act.sent_count > 0)
        role = _guess_role(
            em,
            dom,
            supplier_domains=ctx.supplier_domains,
            blocked_domains=ctx.blocked_domains,
            sent_count=act.sent_count,
        )
        rec = _recommended_contact_status(
            em,
            dom,
            ctx=ctx,
            bounced=bounced,
            suppressed=suppressed,
            outreach_state=outreach_state,
            sent_count=act.sent_count,
            received_count=act.received_count,
        )
        reasons = _reason_codes_for_contact(
            em, dom, ctx=ctx, bounced=bounced, suppressed=suppressed
        )
        row = {
            "normalized_email": em,
            "domain": dom,
            "display_name": display,
            "organization_name": org_name,
            "first_contacted_at": act.first_contacted_at,
            "last_contacted_at": act.last_contacted_at,
            "sent_count": str(act.sent_count),
            "received_count": str(act.received_count),
            "replied_bool": "true" if replied else "false",
            "bounced_bool": "true" if bounced else "false",
            "suppressed_bool": "true" if suppressed else "false",
            "outreach_state": outreach_state,
            "role_guess": role,
            "buyer_type_guess": buyer_type,
            "product_interest_guess": "",
            "latest_subject_safe": act.latest_subject_safe,
            "recommended_status": rec,
            "reason_codes": reasons,
        }
        contacts_out.append(row)

        if not dom:
            continue
        dag = domain_agg[dom]
        dag["contacts"].add(em)
        dag["sent_count"] += act.sent_count
        dag["received_count"] += act.received_count
        if bounced:
            dag["bounced_count"] += 1
        if suppressed:
            dag["suppressed_bool"] = True
        if is_supplier_email_domain(f"x@{dom}", ctx.supplier_domains):
            dag["supplier_bool"] = True
        if dom in ctx.blocked_domains:
            dag["internal_bool"] = True
        if act.last_contacted_at and (
            not dag["latest_contacted_at"] or act.last_contacted_at > dag["latest_contacted_at"]
        ):
            dag["latest_contacted_at"] = act.last_contacted_at

    domains_out: list[dict[str, str]] = []
    for dom in sorted(domain_agg.keys()):
        dag = domain_agg[dom]
        n_contacts = len(dag["contacts"])
        supplier = bool(dag["supplier_bool"])
        internal = bool(dag["internal_bool"])
        domain_suppressed = email_domain_under_operator_domain_suppression(
            dom, ctx.gate.suppressed_contact_domains
        )
        if dag["bounced_count"] == n_contacts and n_contacts > 0:
            d_status = RECOMMENDED_BOUNCED
        elif supplier:
            d_status = RECOMMENDED_SUPPLIER
        elif internal:
            d_status = RECOMMENDED_INTERNAL
        elif dom in ctx.domains_with_sent_contact:
            d_status = RECOMMENDED_ALREADY_CONTACTED
        elif domain_suppressed:
            d_status = RECOMMENDED_UNKNOWN
        else:
            d_status = RECOMMENDED_UNKNOWN
        d_reasons: list[str] = []
        if dom in ctx.domains_with_sent_contact:
            d_reasons.append(REASON_SENT_HISTORY)
        if domain_suppressed:
            d_reasons.append(REASON_DOMAIN_SUPPRESSION)
        if supplier:
            d_reasons.append(REASON_SUPPLIER_DOMAIN)
        if internal:
            d_reasons.append(REASON_INTERNAL_DOMAIN)
        domains_out.append(
            {
                "domain": dom,
                "organization_name": org_by_domain.get(dom, ""),
                "sent_count": str(dag["sent_count"]),
                "received_count": str(dag["received_count"]),
                "unique_contacts": str(n_contacts),
                "bounced_count": str(dag["bounced_count"]),
                "suppressed_bool": "true" if dag["suppressed_bool"] or domain_suppressed else "false",
                "supplier_bool": "true" if supplier else "false",
                "internal_bool": "true" if internal else "false",
                "buyer_type_guess": "",
                "latest_contacted_at": dag["latest_contacted_at"],
                "recommended_status": d_status,
                "reason_codes": "|".join(dict.fromkeys(d_reasons)),
            }
        )

    sent_emails = ctx.gate.sent_recipient_norms
    sent_domains = ctx.domains_with_sent_contact
    replied_contacts = sum(1 for r in contacts_out if r["replied_bool"] == "true")
    replied_domains = len(
        {r["domain"] for r in contacts_out if r["replied_bool"] == "true" and r["domain"]}
    )
    follow_up = sum(1 for r in contacts_out if r["recommended_status"] == RECOMMENDED_FOLLOW_UP)
    blocked = sum(
        1
        for r in contacts_out
        if r["recommended_status"]
        in (
            RECOMMENDED_BOUNCED,
            RECOMMENDED_SUPPLIER,
            RECOMMENDED_INTERNAL,
            RECOMMENDED_ALREADY_CONTACTED,
        )
        and r["recommended_status"] != RECOMMENDED_FOLLOW_UP
    )
    summary = {
        "total_sent_email_rows": total_sent_rows,
        "unique_outbound_recipient_emails": len(sent_emails),
        "unique_outbound_recipient_domains": len(sent_domains),
        "unique_organizations_touched": len(
            {d for d in sent_domains if d in org_by_domain or d}
        ),
        "bounced_recipient_emails": len(ctx.bounced_emails),
        "bounced_domains": len(
            {domain_of(e) for e in ctx.bounced_emails if domain_of(e)}
        ),
        "replied_contacts": replied_contacts,
        "replied_domains": replied_domains,
        "active_warm_opportunity_contacts": len(ctx.warm_opportunity_contacts),
        "supplier_domains": len(ctx.supplier_domains),
        "internal_admin_domains": len(
            {d for d in domain_agg if domain_agg[d]["internal_bool"]}
        ),
        "suppressed_contacts": len(ctx.gate.suppressed_norms),
        "suppressed_domains": len(ctx.gate.suppressed_contact_domains),
        "do_not_repeat_contacts": len(ctx.do_not_repeat_emails),
        "do_not_repeat_domains": len(
            {domain_of(e) for e in ctx.do_not_repeat_emails if domain_of(e)}
        ),
        "contacts_eligible_for_follow_up": follow_up,
        "contacts_blocked_from_outreach": blocked,
        "total_universe_contacts": len(contacts_out),
        "total_universe_domains": len(domains_out),
        "gmail_user": gmail_user,
        "sent_folders": list(sent_folders),
    }
    filtered = build_filtered_exports(contacts_out, domains_out, ctx)
    summary["exact_contacted_emails_for_exclusion"] = len(filtered.exact_emails)
    summary["contacted_domains_for_exclusion"] = len(filtered.domains_exclusion)
    summary["bounced_emails_for_exclusion"] = len(filtered.bounced_emails)
    summary["suppressed_contacts_for_exclusion"] = len(filtered.suppressed_contacts)
    summary["follow_up_candidates_review"] = len(filtered.follow_up_candidates)
    summary["noisy_contacts_review"] = len(filtered.noisy_contacts)
    return ContactedUniverseResult(
        summary=summary,
        contacts=contacts_out,
        domains=domains_out,
        filtered=filtered,
    )


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def write_contacted_universe_outputs(
    result: ContactedUniverseResult,
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "contacted_universe_summary.json"
    md_path = out_dir / "contacted_universe_summary.md"
    contacts_path = out_dir / "contacted_universe_contacts.csv"
    domains_path = out_dir / "contacted_universe_domains.csv"
    exact_path = out_dir / "contacted_exact_emails_for_exclusion.csv"
    domain_excl_path = out_dir / "contacted_domains_for_exclusion.csv"
    bounced_path = out_dir / "bounced_emails_for_exclusion.csv"
    suppressed_path = out_dir / "suppressed_contacts_for_exclusion.csv"
    follow_up_path = out_dir / "follow_up_candidates_review.csv"
    noisy_path = out_dir / "noisy_contacts_review.csv"

    json_path.write_text(
        json.dumps(result.summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    _write_csv(contacts_path, CONTACT_CSV_FIELDS, result.contacts)
    _write_csv(domains_path, DOMAIN_CSV_FIELDS, result.domains)

    filt = result.filtered
    _write_csv(exact_path, EXACT_EMAIL_EXCLUSION_FIELDS, filt.exact_emails)
    _write_csv(domain_excl_path, DOMAIN_EXCLUSION_FIELDS, filt.domains_exclusion)
    _write_csv(bounced_path, BOUNCED_EMAIL_EXCLUSION_FIELDS, filt.bounced_emails)
    _write_csv(suppressed_path, SUPPRESSED_CONTACT_EXCLUSION_FIELDS, filt.suppressed_contacts)
    _write_csv(follow_up_path, FOLLOW_UP_REVIEW_FIELDS, filt.follow_up_candidates)
    _write_csv(noisy_path, NOISY_CONTACT_REVIEW_FIELDS, filt.noisy_contacts)

    raw_keys = (
        "total_sent_email_rows",
        "unique_outbound_recipient_emails",
        "unique_outbound_recipient_domains",
        "total_universe_contacts",
        "total_universe_domains",
        "bounced_recipient_emails",
        "suppressed_contacts",
        "contacts_eligible_for_follow_up",
        "contacts_blocked_from_outreach",
    )
    clean_keys = (
        "exact_contacted_emails_for_exclusion",
        "contacted_domains_for_exclusion",
        "bounced_emails_for_exclusion",
        "suppressed_contacts_for_exclusion",
        "follow_up_candidates_review",
        "noisy_contacts_review",
    )

    def _section(title: str, keys: tuple[str, ...]) -> list[str]:
        block = [f"## {title}", "", "| Metric | Count |", "|--------|------:|"]
        for key in keys:
            val = result.summary.get(key)
            if isinstance(val, (int, float)):
                block.append(f"| {key} | {val:,} |")
        block.append("")
        return block

    lines = [
        "# Contacted universe summary",
        "",
        "Read-only audit from SQLite (Gmail Sent + suppressions + outreach state).",
        "",
    ]
    lines.extend(_section("Raw safety universe (full mail graph)", raw_keys))
    lines.extend(
        _section(
            "Clean exports for DeepSearch / prospecting",
            clean_keys,
        )
    )
    lines.extend(
        [
            f"- Gmail user: `{result.summary.get('gmail_user', '')}`",
            f"- Sent folders: `{', '.join(result.summary.get('sent_folders') or [])}`",
            "",
            "### Raw outputs (unchanged)",
            "- `contacted_universe_contacts.csv`",
            "- `contacted_universe_domains.csv`",
            "",
            "### Prospecting / exclusion outputs",
            "- `contacted_exact_emails_for_exclusion.csv` — Sent, outreach, bounce, suppression only",
            "- `contacted_domains_for_exclusion.csv` — domains touched or blocked",
            "- `bounced_emails_for_exclusion.csv`",
            "- `suppressed_contacts_for_exclusion.csv`",
            "- `follow_up_candidates_review.csv` — human follow-up shortlist",
            "- `noisy_contacts_review.csv` — why the raw universe is large",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "summary_json": json_path,
        "summary_md": md_path,
        "contacts_csv": contacts_path,
        "domains_csv": domains_path,
        "exact_emails_csv": exact_path,
        "domains_exclusion_csv": domain_excl_path,
        "bounced_emails_csv": bounced_path,
        "suppressed_contacts_csv": suppressed_path,
        "follow_up_candidates_csv": follow_up_path,
        "noisy_contacts_csv": noisy_path,
    }
