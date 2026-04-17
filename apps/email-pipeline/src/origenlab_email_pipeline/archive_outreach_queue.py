"""Read-only archive-based outreach candidate queue (historical contact revival).

Candidate source is the historical mart (`contact_master` + optional `organization_master` /
`opportunity_signals`) while exclusion policy reuses the same gate used by lead outreach.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any, Final, Literal, Mapping, cast

from origenlab_email_pipeline.archive_shortlist_commercial_precheck import COMMERCIAL_DROP_STATUSES
from origenlab_email_pipeline.business_mart import primary_sender_email
from origenlab_email_pipeline.candidate_export_gate import (
    REASON_INVALID_EMAIL,
    evaluate_export_eligibility,
)
from origenlab_email_pipeline.marketing_export_context import DEFAULT_SENT_FOLDERS
from origenlab_email_pipeline.outbound_core import gate_context_for_archive_batch
from origenlab_email_pipeline.tatiana_voice_cohort import (
    load_voice_sender_domains,
    sender_domain_matches_voice_domains,
)

ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO: Final[str] = "company_intro"
ARCHIVE_CANDIDATE_SORT_LEGACY: Final[str] = "legacy"
ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO_FRESH_LAST_SEEN: Final[str] = "company_intro_fresh_last_seen"
ArchiveCandidateSortMode = Literal[
    "company_intro",
    "legacy",
    "company_intro_fresh_last_seen",
]

ARCHIVE_OUTREACH_COLUMN_NAMES: tuple[str, ...] = (
    "case_id",
    "contact_email",
    "recipient_name",
    "institution_name",
    "domain",
    "contact_total_emails",
    "contact_last_seen_at",
    "contact_confidence_score",
    "contact_quote_email_count",
    "contact_invoice_email_count",
    "contact_purchase_email_count",
    "org_total_emails",
    "org_quote_email_count",
    "org_invoice_email_count",
    "org_purchase_email_count",
    "dormant_signal_count",
    "warmth_score",
    "warmth_band",
    "is_free_personal_domain",
    "is_generic_mailbox_localpart",
    "is_institutional_domain",
    "is_supplier_like",
    "is_marketplace_like",
    "is_admin_transactional_like",
    "quality_flags",
    "last_contacted_by_labdelivery",
    "labdelivery_last_contact_at",
    "labdelivery_signal_provenance",
)

LABDELIVERY_SIGNAL_PROVENANCE: Final[str] = (
    "emails: max(date_iso) where From domain matches voice_sender_domains "
    "(see tatiana_voice_cohort.load_voice_sender_domains) and comma-delimited "
    "recipients contain the contact email token."
)


@dataclass(frozen=True)
class ArchiveOutreachCandidate:
    case_id: str
    contact_email: str
    recipient_name: str
    institution_name: str
    domain: str
    contact_total_emails: int
    contact_last_seen_at: str
    contact_confidence_score: float
    contact_quote_email_count: int
    contact_invoice_email_count: int
    contact_purchase_email_count: int
    org_total_emails: int
    org_quote_email_count: int
    org_invoice_email_count: int
    org_purchase_email_count: int
    dormant_signal_count: int
    warmth_score: float
    warmth_band: str
    is_free_personal_domain: bool
    is_generic_mailbox_localpart: bool
    is_institutional_domain: bool
    is_supplier_like: bool
    is_marketplace_like: bool
    is_admin_transactional_like: bool
    quality_flags: str
    last_contacted_by_labdelivery: bool
    labdelivery_last_contact_at: str
    labdelivery_signal_provenance: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArchiveOutreachAuditRow:
    candidate: ArchiveOutreachCandidate
    eligible: bool
    reject_reason_code: str

    def to_dict(self) -> dict[str, Any]:
        d = self.candidate.to_dict()
        d["eligible"] = self.eligible
        d["reject_reason_code"] = self.reject_reason_code
        return d


@dataclass(frozen=True)
class ArchiveOutreachAuditResult:
    rows: list[ArchiveOutreachAuditRow]
    eligible_count: int
    blocked_count: int
    blocked_by_reason: dict[str, int]


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def _emails_table_has_lab_lookup_columns(conn: sqlite3.Connection) -> bool:
    """True when ``emails`` has columns needed for labdelivery recipient/sender scan."""
    if not _table_exists(conn, "emails"):
        return False
    cur = conn.execute("PRAGMA table_info(emails)")
    cols = {str(r[1]).lower() for r in cur.fetchall() if len(r) > 1}
    if "sender" not in cols or "recipients" not in cols:
        return False
    return "date_iso" in cols or "date_raw" in cols


def _int(v: object) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _float(v: object) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _warmth_score(row: dict[str, Any]) -> float:
    """Deterministic heuristic score (no ML, no hidden ranking state)."""
    c_total = _int(row.get("contact_total_emails"))
    o_total = _int(row.get("org_total_emails"))
    c_quote = _int(row.get("contact_quote_email_count"))
    c_invoice = _int(row.get("contact_invoice_email_count"))
    c_purchase = _int(row.get("contact_purchase_email_count"))
    o_quote = _int(row.get("org_quote_email_count"))
    o_invoice = _int(row.get("org_invoice_email_count"))
    o_purchase = _int(row.get("org_purchase_email_count"))
    conf = _float(row.get("contact_confidence_score"))
    dormant = _int(row.get("dormant_signal_count"))
    return (
        min(c_total, 80) * 0.45
        + min(o_total, 120) * 0.12
        + c_quote * 2.2
        + c_invoice * 1.6
        + c_purchase * 1.6
        + o_quote * 1.4
        + o_invoice * 1.1
        + o_purchase * 1.1
        + conf * 10.0
        + min(dormant, 10) * 0.9
    )


_FREE_PERSONAL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "icloud.com",
        "proton.me",
        "protonmail.com",
    }
)
_GENERIC_LOCALS: tuple[str, ...] = (
    "info",
    "contacto",
    "contact",
    "ventas",
    "sales",
    "admin",
    "soporte",
    "support",
    "compras",
    "adquisiciones",
    "facturacion",
    "billing",
    "noreply",
    "no-reply",
    "postmaster",
    "mailer-daemon",
)
_MARKETPLACE_DOMAINS: frozenset[str] = frozenset(
    {
        "mercadopublico.cl",
        "chilecompra.cl",
        "solostocks.com",
        "solostocks.cl",
        "wherex.com",
    }
)


def _domain_matches(domain: str, ref: frozenset[str]) -> bool:
    d = domain.strip().lower()
    if not d:
        return False
    if d in ref:
        return True
    return any(d.endswith("." + x) for x in ref)


def _institutional_domain(domain: str) -> bool:
    d = domain.strip().lower()
    if not d:
        return False
    return (
        ".edu" in d
        or ".gov" in d
        or ".gob." in d
        or d.endswith(".municipal.cl")
        or ".muni" in d
        or ".salud" in d
        or ".hospital" in d
        or ".pjud." in d
        or ".min" in d
    )


def _local_part(email: str) -> str:
    e = str(email or "").strip().lower()
    if "@" not in e:
        return ""
    return e.split("@", 1)[0].strip()


def _is_generic_local(local: str) -> bool:
    if not local:
        return False
    return any(local == x or local.startswith(x + ".") or local.startswith(x + "+") for x in _GENERIC_LOCALS)


def _is_admin_transactional(local: str) -> bool:
    return _is_generic_local(local) or any(
        token in local
        for token in ("noreply", "notificacion", "notification", "boletin", "newsletter", "alerts")
    )


def _warmth_band(score: float) -> str:
    if score >= 120:
        return "strong"
    if score < 45:
        return "weak"
    return "medium"


def commercial_contact_drop_penalties(conn: sqlite3.Connection, emails: set[str]) -> dict[str, bool]:
    """Map normalized contact email -> True when ``contact_candidate.status`` is a commercial drop tier."""
    if not emails or not _table_exists(conn, "contact_candidate"):
        return {}
    ph = ",".join("?" * len(emails))
    rows = conn.execute(
        f"""
        SELECT lower(trim(contact_email)) AS em, lower(trim(status)) AS st
        FROM contact_candidate
        WHERE lower(trim(contact_email)) IN ({ph})
        """,
        tuple(sorted(emails)),
    ).fetchall()
    out: dict[str, bool] = {}
    for em, st in rows:
        if st in COMMERCIAL_DROP_STATUSES:
            out[str(em)] = True
    return out


def _voice_sender_sql_or(domains: frozenset[str]) -> tuple[str, list[str]]:
    """SQL fragment matching From-style ``sender`` text against voice cohort domains."""
    parts: list[str] = []
    params: list[str] = []
    for d in sorted(domains):
        d0 = (d or "").strip().lower()
        if not d0 or " " in d0 or "@" in d0:
            continue
        parts.append(
            "("
            "LOWER(COALESCE(e.sender,'')) LIKE ? "
            "OR LOWER(COALESCE(e.sender,'')) LIKE ? "
            "OR LOWER(COALESCE(e.sender,'')) LIKE ?"
            ")"
        )
        params.append(f"%@{d0}")
        params.append(f"%.{d0}")
        # RFC822-style ``Name <user@domain>`` often ends with ``>`` after the domain.
        params.append(f"%@{d0}>")
    if not parts:
        return "1=0", []
    return "(" + " OR ".join(parts) + ")", params


def _sort_epoch_from_lab_date(iso: str) -> float:
    s = (iso or "").strip()
    if not s:
        return 0.0
    try:
        s2 = s.replace("Z", "+00:00")
        return float(datetime.fromisoformat(s2).timestamp())
    except (ValueError, OSError, OverflowError):
        pass
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return float(datetime.fromisoformat(s[:10] + "T00:00:00").timestamp())
        except (ValueError, OSError, OverflowError):
            return 0.0
    return 0.0


def _recipient_emails_from_recipients_field(recipients: str | None) -> set[str]:
    """Split To/Cc-style ``recipients`` and parse each token into a bare email."""
    out: set[str] = set()
    for part in re.split(r"[;,]", str(recipients or "")):
        p = part.strip()
        if not p:
            continue
        e = primary_sender_email(p)
        if e:
            out.add(e.strip().lower())
    return out


def labdelivery_contact_last_seen(
    conn: sqlite3.Connection,
    contact_emails: set[str],
    *,
    voice_domains: frozenset[str] | None = None,
) -> dict[str, str]:
    """Map normalized contact email -> latest ``date_iso`` (fallback ``date_raw``) for archive rows.

    Scans ``emails`` rows whose ``sender`` matches configured voice domains (defaults
    include ``labdelivery.cl``), parses ``recipients`` into addresses (handles
    ``Name <addr@dom>``), and keeps the max timestamp per matched needle. Ranking-only;
    not a gate.
    """
    needles = {str(e or "").strip().lower() for e in contact_emails if str(e or "").strip()}
    if not needles or not _emails_table_has_lab_lookup_columns(conn):
        return {}
    doms = voice_domains if voice_domains is not None else load_voice_sender_domains()
    if not doms:
        doms = frozenset({"labdelivery.cl"})
    sender_sql, sender_params = _voice_sender_sql_or(doms)
    if sender_sql == "1=0":
        return {}
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT e.sender,
               e.recipients,
               NULLIF(trim(COALESCE(e.date_iso,'')), '') AS d_iso,
               NULLIF(trim(COALESCE(e.date_raw,'')), '') AS d_raw
        FROM emails e
        WHERE {sender_sql}
        """,
        tuple(sender_params),
    )
    best: dict[str, str] = {}
    for sender_hdr, recips, d_iso, d_raw in cur.fetchall():
        if not sender_domain_matches_voice_domains(str(sender_hdr or ""), doms):
            continue
        ts = ((d_iso or "").strip() or (d_raw or "").strip())
        if not ts:
            continue
        for addr in _recipient_emails_from_recipients_field(recips):
            if addr not in needles:
                continue
            prev = best.get(addr, "")
            if not prev or _sort_epoch_from_lab_date(ts) >= _sort_epoch_from_lab_date(prev):
                best[addr] = ts
    return best


def archive_company_intro_sort_key_from_candidate(
    c: ArchiveOutreachCandidate,
    *,
    commercial_contact_is_drop: bool = False,
    prefer_newer_contact_last_seen: bool = False,
) -> tuple[Any, ...]:
    """Sort key: lower tuple orders earlier (higher business priority for company-intro outreach).

    Order: commercial-drop → free-personal → generic-local → supplier-like → marketplace-like
    → non-institutional → no labdelivery outbound history → older labdelivery touch
    → procurement → warmth → volume → contact recency → email (stable).

    When ``prefer_newer_contact_last_seen`` is true, ``contact_last_seen_at`` is ordered
    newest-first (stronger archive activity recency) before the stable email tie-break.
    """
    procurement = (
        c.contact_quote_email_count
        + c.contact_invoice_email_count
        + c.contact_purchase_email_count
        + (c.org_quote_email_count + c.org_invoice_email_count + c.org_purchase_email_count) // 2
    )
    org_doc_signal = c.org_quote_email_count + c.org_invoice_email_count + c.org_purchase_email_count
    lab_epoch = _sort_epoch_from_lab_date(c.labdelivery_last_contact_at)
    has_lab = bool(c.last_contacted_by_labdelivery)
    last_seen_key: Any
    if prefer_newer_contact_last_seen:
        last_seen_key = -_sort_epoch_from_lab_date(c.contact_last_seen_at)
    else:
        last_seen_key = c.contact_last_seen_at
    return (
        1 if commercial_contact_is_drop else 0,
        1 if c.is_free_personal_domain else 0,
        1 if c.is_generic_mailbox_localpart else 0,
        1 if c.is_supplier_like else 0,
        1 if c.is_marketplace_like else 0,
        0 if c.is_institutional_domain else 1,
        0 if org_doc_signal > 0 else 1,
        0 if has_lab else 1,
        -(lab_epoch if has_lab else 0.0),
        -procurement,
        -c.warmth_score,
        -c.contact_total_emails,
        last_seen_key,
        c.contact_email,
    )


def _truthy_mapping_cell(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in {"1", "true", "yes", "y"}


def _int_mapping_cell(v: Any) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def archive_company_intro_sort_key_from_row_dict(
    row: Mapping[str, Any],
    *,
    commercial_contact_is_drop: bool = False,
    prefer_newer_contact_last_seen: bool = False,
) -> tuple[Any, ...]:
    """Same ordering as ``archive_company_intro_sort_key_from_candidate`` for audit-row dicts."""
    free = _truthy_mapping_cell(row.get("is_free_personal_domain"))
    generic = _truthy_mapping_cell(row.get("is_generic_mailbox_localpart"))
    inst = _truthy_mapping_cell(row.get("is_institutional_domain"))
    supplier = _truthy_mapping_cell(row.get("is_supplier_like"))
    market = _truthy_mapping_cell(row.get("is_marketplace_like"))
    c_q = _int_mapping_cell(row.get("contact_quote_email_count"))
    c_i = _int_mapping_cell(row.get("contact_invoice_email_count"))
    c_p = _int_mapping_cell(row.get("contact_purchase_email_count"))
    o_q = _int_mapping_cell(row.get("org_quote_email_count"))
    o_i = _int_mapping_cell(row.get("org_invoice_email_count"))
    o_p = _int_mapping_cell(row.get("org_purchase_email_count"))
    procurement = c_q + c_i + c_p + (o_q + o_i + o_p) // 2
    org_doc_signal = o_q + o_i + o_p
    warmth = float(row.get("warmth_score") or 0.0)
    total = _int_mapping_cell(row.get("contact_total_emails"))
    last_seen = str(row.get("contact_last_seen_at") or "")
    email = str(row.get("contact_email") or "").strip().lower()
    lab_ts = str(row.get("labdelivery_last_contact_at") or "").strip()
    lab_epoch = _sort_epoch_from_lab_date(lab_ts)
    has_lab = _truthy_mapping_cell(row.get("last_contacted_by_labdelivery"))
    last_seen_key: Any = -_sort_epoch_from_lab_date(last_seen) if prefer_newer_contact_last_seen else last_seen
    return (
        1 if commercial_contact_is_drop else 0,
        1 if free else 0,
        1 if generic else 0,
        1 if supplier else 0,
        1 if market else 0,
        0 if inst else 1,
        0 if org_doc_signal > 0 else 1,
        0 if has_lab else 1,
        -(lab_epoch if has_lab else 0.0),
        -procurement,
        -warmth,
        -total,
        last_seen_key,
        email,
    )


def _legacy_archive_candidate_sort_key(c: ArchiveOutreachCandidate) -> tuple[Any, ...]:
    return (-c.warmth_score, -c.contact_total_emails, c.contact_last_seen_at, c.contact_email)


def _normalize_archive_candidate_sort(mode: str | None) -> ArchiveCandidateSortMode:
    m = (mode or ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO).strip().lower()
    allowed: tuple[str, ...] = (
        ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO,
        ARCHIVE_CANDIDATE_SORT_LEGACY,
        ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO_FRESH_LAST_SEEN,
    )
    if m not in allowed:
        raise ValueError(
            "archive_candidate_sort must be one of "
            f"{', '.join(repr(x) for x in allowed)}, "
            f"got {mode!r}"
        )
    return cast(ArchiveCandidateSortMode, m)


def _quality_flags(*, email: str, domain: str, supplier_like: bool, score: float) -> tuple[bool, bool, bool, bool, bool, bool, str, str]:
    local = _local_part(email)
    is_free = _domain_matches(domain, _FREE_PERSONAL_DOMAINS)
    is_generic = _is_generic_local(local)
    is_inst = _institutional_domain(domain)
    is_market = _domain_matches(domain, _MARKETPLACE_DOMAINS)
    is_admin_tx = _is_admin_transactional(local)
    band = _warmth_band(score)
    tags: list[str] = []
    if is_free:
        tags.append("free_personal_domain")
    if is_generic:
        tags.append("generic_mailbox_localpart")
    if is_inst:
        tags.append("institutional_domain")
    if supplier_like:
        tags.append("supplier_like")
    if is_market:
        tags.append("marketplace_like")
    if is_admin_tx:
        tags.append("admin_transactional_like")
    tags.append(f"warmth_{band}")
    return is_free, is_generic, is_inst, supplier_like, is_market, is_admin_tx, band, ",".join(tags)


def _archive_candidate_sql(*, include_org: bool, include_signals: bool, include_supplier: bool) -> str:
    org_join = ""
    sig_join = ""
    if include_org:
        org_join = """
        LEFT JOIN organization_master om
          ON lower(trim(om.domain)) = lower(trim(cm.domain))
        """
    if include_signals:
        sig_join = """
        LEFT JOIN (
          SELECT lower(trim(entity_key)) AS entity_key_norm, COUNT(*) AS dormant_signal_count
          FROM opportunity_signals
          WHERE signal_type = 'dormant_contact'
          GROUP BY lower(trim(entity_key))
        ) ds_email ON ds_email.entity_key_norm = lower(trim(cm.email))
        LEFT JOIN (
          SELECT lower(trim(entity_key)) AS entity_key_norm, COUNT(*) AS dormant_signal_count
          FROM opportunity_signals
          WHERE signal_type = 'dormant_contact'
          GROUP BY lower(trim(entity_key))
        ) ds_domain ON ds_domain.entity_key_norm = lower(trim(cm.domain))
        """
    supplier_join = ""
    supplier_col = "0 AS supplier_domain_match"
    if include_supplier:
        supplier_join = """
        LEFT JOIN (
          SELECT DISTINCT lower(trim(domain_norm)) AS supplier_domain_norm
          FROM supplier_master
          WHERE domain_norm IS NOT NULL AND trim(domain_norm) != ''
        ) sm ON sm.supplier_domain_norm = lower(trim(cm.domain))
        """
        supplier_col = "CASE WHEN sm.supplier_domain_norm IS NULL THEN 0 ELSE 1 END AS supplier_domain_match"
    return f"""
    SELECT
      lower(trim(cm.email)) AS contact_email,
      COALESCE(cm.contact_name_best, '') AS recipient_name,
      COALESCE(cm.organization_name_guess, '') AS institution_name,
      COALESCE(lower(trim(cm.domain)), '') AS domain,
      COALESCE(cm.total_emails, 0) AS contact_total_emails,
      COALESCE(cm.last_seen_at, '') AS contact_last_seen_at,
      COALESCE(cm.confidence_score, 0.0) AS contact_confidence_score,
      COALESCE(cm.quote_email_count, 0) AS contact_quote_email_count,
      COALESCE(cm.invoice_email_count, 0) AS contact_invoice_email_count,
      COALESCE(cm.purchase_email_count, 0) AS contact_purchase_email_count,
      COALESCE(om.total_emails, 0) AS org_total_emails,
      COALESCE(om.quote_email_count, 0) AS org_quote_email_count,
      COALESCE(om.invoice_email_count, 0) AS org_invoice_email_count,
      COALESCE(om.purchase_email_count, 0) AS org_purchase_email_count,
      COALESCE(ds_email.dormant_signal_count, 0) + COALESCE(ds_domain.dormant_signal_count, 0) AS dormant_signal_count,
      {supplier_col}
    FROM contact_master cm
    {org_join}
    {sig_join}
    {supplier_join}
    WHERE cm.email IS NOT NULL
      AND trim(cm.email) != ''
      AND instr(cm.email, '@') > 0
    ORDER BY COALESCE(cm.total_emails, 0) DESC, COALESCE(cm.last_seen_at, '') DESC
    LIMIT ?
    """.strip()


def fetch_archive_outreach_candidates(
    conn: sqlite3.Connection,
    *,
    fetch_cap: int = 20000,
    limit: int = 500,
    archive_candidate_sort: str = ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO,
) -> list[ArchiveOutreachCandidate]:
    """Read-only archive candidates (source pool only; no gate applied)."""
    if not _table_exists(conn, "contact_master"):
        return []
    include_org = _table_exists(conn, "organization_master")
    include_signals = _table_exists(conn, "opportunity_signals")
    include_supplier = _table_exists(conn, "supplier_master")
    cap = max(10, min(int(fetch_cap), 200000))
    prev_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        sql = _archive_candidate_sql(
            include_org=include_org,
            include_signals=include_signals,
            include_supplier=include_supplier,
        )
        cur = conn.execute(sql, (cap,))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.row_factory = prev_factory
    out: list[ArchiveOutreachCandidate] = []
    seen: set[str] = set()
    for i, d in enumerate(rows, start=1):
        email = str(d.get("contact_email") or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        score = _warmth_score(d)
        domain = str(d.get("domain") or "").strip().lower()
        supplier_like = _int(d.get("supplier_domain_match")) == 1
        is_free, is_generic, is_inst, is_supplier_like, is_market, is_admin_tx, warmth_band, quality_flags = _quality_flags(
            email=email,
            domain=domain,
            supplier_like=supplier_like,
            score=score,
        )
        out.append(
            ArchiveOutreachCandidate(
                case_id=f"arch_{i:05d}",
                contact_email=email,
                recipient_name=str(d.get("recipient_name") or "").strip(),
                institution_name=str(d.get("institution_name") or "").strip(),
                domain=domain,
                contact_total_emails=_int(d.get("contact_total_emails")),
                contact_last_seen_at=str(d.get("contact_last_seen_at") or "").strip(),
                contact_confidence_score=_float(d.get("contact_confidence_score")),
                contact_quote_email_count=_int(d.get("contact_quote_email_count")),
                contact_invoice_email_count=_int(d.get("contact_invoice_email_count")),
                contact_purchase_email_count=_int(d.get("contact_purchase_email_count")),
                org_total_emails=_int(d.get("org_total_emails")),
                org_quote_email_count=_int(d.get("org_quote_email_count")),
                org_invoice_email_count=_int(d.get("org_invoice_email_count")),
                org_purchase_email_count=_int(d.get("org_purchase_email_count")),
                dormant_signal_count=_int(d.get("dormant_signal_count")),
                warmth_score=score,
                warmth_band=warmth_band,
                is_free_personal_domain=is_free,
                is_generic_mailbox_localpart=is_generic,
                is_institutional_domain=is_inst,
                is_supplier_like=is_supplier_like,
                is_marketplace_like=is_market,
                is_admin_transactional_like=is_admin_tx,
                quality_flags=quality_flags,
                last_contacted_by_labdelivery=False,
                labdelivery_last_contact_at="",
                labdelivery_signal_provenance="",
            )
        )
    lab_touch = labdelivery_contact_last_seen(conn, {c.contact_email for c in out})
    enriched: list[ArchiveOutreachCandidate] = []
    for c in out:
        at = (lab_touch.get(c.contact_email) or "").strip()
        flagged = bool(at)
        prov = LABDELIVERY_SIGNAL_PROVENANCE if flagged else ""
        qf = c.quality_flags
        if flagged and "labdelivery_hist" not in qf:
            qf = f"{qf},labdelivery_hist" if qf else "labdelivery_hist"
        enriched.append(
            replace(
                c,
                last_contacted_by_labdelivery=flagged,
                labdelivery_last_contact_at=at,
                labdelivery_signal_provenance=prov,
                quality_flags=qf,
            )
        )
    out = enriched
    sort_mode = _normalize_archive_candidate_sort(archive_candidate_sort)
    if sort_mode == ARCHIVE_CANDIDATE_SORT_LEGACY:
        out.sort(key=_legacy_archive_candidate_sort_key)
    else:
        penalties = commercial_contact_drop_penalties(conn, {c.contact_email for c in out})
        prefer_fresh = sort_mode == ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO_FRESH_LAST_SEEN
        out.sort(
            key=lambda c: archive_company_intro_sort_key_from_candidate(
                c,
                commercial_contact_is_drop=bool(penalties.get(c.contact_email)),
                prefer_newer_contact_last_seen=prefer_fresh,
            )
        )
    return out[: max(1, min(int(limit), 50000))]


def audit_archive_outreach_candidates(
    conn: sqlite3.Connection,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...] = DEFAULT_SENT_FOLDERS,
    extra_exclude_domains: tuple[str, ...] = (),
    fetch_cap: int = 20000,
    limit: int = 500,
    strict_contact_graph_noise: bool = True,
    archive_candidate_sort: str = ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO,
) -> ArchiveOutreachAuditResult:
    """Run existing gate on archive candidates; returns eligible + blocked rows with reason."""
    cands = fetch_archive_outreach_candidates(
        conn,
        fetch_cap=fetch_cap,
        limit=limit,
        archive_candidate_sort=archive_candidate_sort,
    )
    gate_ctx = gate_context_for_archive_batch(
        conn,
        gmail_user=gmail_user,
        sent_folders=sent_folders,
        extra_exclude_domains=extra_exclude_domains,
        strict_contact_graph_noise=bool(strict_contact_graph_noise),
    )
    rows: list[ArchiveOutreachAuditRow] = []
    blocked_by_reason: dict[str, int] = {}
    eligible_count = 0
    for c in cands:
        gres = evaluate_export_eligibility(
            contact_email=c.contact_email,
            institution_name=c.institution_name or None,
            ctx=gate_ctx,
        )
        reason = gres.reasons[0] if gres.reasons else ""
        if gres.eligible:
            eligible_count += 1
        else:
            blocked_by_reason[reason] = blocked_by_reason.get(reason, 0) + 1
        rows.append(
            ArchiveOutreachAuditRow(
                candidate=c,
                eligible=bool(gres.eligible),
                reject_reason_code=reason if reason else ("" if gres.eligible else REASON_INVALID_EMAIL),
            )
        )
    return ArchiveOutreachAuditResult(
        rows=rows,
        eligible_count=eligible_count,
        blocked_count=len(rows) - eligible_count,
        blocked_by_reason=blocked_by_reason,
    )


__all__ = [
    "ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO",
    "ARCHIVE_CANDIDATE_SORT_COMPANY_INTRO_FRESH_LAST_SEEN",
    "ARCHIVE_CANDIDATE_SORT_LEGACY",
    "ARCHIVE_OUTREACH_COLUMN_NAMES",
    "LABDELIVERY_SIGNAL_PROVENANCE",
    "ArchiveCandidateSortMode",
    "ArchiveOutreachCandidate",
    "ArchiveOutreachAuditRow",
    "ArchiveOutreachAuditResult",
    "archive_company_intro_sort_key_from_candidate",
    "archive_company_intro_sort_key_from_row_dict",
    "commercial_contact_drop_penalties",
    "fetch_archive_outreach_candidates",
    "audit_archive_outreach_candidates",
    "labdelivery_contact_last_seen",
]
