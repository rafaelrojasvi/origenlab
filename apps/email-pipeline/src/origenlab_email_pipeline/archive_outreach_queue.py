"""Read-only archive-based outreach candidate queue (historical contact revival).

Candidate source is the historical mart (`contact_master` + optional `organization_master` /
`opportunity_signals`) while exclusion policy reuses the same gate used by lead outreach.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from origenlab_email_pipeline.candidate_export_gate import (
    REASON_INVALID_EMAIL,
    evaluate_export_eligibility,
)
from origenlab_email_pipeline.marketing_export_context import (
    DEFAULT_SENT_FOLDERS,
    build_marketing_export_gate_context,
)

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
            )
        )
    out.sort(
        key=lambda r: (
            -r.warmth_score,
            -r.contact_total_emails,
            r.contact_last_seen_at,
            r.contact_email,
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
) -> ArchiveOutreachAuditResult:
    """Run existing gate on archive candidates; returns eligible + blocked rows with reason."""
    cands = fetch_archive_outreach_candidates(conn, fetch_cap=fetch_cap, limit=limit)
    gate_ctx = build_marketing_export_gate_context(
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
    "ARCHIVE_OUTREACH_COLUMN_NAMES",
    "ArchiveOutreachCandidate",
    "ArchiveOutreachAuditRow",
    "ArchiveOutreachAuditResult",
    "fetch_archive_outreach_candidates",
    "audit_archive_outreach_candidates",
]
