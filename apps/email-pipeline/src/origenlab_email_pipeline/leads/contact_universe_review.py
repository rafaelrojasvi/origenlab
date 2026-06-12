"""Read-only contact universe review export for outreach planning."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Literal

from origenlab_email_pipeline.business_mart import domain_of, emails_in
from origenlab_email_pipeline.candidate_export_gate import (
    email_domain_under_operator_domain_suppression,
    normalize_export_email,
)
from origenlab_email_pipeline.leads.contacted_universe_audit import (
    ContactedUniverseContext,
    EmailActivity,
    build_contacted_universe_context,
    connect_readonly,
    load_do_not_repeat_emails_from_csv,
)
from origenlab_email_pipeline.marketing_supplier_domains import is_supplier_email_domain
from origenlab_email_pipeline.merge_marketing_contact_csvs import normalize_header_row
from origenlab_email_pipeline.org_normalize import is_junk_org_name, normalize_domain

SourceType = Literal[
    "active_current",
    "conversation_intelligence",
    "archive_research",
    "archive_campaign",
    "campaign_json",
    "sqlite_activity",
    "inventory",
]

BUCKET_FOLLOWUP = "followup_old_no_response"
BUCKET_NET_NEW = "net_new_review"
BUCKET_RECENT = "already_contacted_recently"
BUCKET_ACTIVE = "active_conversation_do_not_mass_send"
BUCKET_BLOCKED = "bounced_or_suppressed_do_not_send"
BUCKET_DOMAIN = "domain_blocked_do_not_send"
BUCKET_INVALID = "missing_or_invalid_email"
BUCKET_MANUAL = "manual_mapping_needed"
BUCKET_SUPPLIER = "supplier_or_vendor_do_not_market"

ALL_BUCKETS: frozenset[str] = frozenset(
    {
        BUCKET_FOLLOWUP,
        BUCKET_NET_NEW,
        BUCKET_RECENT,
        BUCKET_ACTIVE,
        BUCKET_BLOCKED,
        BUCKET_DOMAIN,
        BUCKET_INVALID,
        BUCKET_MANUAL,
        BUCKET_SUPPLIER,
    }
)

REDSALUD_DOMAINS: tuple[str, ...] = (
    "redsalud.gob.cl",
    "redsalud.gov.cl",
    "redsalud.cl",
)

ACTIVE_CURRENT_CSV_NAMES: tuple[str, ...] = (
    "contacted_universe_contacts.csv",
    "contacted_exact_emails_for_exclusion.csv",
    "bounced_emails_for_exclusion.csv",
    "suppressed_contacts_for_exclusion.csv",
    "follow_up_candidates_review.csv",
    "noisy_contacts_review.csv",
    "do_not_repeat_master.csv",
    "all_known_marketing_contacts_dedup.csv",
    "presentacion_origenlab_send_now_review.csv",
    "presentacion_do_not_send_reasons.csv",
    "presentacion_batch1_final_send_25.csv",
    "presentacion_batch2_followup_old_25.csv",
    "new_customer_targets_review.csv",
    "new_customer_targets_blocked.csv",
)

RECENT_CAMPAIGN_SOURCE_NAMES: frozenset[str] = frozenset(
    {
        "presentacion_batch1_final_send_25.csv",
        "presentacion_batch2_followup_old_25.csv",
        "presentacion_origenlab_send_now_review.csv",
    }
)

RECENT_SENT_DAYS = 30

_EMAIL_COLUMNS: tuple[str, ...] = (
    "normalized_email",
    "contact_email",
    "email",
    "email_norm",
    "buyer_email",
    "technical_email",
    "general_contact_email",
    "to",
    "from",
    "sender",
)

_ORG_COLUMNS: tuple[str, ...] = (
    "organization_name",
    "organization_guess",
    "institution_name",
    "organization",
    "company",
    "display_name",
)

CANDIDATE_FIELDS: tuple[str, ...] = (
    "email",
    "domain",
    "normalized_domain",
    "organization_guess",
    "source_files",
    "source_count",
    "source_types",
    "first_seen_source",
    "already_sent_count",
    "last_sent_at",
    "inbound_count",
    "last_inbound_at",
    "bounced",
    "suppressed_email",
    "suppressed_domain",
    "do_not_repeat",
    "has_recent_campaign_touch",
    "has_response",
    "has_active_or_warm_case",
    "recommended_bucket",
    "review_reason",
)

DOMAIN_ROLLUP_FIELDS: tuple[str, ...] = (
    "domain",
    "organization_guess",
    "total_emails",
    "sent_count",
    "inbound_count",
    "suppressed_count",
    "bounced_count",
    "net_new_count",
    "followup_count",
    "recommended_domain_bucket",
    "notes",
)

REDSALUD_EXAMPLE_FIELDS: tuple[str, ...] = (
    "email",
    "domain",
    "normalized_domain",
    "redsalud_family",
    "organization_guess",
    "source_files",
    "sqlite_sent_count",
    "sqlite_inbound_count",
    "suppressed_email",
    "suppressed_domain",
    "recommended_bucket",
    "repo_source_hits",
    "dashboard_visibility_note",
)

SOURCE_INVENTORY_FIELDS: tuple[str, ...] = (
    "path",
    "source_type",
    "exists",
    "emails_extracted",
    "notes",
)

_JSON_EMAIL_KEYS: frozenset[str] = frozenset(
    {
        "contact_email",
        "email",
        "email_norm",
        "buyer_email",
        "technical_email",
        "general_contact_email",
        "normalized_email",
    }
)

_EMAIL_IN_TEXT_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class SourceHit:
    path: str
    source_type: SourceType
    organization_guess: str = ""


@dataclass
class EmailAccumulator:
    email: str
    domain: str
    normalized_domain: str
    organization_guess: str = ""
    sources: list[SourceHit] = field(default_factory=list)

    @property
    def source_files(self) -> str:
        return ";".join(sorted({s.path for s in self.sources}))

    @property
    def source_types(self) -> str:
        return ";".join(sorted({s.source_type for s in self.sources}))

    @property
    def source_count(self) -> int:
        return len({s.path for s in self.sources})

    @property
    def first_seen_source(self) -> str:
        return self.sources[0].path if self.sources else ""


@dataclass(frozen=True)
class BucketInput:
    email: str | None
    sent_count: int = 0
    inbound_count: int = 0
    bounced: bool = False
    suppressed_email: bool = False
    suppressed_domain: bool = False
    do_not_repeat: bool = False
    has_recent_campaign_touch: bool = False
    has_response: bool = False
    has_active_or_warm_case: bool = False
    supplier_domain: bool = False
    invalid_email: bool = False
    needs_manual_mapping: bool = False


@dataclass
class ContactUniverseReviewResult:
    summary: dict[str, Any]
    candidates: list[dict[str, str]]
    domain_rollup: list[dict[str, str]]
    source_inventory: list[dict[str, str]]
    followup_candidates: list[dict[str, str]]
    net_new_candidates: list[dict[str, str]]
    blocked_or_suppressed: list[dict[str, str]]
    needs_manual_mapping: list[dict[str, str]]
    redsalud_examples: list[dict[str, str]]


def default_out_dir(active_current: Path) -> Path:
    return active_current / "contact_universe_review"


def is_redsalud_domain(domain: str | None) -> bool:
    d = (domain or "").strip().lower()
    if not d:
        return False
    if d in REDSALUD_DOMAINS:
        return True
    return d.endswith(".redsalud.gob.cl") or d.endswith(".redsalud.gov.cl") or d.endswith(".redsalud.cl")


def redsalud_family_label(domain: str | None) -> str:
    """Preserve distinct RedSalud TLD variants while grouping for audit."""
    d = (domain or "").strip().lower()
    if not d:
        return ""
    for canonical in REDSALUD_DOMAINS:
        if d == canonical or d.endswith("." + canonical):
            return canonical
    if "redsalud" in d:
        return d
    return ""


def normalize_review_domain(domain_or_email: str) -> str:
    """Normalize domain without dropping RedSalud TLD variants."""
    raw = (domain_or_email or "").strip().lower()
    if not raw:
        return ""
    if "@" in raw:
        raw = raw.rsplit("@", 1)[-1]
    nd = normalize_domain(raw)
    return nd or raw.split("/")[0].split(":")[0]


def extract_emails_from_csv_row(row: dict[str, str]) -> list[str]:
    norm = normalize_header_row({str(k): str(v or "") for k, v in row.items()})
    found: list[str] = []
    seen: set[str] = set()
    for col in _EMAIL_COLUMNS:
        raw = norm.get(col, "")
        if not raw:
            continue
        for em in emails_in(raw):
            if em not in seen:
                seen.add(em)
                found.append(em)
    return found


def extract_organization_from_row(row: dict[str, str]) -> str:
    norm = normalize_header_row({str(k): str(v or "") for k, v in row.items()})
    for col in _ORG_COLUMNS:
        val = (norm.get(col) or "").strip()
        if val and not is_junk_org_name(val):
            return val
    return ""


def extract_emails_from_json_value(value: Any, *, _depth: int = 0) -> list[str]:
    if _depth > 12:
        return []
    if value is None:
        return []
    if isinstance(value, str):
        out: list[str] = []
        seen: set[str] = set()
        for em in emails_in(value):
            if em not in seen:
                seen.add(em)
                out.append(em)
        if not out:
            for match in _EMAIL_IN_TEXT_RE.findall(value):
                parsed = emails_in(match)
                for em in parsed:
                    if em not in seen:
                        seen.add(em)
                        out.append(em)
        return out
    if isinstance(value, dict):
        out: list[str] = []
        seen: set[str] = set()
        for key, item in value.items():
            key_l = str(key).lower()
            if key_l in _JSON_EMAIL_KEYS:
                for em in extract_emails_from_json_value(item, _depth=_depth + 1):
                    if em not in seen:
                        seen.add(em)
                        out.append(em)
            else:
                for em in extract_emails_from_json_value(item, _depth=_depth + 1):
                    if em not in seen:
                        seen.add(em)
                        out.append(em)
        return out
    if isinstance(value, list):
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            for em in extract_emails_from_json_value(item, _depth=_depth + 1):
                if em not in seen:
                    seen.add(em)
                    out.append(em)
        return out
    return []


def classify_recommended_bucket(inp: BucketInput) -> tuple[str, str]:
    """Return (recommended_bucket, review_reason)."""
    if inp.invalid_email or not inp.email:
        return BUCKET_INVALID, "invalid_or_missing_email"
    if inp.needs_manual_mapping:
        return BUCKET_MANUAL, "organization_or_institution_mapping_needed"
    if inp.supplier_domain:
        return BUCKET_SUPPLIER, "supplier_or_vendor_domain"
    if inp.suppressed_domain:
        return BUCKET_DOMAIN, "domain_suppression_active"
    if inp.bounced:
        return BUCKET_BLOCKED, "bounce_suppression"
    if inp.suppressed_email:
        return BUCKET_BLOCKED, "email_suppression_active"
    if inp.has_response or inp.has_active_or_warm_case:
        return BUCKET_ACTIVE, "active_thread_or_warm_case"
    if inp.sent_count > 0 and inp.has_recent_campaign_touch:
        return BUCKET_RECENT, "recent_campaign_touch"
    if inp.sent_count > 0 and inp.inbound_count == 0:
        return BUCKET_FOLLOWUP, "prior_outreach_no_inbound_reply"
    if inp.sent_count == 0:
        if inp.do_not_repeat:
            return BUCKET_BLOCKED, "do_not_repeat_master"
        return BUCKET_NET_NEW, "never_contacted_not_blocked"
    return BUCKET_FOLLOWUP, "sent_history_review"


def _parse_iso_date(value: str) -> datetime | None:
    s = (value or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _is_recent_date(value: str, *, now: datetime, days: int = RECENT_SENT_DAYS) -> bool:
    dt = _parse_iso_date(value)
    if not dt:
        return False
    return dt >= now - timedelta(days=days)


def _accumulate_email(
    store: dict[str, EmailAccumulator],
    email: str,
    *,
    hit: SourceHit,
    organization_guess: str = "",
) -> None:
    em = normalize_export_email(email)
    if not em:
        return
    dom = domain_of(em) or ""
    nd = normalize_review_domain(dom)
    acc = store.get(em)
    if acc is None:
        acc = EmailAccumulator(email=em, domain=dom, normalized_domain=nd)
        store[em] = acc
    acc.sources.append(hit)
    if organization_guess and not acc.organization_guess:
        acc.organization_guess = organization_guess
    elif organization_guess and is_junk_org_name(acc.organization_guess):
        acc.organization_guess = organization_guess


def _scan_csv_file(
    path: Path,
    *,
    source_type: SourceType,
    store: dict[str, EmailAccumulator],
) -> int:
    if not path.is_file():
        return 0
    count = 0
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return 0
        for row in reader:
            org = extract_organization_from_row(row)
            for em in extract_emails_from_csv_row(row):
                _accumulate_email(
                    store,
                    em,
                    hit=SourceHit(path=path.name, source_type=source_type, organization_guess=org),
                    organization_guess=org,
                )
                count += 1
    return count


def _scan_json_file(
    path: Path,
    *,
    source_type: SourceType,
    store: dict[str, EmailAccumulator],
) -> int:
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    emails = extract_emails_from_json_value(payload)
    for em in emails:
        _accumulate_email(
            store,
            em,
            hit=SourceHit(path=str(path.relative_to(path.parents[3]) if len(path.parents) > 3 else path.name), source_type=source_type),
        )
    return len(emails)


def discover_source_paths(
    repo_root: Path,
    *,
    active_current: Path,
    limit_sources: int | None = None,
) -> list[tuple[Path, SourceType]]:
    paths: list[tuple[Path, SourceType]] = []

    inventory_path = active_current / "contact_csv_inventory.json"
    if inventory_path.is_file():
        try:
            inv = json.loads(inventory_path.read_text(encoding="utf-8"))
            for item in inv if isinstance(inv, list) else inv.get("files", []):
                if isinstance(item, str):
                    p = Path(item)
                    if not p.is_absolute():
                        p = repo_root / p
                    paths.append((p, "inventory"))
                elif isinstance(item, dict):
                    raw = item.get("path") or item.get("file") or ""
                    if raw:
                        p = Path(raw)
                        if not p.is_absolute():
                            p = repo_root / p
                        paths.append((p, "inventory"))
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    for name in ACTIVE_CURRENT_CSV_NAMES:
        paths.append((active_current / name, "active_current"))

    conv_dir = active_current / "email_conversation_intelligence"
    if conv_dir.is_dir():
        for p in sorted(conv_dir.glob("*.csv")):
            paths.append((p, "conversation_intelligence"))

    archive_research = repo_root / "reports" / "out" / "archive" / "research"
    if archive_research.is_dir():
        for p in sorted(archive_research.rglob("*.csv")):
            paths.append((p, "archive_research"))

    archive_campaigns = repo_root / "reports" / "out" / "archive" / "campaigns"
    if archive_campaigns.is_dir():
        for p in sorted(archive_campaigns.rglob("*.csv")):
            paths.append((p, "archive_campaign"))

    campaign_json_dir = repo_root / "scripts" / "leads" / "campaigns" / "data"
    if campaign_json_dir.is_dir():
        for p in sorted(campaign_json_dir.glob("*.json")):
            paths.append((p, "campaign_json"))

    seen: set[str] = set()
    deduped: list[tuple[Path, SourceType]] = []
    for p, st in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((p, st))

    if limit_sources is not None and limit_sources >= 0:
        deduped = deduped[:limit_sources]
    return deduped


def collect_candidates_from_sources(
    source_paths: Iterable[tuple[Path, SourceType]],
) -> tuple[dict[str, EmailAccumulator], list[dict[str, str]]]:
    store: dict[str, EmailAccumulator] = {}
    inventory: list[dict[str, str]] = []

    for path, source_type in source_paths:
        rel = path.name
        exists = path.is_file()
        extracted = 0
        notes = ""
        if exists:
            if path.suffix.lower() == ".json":
                extracted = _scan_json_file(path, source_type=source_type, store=store)
            elif path.suffix.lower() == ".csv":
                extracted = _scan_csv_file(path, source_type=source_type, store=store)
            else:
                notes = "skipped_unsupported_extension"
        else:
            notes = "missing"
        inventory.append(
            {
                "path": rel,
                "source_type": source_type,
                "exists": str(exists).lower(),
                "emails_extracted": str(extracted),
                "notes": notes,
            }
        )
    return store, inventory


def _load_domain_suppression(conn: sqlite3.Connection) -> frozenset[str]:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='contact_domain_suppression' LIMIT 1"
    ).fetchone()
    if not row:
        return frozenset()
    rows = conn.execute(
        "SELECT lower(trim(domain_norm)) FROM contact_domain_suppression WHERE length(trim(domain_norm)) > 0"
    ).fetchall()
    return frozenset(str(r[0]) for r in rows if r[0])


def _needs_manual_mapping(acc: EmailAccumulator, ctx: ContactedUniverseContext) -> bool:
    org = (acc.organization_guess or "").strip()
    if org and not is_junk_org_name(org):
        return False
    dom = acc.normalized_domain or acc.domain
    if not dom:
        return True
    if dom in ctx.domains_with_sent_contact:
        return False
    if any(st in ("archive_research", "campaign_json") for st in acc.source_types.split(";")):
        return True
    return False


def _has_recent_campaign_touch(acc: EmailAccumulator, activity: EmailActivity, *, now: datetime) -> bool:
    source_names = {s.path for s in acc.sources}
    if source_names & RECENT_CAMPAIGN_SOURCE_NAMES:
        return True
    if _is_recent_date(activity.last_contacted_at, now=now) and activity.sent_count > 0:
        return True
    return False


def enrich_candidates(
    store: dict[str, EmailAccumulator],
    *,
    ctx: ContactedUniverseContext,
    activity: dict[str, EmailActivity],
    domain_suppressed: frozenset[str],
    focus_domains: frozenset[str] | None = None,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    now = now or datetime.now(UTC)
    rows: list[dict[str, str]] = []

    for em, acc in sorted(store.items()):
        if focus_domains:
            dom_l = (acc.domain or "").lower()
            nd_l = (acc.normalized_domain or "").lower()
            matches = dom_l in focus_domains or nd_l in focus_domains
            if not matches and is_redsalud_domain(dom_l):
                matches = any(is_redsalud_domain(fd) for fd in focus_domains)
            if not matches:
                continue

        act = activity.get(em, EmailActivity())
        dom = acc.domain or domain_of(em) or ""
        bounced = em in ctx.bounced_emails
        suppressed_email = em in ctx.gate.suppressed_norms
        suppressed_domain = email_domain_under_operator_domain_suppression(dom, domain_suppressed)
        supplier = is_supplier_email_domain(em, ctx.supplier_domains)
        outreach = ctx.all_outreach_state.get(em, "")
        has_response = act.received_count > 0 or outreach == "replied"
        warm = em in ctx.warm_opportunity_contacts
        dnr = em in ctx.do_not_repeat_emails
        recent_touch = _has_recent_campaign_touch(acc, act, now=now)
        manual = _needs_manual_mapping(acc, ctx)

        bucket_inp = BucketInput(
            email=em,
            sent_count=act.sent_count,
            inbound_count=act.received_count,
            bounced=bounced,
            suppressed_email=suppressed_email,
            suppressed_domain=suppressed_domain,
            do_not_repeat=dnr,
            has_recent_campaign_touch=recent_touch,
            has_response=has_response,
            has_active_or_warm_case=warm or outreach in ("replied", "contacted"),
            supplier_domain=supplier,
            invalid_email=False,
            needs_manual_mapping=manual,
        )
        bucket, reason = classify_recommended_bucket(bucket_inp)

        rows.append(
            {
                "email": em,
                "domain": dom,
                "normalized_domain": acc.normalized_domain or normalize_review_domain(dom),
                "organization_guess": acc.organization_guess,
                "source_files": acc.source_files,
                "source_count": str(acc.source_count),
                "source_types": acc.source_types,
                "first_seen_source": acc.first_seen_source,
                "already_sent_count": str(act.sent_count),
                "last_sent_at": act.last_contacted_at if act.sent_count > 0 else "",
                "inbound_count": str(act.received_count),
                "last_inbound_at": act.last_contacted_at if act.received_count > 0 else "",
                "bounced": str(bounced).lower(),
                "suppressed_email": str(suppressed_email).lower(),
                "suppressed_domain": str(suppressed_domain).lower(),
                "do_not_repeat": str(dnr).lower(),
                "has_recent_campaign_touch": str(recent_touch).lower(),
                "has_response": str(has_response).lower(),
                "has_active_or_warm_case": str(warm or outreach in ("replied", "contacted")).lower(),
                "recommended_bucket": bucket,
                "review_reason": reason,
            }
        )
    return rows


def build_domain_rollup(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    by_domain: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in candidates:
        dom = row.get("normalized_domain") or row.get("domain") or ""
        if dom:
            by_domain[dom].append(row)

    rollup: list[dict[str, str]] = []
    for dom in sorted(by_domain):
        rows = by_domain[dom]
        org = next((r.get("organization_guess", "") for r in rows if r.get("organization_guess")), "")
        sent_total = sum(int(r.get("already_sent_count") or 0) for r in rows)
        inbound_total = sum(int(r.get("inbound_count") or 0) for r in rows)
        suppressed = sum(1 for r in rows if r.get("suppressed_email") == "true")
        bounced = sum(1 for r in rows if r.get("bounced") == "true")
        net_new = sum(1 for r in rows if r.get("recommended_bucket") == BUCKET_NET_NEW)
        followup = sum(1 for r in rows if r.get("recommended_bucket") == BUCKET_FOLLOWUP)
        buckets = [r.get("recommended_bucket", "") for r in rows]
        if any(b == BUCKET_DOMAIN for b in buckets):
            domain_bucket = BUCKET_DOMAIN
            notes = "domain_suppression_present"
        elif any(b == BUCKET_BLOCKED for b in buckets) and all(
            b in (BUCKET_BLOCKED, BUCKET_SUPPLIER) for b in buckets
        ):
            domain_bucket = BUCKET_BLOCKED
            notes = "all_contacts_blocked"
        elif any(b == BUCKET_ACTIVE for b in buckets):
            domain_bucket = BUCKET_ACTIVE
            notes = "active_conversation_on_domain"
        elif followup > 0 and net_new > 0:
            domain_bucket = "mixed_review"
            notes = "both_followup_and_net_new"
        elif followup > 0:
            domain_bucket = BUCKET_FOLLOWUP
            notes = "followup_candidates_on_domain"
        elif net_new > 0:
            domain_bucket = BUCKET_NET_NEW
            notes = "net_new_candidates_on_domain"
        else:
            domain_bucket = buckets[0] if buckets else "unknown"
            notes = "review_domain"
        rollup.append(
            {
                "domain": dom,
                "organization_guess": org,
                "total_emails": str(len(rows)),
                "sent_count": str(sent_total),
                "inbound_count": str(inbound_total),
                "suppressed_count": str(suppressed),
                "bounced_count": str(bounced),
                "net_new_count": str(net_new),
                "followup_count": str(followup),
                "recommended_domain_bucket": domain_bucket,
                "notes": notes,
            }
        )
    return rollup


def build_redsalud_examples(
    candidates: list[dict[str, str]],
    *,
    store: dict[str, EmailAccumulator],
    activity: dict[str, EmailActivity],
    ctx: ContactedUniverseContext,
    domain_suppressed: frozenset[str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    dashboard_note = (
        "RedSalud uses multiple TLD variants (gob.cl, gov.cl, .cl). "
        "Dashboard Clientes/instituciones groups by normalized org name and primary domain; "
        "contacts on secondary RedSalud domains may not rollup unless institution mapping exists."
    )
    for row in candidates:
        dom = row.get("domain", "")
        nd = row.get("normalized_domain", "")
        if not (is_redsalud_domain(dom) or is_redsalud_domain(nd)):
            continue
        em = row.get("email", "")
        acc = store.get(em)
        act = activity.get(em, EmailActivity())
        dom_l = dom or nd
        suppressed_domain = email_domain_under_operator_domain_suppression(dom_l, domain_suppressed)
        repo_hits = acc.source_files if acc else row.get("source_files", "")
        rows.append(
            {
                "email": em,
                "domain": dom,
                "normalized_domain": nd,
                "redsalud_family": redsalud_family_label(dom or nd),
                "organization_guess": row.get("organization_guess", ""),
                "source_files": row.get("source_files", ""),
                "sqlite_sent_count": str(act.sent_count),
                "sqlite_inbound_count": str(act.received_count),
                "suppressed_email": row.get("suppressed_email", "false"),
                "suppressed_domain": str(suppressed_domain).lower(),
                "recommended_bucket": row.get("recommended_bucket", ""),
                "repo_source_hits": repo_hits,
                "dashboard_visibility_note": dashboard_note,
            }
        )

    for canonical in REDSALUD_DOMAINS:
        if not any(r.get("domain") == canonical or r.get("normalized_domain") == canonical for r in rows):
            rows.append(
                {
                    "email": "",
                    "domain": canonical,
                    "normalized_domain": normalize_review_domain(canonical),
                    "redsalud_family": canonical,
                    "organization_guess": "",
                    "source_files": "",
                    "sqlite_sent_count": "0",
                    "sqlite_inbound_count": "0",
                    "suppressed_email": "false",
                    "suppressed_domain": str(
                        email_domain_under_operator_domain_suppression(canonical, domain_suppressed)
                    ).lower(),
                    "recommended_bucket": BUCKET_NET_NEW,
                    "repo_source_hits": "",
                    "dashboard_visibility_note": (
                        f"No candidate email extracted for {canonical} in this review run. "
                        + dashboard_note
                    ),
                }
            )
    return sorted(rows, key=lambda r: (r.get("redsalud_family", ""), r.get("email", ""), r.get("domain", "")))


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Contact universe review",
        "",
        f"Generated: {summary.get('generated_at_utc', '')}",
        "",
        "## Counts",
        "",
        f"- Total candidate emails: **{summary.get('total_candidates', 0)}**",
        f"- Follow-up candidates: **{summary.get('followup_candidates', 0)}**",
        f"- Net-new review: **{summary.get('net_new_candidates', 0)}**",
        f"- Blocked/suppressed: **{summary.get('blocked_or_suppressed', 0)}**",
        f"- Manual mapping needed: **{summary.get('needs_manual_mapping', 0)}**",
        f"- RedSalud examples: **{summary.get('redsalud_examples', 0)}**",
        "",
        "## Bucket breakdown",
        "",
    ]
    for bucket, count in sorted((summary.get("bucket_counts") or {}).items()):
        lines.append(f"- `{bucket}`: {count}")
    lines.extend(
        [
            "",
            "## Source files scanned",
            "",
            f"- Sources in inventory: **{summary.get('sources_scanned', 0)}**",
            f"- Sources present on disk: **{summary.get('sources_present', 0)}**",
            "",
            "Read-only export — no Gmail, SQLite, or Postgres mutations.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_contact_universe_review_outputs(
    result: ContactUniverseReviewResult,
    out_dir: Path,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_md": out_dir / "CONTACT_UNIVERSE_REVIEW_SUMMARY.md",
        "source_inventory": out_dir / "source_file_inventory.csv",
        "all_candidates": out_dir / "all_candidate_emails.csv",
        "domain_rollup": out_dir / "domain_rollup.csv",
        "followup": out_dir / "followup_candidates.csv",
        "net_new": out_dir / "net_new_candidates.csv",
        "blocked": out_dir / "blocked_or_suppressed.csv",
        "manual_mapping": out_dir / "needs_manual_mapping.csv",
        "redsalud": out_dir / "examples_redsalud.csv",
    }
    _write_summary_md(paths["summary_md"], result.summary)
    _write_csv(paths["source_inventory"], SOURCE_INVENTORY_FIELDS, result.source_inventory)
    _write_csv(paths["all_candidates"], CANDIDATE_FIELDS, result.candidates)
    _write_csv(paths["domain_rollup"], DOMAIN_ROLLUP_FIELDS, result.domain_rollup)
    _write_csv(paths["followup"], CANDIDATE_FIELDS, result.followup_candidates)
    _write_csv(paths["net_new"], CANDIDATE_FIELDS, result.net_new_candidates)
    _write_csv(paths["blocked"], CANDIDATE_FIELDS, result.blocked_or_suppressed)
    _write_csv(paths["manual_mapping"], CANDIDATE_FIELDS, result.needs_manual_mapping)
    _write_csv(paths["redsalud"], REDSALUD_EXAMPLE_FIELDS, result.redsalud_examples)
    return paths


def build_contact_universe_review(
    *,
    repo_root: Path,
    sqlite_path: Path,
    active_current: Path,
    gmail_user: str,
    sent_folders: tuple[str, ...],
    focus_domains: frozenset[str] | None = None,
    limit_sources: int | None = None,
    do_not_repeat_csv: Path | None = None,
    now: datetime | None = None,
) -> ContactUniverseReviewResult:
    """Build read-only contact universe review artifacts."""
    now = now or datetime.now(UTC)
    source_paths = discover_source_paths(
        repo_root, active_current=active_current, limit_sources=limit_sources
    )
    store, source_inventory = collect_candidates_from_sources(source_paths)

    conn = connect_readonly(sqlite_path)
    try:
        ctx, activity, _sent_rows = build_contacted_universe_context(
            conn,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
            do_not_repeat_csv=do_not_repeat_csv,
        )
        domain_suppressed = _load_domain_suppression(conn)
        for em in activity:
            if em not in store:
                store[em] = EmailAccumulator(
                    email=em,
                    domain=domain_of(em) or "",
                    normalized_domain=normalize_review_domain(domain_of(em) or ""),
                    sources=[
                        SourceHit(path="sqlite:emails", source_type="sqlite_activity"),
                    ],
                )
    finally:
        conn.close()

    candidates = enrich_candidates(
        store,
        ctx=ctx,
        activity=activity,
        domain_suppressed=domain_suppressed,
        focus_domains=focus_domains,
        now=now,
    )
    domain_rollup = build_domain_rollup(candidates)
    followup = [r for r in candidates if r["recommended_bucket"] == BUCKET_FOLLOWUP]
    net_new = [r for r in candidates if r["recommended_bucket"] == BUCKET_NET_NEW]
    blocked = [r for r in candidates if r["recommended_bucket"] in (BUCKET_BLOCKED, BUCKET_DOMAIN)]
    manual = [r for r in candidates if r["recommended_bucket"] == BUCKET_MANUAL]
    redsalud = build_redsalud_examples(
        candidates,
        store=store,
        activity=activity,
        ctx=ctx,
        domain_suppressed=domain_suppressed,
    )

    bucket_counts: dict[str, int] = defaultdict(int)
    for row in candidates:
        bucket_counts[row["recommended_bucket"]] += 1

    sources_present = sum(1 for s in source_inventory if s.get("exists") == "true")

    summary = {
        "generated_at_utc": now.astimezone(UTC).replace(microsecond=0).isoformat(),
        "total_candidates": len(candidates),
        "followup_candidates": len(followup),
        "net_new_candidates": len(net_new),
        "blocked_or_suppressed": len(blocked),
        "needs_manual_mapping": len(manual),
        "redsalud_examples": len(redsalud),
        "bucket_counts": dict(bucket_counts),
        "sources_scanned": len(source_inventory),
        "sources_present": sources_present,
        "focus_domains": sorted(focus_domains) if focus_domains else [],
    }

    return ContactUniverseReviewResult(
        summary=summary,
        candidates=candidates,
        domain_rollup=domain_rollup,
        source_inventory=source_inventory,
        followup_candidates=followup,
        net_new_candidates=net_new,
        blocked_or_suppressed=blocked,
        needs_manual_mapping=manual,
        redsalud_examples=redsalud,
    )
