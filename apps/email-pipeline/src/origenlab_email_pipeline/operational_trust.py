"""Shared operational trust checks for QA scripts and tests."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from origenlab_email_pipeline.leads_schema import ensure_leads_tables

ALLOWED_FIT_BUCKETS = frozenset({"high_fit", "medium_fit", "low_fit", ""})
ALLOWED_BUYER_KINDS = frozenset(
    {
        "hospital",
        "universidad",
        "publico",
        "municipal",
        "gobierno",
        "agricola",
        "",
    }
)

AUDIT_DB_LINE_RE = re.compile(
    r"\*\*Base de datos usada:\*\*\s*`([^`]+)`",
    re.MULTILINE,
)


@dataclass(frozen=True)
class TrustCheck:
    check_id: str
    ok: bool
    critical: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "ok": self.ok,
            "critical": self.critical,
            "message": self.message,
            "details": self.details,
        }


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def id_leads_from_rows(rows: list[dict[str, str]], col: str = "id_lead") -> list[int]:
    out: list[int] = []
    for r in rows:
        raw = (r.get(col) or "").strip()
        if not raw:
            continue
        try:
            out.append(int(raw))
        except ValueError:
            continue
    return out


def duplicate_ids(ids: list[int]) -> list[int]:
    seen: set[int] = set()
    dups: set[int] = set()
    for i in ids:
        if i in seen:
            dups.add(i)
        seen.add(i)
    return sorted(dups)


def parse_iso_utc(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def load_client_pack_summary(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# Same expression as build_leads_client_pack: empty/whitespace fit_bucket counts as low_fit.
_FIT_BUCKET_GROUP_SQL = "COALESCE(NULLIF(TRIM(fit_bucket), ''), 'low_fit')"


def normalized_fit_bucket_counts(raw: dict[str, Any]) -> dict[str, int]:
    """Merge summary/DB fit_bucket maps for comparison (case-fold, trim, '' → low_fit)."""
    out: dict[str, int] = {}
    for k, v in raw.items():
        label = str(k).strip().lower() if k is not None else ""
        if not label:
            label = "low_fit"
        try:
            n = int(v)
        except (TypeError, ValueError):
            n = int(float(v))
        out[label] = out.get(label, 0) + n
    return out


def db_lead_totals(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_leads_tables(conn)
    total = conn.execute("SELECT COUNT(*) FROM lead_master").fetchone()[0]
    fit_rows = conn.execute(
        f"""
        SELECT {_FIT_BUCKET_GROUP_SQL} AS fb, COUNT(*)
        FROM lead_master GROUP BY fb
        """
    ).fetchall()
    fit_counts = {str(r[0]): int(r[1]) for r in fit_rows}
    return {"lead_master_rows": int(total), "fit_bucket": fit_counts}


def check_cohort_partition(
    hunt_path: Path,
    ready_path: Path,
    needs_path: Path,
    not_ready_path: Path,
) -> list[TrustCheck]:
    checks: list[TrustCheck] = []
    hunt_rows = read_csv_rows(hunt_path)
    hunt_ids_list = id_leads_from_rows(hunt_rows)
    hunt_set = set(hunt_ids_list)
    ready = set(id_leads_from_rows(read_csv_rows(ready_path)))
    needs = set(id_leads_from_rows(read_csv_rows(needs_path)))
    not_ready = set(id_leads_from_rows(read_csv_rows(not_ready_path)))

    dups = duplicate_ids(hunt_ids_list)
    checks.append(
        TrustCheck(
            "hunt_duplicate_id_lead",
            ok=len(dups) == 0,
            critical=True,
            message="No duplicate id_lead in hunt cohort"
            if not dups
            else f"Duplicate id_lead in hunt: {dups[:30]}{'…' if len(dups) > 30 else ''}",
            details={"duplicates": dups},
        )
    )

    union = ready | needs | not_ready
    inter_rn = ready & needs
    inter_rnr = ready & not_ready
    inter_nn = needs & not_ready
    overlap = sorted(inter_rn | inter_rnr | inter_nn)

    sum_counts = len(ready) + len(needs) + len(not_ready)
    checks.append(
        TrustCheck(
            "readiness_partition_disjoint",
            ok=len(overlap) == 0,
            critical=True,
            message="Ready/needs/not_ready ID sets are pairwise disjoint"
            if not overlap
            else f"Overlapping ids across readiness buckets: {overlap[:40]}",
            details={"overlap": overlap},
        )
    )

    checks.append(
        TrustCheck(
            "cohort_sum_invariant",
            ok=sum_counts == len(hunt_set) and union == hunt_set,
            critical=True,
            message=(
                f"ready({len(ready)})+needs({len(needs)})+not_ready({len(not_ready)}) "
                f"equals hunt unique ids ({len(hunt_set)}) and covers same set"
            ),
            details={
                "ready_n": len(ready),
                "needs_n": len(needs),
                "not_ready_n": len(not_ready),
                "hunt_unique_n": len(hunt_set),
                "only_in_hunt": sorted(hunt_set - union)[:50],
                "only_in_readiness": sorted(union - hunt_set)[:50],
            },
        )
    )

    checks.append(
        TrustCheck(
            "hunt_row_count_vs_unique",
            ok=len(hunt_rows) == len(hunt_set),
            critical=False,
            message=(
                "Hunt row count matches unique id_lead count"
                if len(hunt_rows) == len(hunt_set)
                else f"Hunt has {len(hunt_rows)} rows but {len(hunt_set)} unique id_lead"
            ),
            details={"rows": len(hunt_rows), "unique": len(hunt_set)},
        )
    )
    return checks


def check_readiness_critical_fields(
    ready_path: Path,
    needs_path: Path,
    not_ready_path: Path,
) -> list[TrustCheck]:
    issues: list[str] = []
    for label, path, cols in (
        ("ready", ready_path, ["id_lead", "org_name"]),
        ("needs", needs_path, ["id_lead", "org_name"]),
        ("not_ready", not_ready_path, ["id_lead", "org_name"]),
    ):
        rows = read_csv_rows(path)
        if not path.is_file():
            issues.append(f"{label}: missing file {path}")
            continue
        for i, r in enumerate(rows, start=2):
            for c in cols:
                if not (r.get(c) or "").strip():
                    issues.append(f"{label} row {i}: empty {c}")
    return [
        TrustCheck(
            "readiness_critical_fields",
            ok=len(issues) == 0,
            critical=True,
            message="Readiness CSVs have id_lead and org_name filled"
            if not issues
            else f"Missing critical fields: {len(issues)} issue(s), first: {issues[:5]}",
            details={"issues": issues[:100]},
        )
    ]


def check_taxonomy_hunt(hunt_path: Path) -> list[TrustCheck]:
    rows = read_csv_rows(hunt_path)
    bad_fit: list[str] = []
    bad_buyer: list[str] = []
    for r in rows:
        lid = (r.get("id_lead") or "").strip()
        fit = (r.get("ajuste_fit") or "").strip()
        buyer = (r.get("tipo_comprador") or "").strip().lower()
        if fit and fit not in ALLOWED_FIT_BUCKETS:
            bad_fit.append(f"{lid}:{fit}")
        if buyer and buyer not in ALLOWED_BUYER_KINDS:
            bad_buyer.append(f"{lid}:{buyer}")
    return [
        TrustCheck(
            "taxonomy_fit_bucket_hunt",
            ok=len(bad_fit) == 0,
            critical=False,
            message="Hunt ajuste_fit values are known"
            if not bad_fit
            else f"Unknown fit values: {bad_fit[:20]}",
            details={"bad": bad_fit[:50]},
        ),
        TrustCheck(
            "taxonomy_buyer_kind_hunt",
            ok=len(bad_buyer) == 0,
            critical=False,
            message="Hunt tipo_comprador values are in allowlist"
            if not bad_buyer
            else f"Unusual buyer_kind (review): {bad_buyer[:20]}",
            details={"bad": bad_buyer[:50]},
        ),
    ]


def check_stale_client_pack(
    summary_path: Path,
    *,
    max_age_hours: float,
) -> TrustCheck:
    summary = load_client_pack_summary(summary_path)
    if not summary:
        return TrustCheck(
            "client_pack_summary_exists",
            ok=False,
            critical=True,
            message=f"Missing or invalid summary: {summary_path}",
        )
    gen = summary.get("generated_at_utc") or ""
    dt = parse_iso_utc(str(gen))
    if dt is None:
        return TrustCheck(
            "client_pack_generated_at_parse",
            ok=False,
            critical=True,
            message=f"Cannot parse generated_at_utc: {gen!r}",
        )
    age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    ok = age_h <= max_age_hours
    return TrustCheck(
        "client_pack_freshness",
        ok=ok,
        critical=True,
        message=(
            f"client_pack generated_at_utc is within {max_age_hours}h "
            f"(age {age_h:.1f}h)"
            if ok
            else f"Stale client_pack: generated {age_h:.1f}h ago (limit {max_age_hours}h)"
        ),
        details={"generated_at_utc": gen, "age_hours": age_h},
    )


def check_provenance_db_path(
    *,
    resolved_db: Path,
    audit_md_path: Path,
) -> TrustCheck:
    if not audit_md_path.is_file():
        return TrustCheck(
            "provenance_audit_exists",
            ok=False,
            critical=False,
            message=f"No CONTACT_READINESS_AUDIT.md at {audit_md_path} (skip path compare)",
        )
    text = audit_md_path.read_text(encoding="utf-8")
    m = AUDIT_DB_LINE_RE.search(text)
    if not m:
        return TrustCheck(
            "provenance_audit_db_line",
            ok=False,
            critical=False,
            message="Could not find **Base de datos usada:** line in audit markdown",
        )
    recorded = Path(m.group(1).strip()).resolve()
    actual = resolved_db.resolve()
    ok = recorded == actual
    return TrustCheck(
        "provenance_audit_db_matches_config",
        ok=ok,
        critical=False,
        message=(
            "Audit markdown DB path matches configured SQLite"
            if ok
            else f"Path drift: audit has {recorded}, config has {actual}"
        ),
        details={"audit_path": str(recorded), "config_path": str(actual)},
    )


def verify_client_pack_against_db(
    summary_path: Path,
    db_path: Path,
) -> list[TrustCheck]:
    checks: list[TrustCheck] = []
    summary = load_client_pack_summary(summary_path)
    if not summary:
        return [
            TrustCheck(
                "pack_summary_load",
                ok=False,
                critical=True,
                message=f"Cannot load {summary_path}",
            )
        ]
    if not db_path.is_file():
        return [
            TrustCheck(
                "db_exists",
                ok=False,
                critical=True,
                message=f"DB not found: {db_path}",
            )
        ]
    conn = sqlite3.connect(str(db_path))
    try:
        live = db_lead_totals(conn)
    finally:
        conn.close()
    totals = summary.get("totals") or {}
    exp_rows = int(totals.get("lead_master_rows", -1))
    live_rows = int(live["lead_master_rows"])
    checks.append(
        TrustCheck(
            "pack_vs_db_lead_master_rows",
            ok=exp_rows == live_rows,
            critical=True,
            message=f"summary lead_master_rows {exp_rows} vs DB {live_rows}",
            details={"summary": exp_rows, "db": live_rows},
        )
    )
    exp_fit = totals.get("fit_bucket") or {}
    live_fit = live["fit_bucket"]
    norm_exp = normalized_fit_bucket_counts(exp_fit)
    norm_live = normalized_fit_bucket_counts(live_fit)
    fit_ok = norm_exp == norm_live
    checks.append(
        TrustCheck(
            "pack_vs_db_fit_buckets",
            ok=fit_ok,
            critical=True,
            message="summary fit_bucket matches DB" if fit_ok else "fit_bucket mismatch",
            details={
                "summary": exp_fit,
                "db": live_fit,
                "summary_normalized": norm_exp,
                "db_normalized": norm_live,
            },
        )
    )
    return checks


def verify_top20_and_readiness(
    *,
    top20_path: Path,
    ready_path: Path,
    needs_path: Path,
    hunt_path: Path,
    db_path: Path,
) -> list[TrustCheck]:
    checks: list[TrustCheck] = []
    top_rows = read_csv_rows(top20_path)
    if not top20_path.is_file():
        return [
            TrustCheck(
                "top20_file",
                ok=False,
                critical=True,
                message=f"Missing {top20_path}",
            )
        ]
    top_ids = id_leads_from_rows(top_rows)
    dups = duplicate_ids(top_ids)
    checks.append(
        TrustCheck(
            "top20_duplicate_ids",
            ok=len(dups) == 0,
            critical=True,
            message="top20 has unique id_lead" if not dups else f"Duplicates: {dups}",
        )
    )
    checks.append(
        TrustCheck(
            "top20_row_count",
            ok=len(top_rows) == 20,
            critical=True,
            message=f"Expected 20 top20 rows, got {len(top_rows)}",
            details={"n": len(top_rows)},
        )
    )

    ready_ids = set(id_leads_from_rows(read_csv_rows(ready_path)))
    needs_ids = set(id_leads_from_rows(read_csv_rows(needs_path)))
    hunt_ids = set(id_leads_from_rows(read_csv_rows(hunt_path)))

    ready_in_top = [r for r in top_rows if (r.get("readiness_status") or "").strip() == "ready_now"]
    needs_in_top = [r for r in top_rows if (r.get("readiness_status") or "").strip() == "needs_validation"]
    checks.append(
        TrustCheck(
            "top20_ready_needs_split",
            ok=len(ready_in_top) == 8 and len(needs_in_top) == 12,
            critical=False,
            message=f"top20 split ready_now={len(ready_in_top)}, needs_validation={len(needs_in_top)}",
            details={"ready_now": len(ready_in_top), "needs_validation": len(needs_in_top)},
        )
    )

    top_id_set = set(top_ids)
    ready_top: set[int] = set()
    for r in ready_in_top:
        raw = (r.get("id_lead") or "").strip()
        if raw.isdigit():
            ready_top.add(int(raw))
    checks.append(
        TrustCheck(
            "top20_ready_ids_match_readiness",
            ok=ready_top == ready_ids,
            critical=True,
            message="top20 ready_now id_lead set matches leads_ready_to_contact.csv",
            details={"top_ready": sorted(ready_top), "csv_ready": sorted(ready_ids)},
        )
    )

    missing_hunt = sorted(top_id_set - hunt_ids)
    checks.append(
        TrustCheck(
            "top20_ids_subset_hunt",
            ok=len(missing_hunt) == 0,
            critical=True,
            message="All top20 ids are in hunt cohort" if not missing_hunt else f"Not in hunt: {missing_hunt}",
        )
    )

    if db_path.is_file():
        conn = sqlite3.connect(str(db_path))
        try:
            missing_db: list[int] = []
            for lid in top_id_set:
                row = conn.execute("SELECT 1 FROM lead_master WHERE id=?", (lid,)).fetchone()
                if not row:
                    missing_db.append(lid)
        finally:
            conn.close()
        checks.append(
            TrustCheck(
                "top20_ids_in_lead_master",
                ok=len(missing_db) == 0,
                critical=True,
                message="All top20 ids exist in lead_master"
                if not missing_db
                else f"Missing in DB: {missing_db}",
            )
        )

    # Critical fields in top20
    bad: list[str] = []
    for i, r in enumerate(top_rows, start=2):
        if not (r.get("id_lead") or "").strip():
            bad.append(f"row {i} empty id_lead")
        if not (r.get("org_name") or "").strip():
            bad.append(f"row {i} empty org_name")
        if not (r.get("source_url") or "").strip() and not (r.get("evidence_summary") or "").strip():
            bad.append(f"row {i} missing source_url and evidence_summary")
    checks.append(
        TrustCheck(
            "top20_critical_fields",
            ok=len(bad) == 0,
            critical=True,
            message="top20 has required fields" if not bad else f"Field issues: {bad[:8]}",
            details={"issues": bad[:50]},
        )
    )

    return checks


def is_valid_http_url(url: str) -> bool:
    u = (url or "").strip()
    if not u:
        return False
    p = urlparse(u)
    return p.scheme in ("http", "https") and bool(p.netloc)


def probe_url(url: str, *, timeout: float, method: str = "HEAD") -> tuple[bool, str]:
    """Return (ok, reason)."""
    if not is_valid_http_url(url):
        return False, "invalid_or_empty_url"
    req = Request(url, method=method, headers={"User-Agent": "origenlab-operational-trust/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            if code is not None and 200 <= int(code) < 400:
                return True, f"ok:{code}"
            return False, f"http:{code}"
    except HTTPError as e:
        if method == "HEAD" and e.code in (403, 405, 501):
            return probe_url(url, timeout=timeout, method="GET")
        return False, f"http_error:{e.code}"
    except URLError as e:
        return False, f"url_error:{e.reason!s}"
    except Exception as e:
        return False, f"error:{type(e).__name__}"


def check_urls_batch(
    urls: list[str],
    *,
    timeout: float,
    max_failures: int,
    max_fail_ratio: float | None = None,
) -> TrustCheck:
    checked = 0
    failures: list[dict[str, str]] = []
    for u in urls:
        u = (u or "").strip()
        if not u:
            continue
        checked += 1
        ok, reason = probe_url(u, timeout=timeout)
        if not ok:
            failures.append({"url": u[:500], "reason": reason})
    n_fail = len(failures)
    ratio = (n_fail / checked) if checked else 0.0
    over_n = n_fail > max_failures
    over_ratio = max_fail_ratio is not None and checked > 0 and ratio > max_fail_ratio
    ok = checked > 0 and not over_n and not over_ratio
    return TrustCheck(
        "evidence_url_http",
        ok=ok,
        critical=True,
        message=(
            f"URL checks: {checked} checked, {n_fail} failed (limit {max_failures}"
            + (f", ratio limit {max_fail_ratio}" if max_fail_ratio is not None else "")
            + ")"
        ),
        details={
            "checked": checked,
            "failures": failures[:50],
            "failure_count": n_fail,
            "failure_ratio": ratio,
        },
    )


def collect_urls_from_csvs(
    paths_and_columns: list[tuple[Path, list[str]]],
) -> list[str]:
    urls: list[str] = []
    for path, cols in paths_and_columns:
        for r in read_csv_rows(path):
            for c in cols:
                v = (r.get(c) or "").strip()
                if v:
                    urls.append(v)
    return urls


def any_critical_failed(checks: Iterable[TrustCheck]) -> bool:
    return any(not c.ok and c.critical for c in checks)


@dataclass(frozen=True)
class LeadsActivePaths:
    """Standard repo locations for hunt, readiness exports, top20, client pack."""

    repo_root: Path
    hunt: Path
    ready: Path
    needs: Path
    not_ready: Path
    top20: Path
    merged_hunt: Path
    contact_audit_md: Path
    client_pack_summary: Path


def leads_active_paths(repo_root: Path) -> LeadsActivePaths:
    active = repo_root / "reports" / "out" / "active"
    return LeadsActivePaths(
        repo_root=repo_root,
        hunt=active / "leads_contact_hunt_current.csv",
        ready=active / "leads_ready_to_contact.csv",
        needs=active / "leads_needs_contact_research.csv",
        not_ready=active / "leads_not_ready.csv",
        top20=active / "leads_top20_for_client_report.csv",
        merged_hunt=active / "leads_contact_hunt_current_merged.csv",
        contact_audit_md=repo_root / "docs" / "generated" / "CONTACT_READINESS_AUDIT.md",
        client_pack_summary=repo_root / "reports" / "out" / "client_pack_latest" / "summary.json",
    )


def dedupe_urls(urls: list[str]) -> list[str]:
    return list(dict.fromkeys((u or "").strip() for u in urls if (u or "").strip()))


def check_evidence_url_formats(urls: list[str]) -> TrustCheck:
    """Reject non-http(s) URL strings collected from CSV columns (mailto:, relative, etc.)."""
    bad: list[str] = []
    for u in dedupe_urls(urls):
        if not is_valid_http_url(u):
            bad.append(u[:400])
    return TrustCheck(
        "evidence_url_format",
        ok=len(bad) == 0,
        critical=True,
        message="All collected evidence URLs use http(s) scheme with host"
        if not bad
        else f"Invalid URL format(s): {len(bad)} (showing first 5): {bad[:5]}",
        details={"invalid": bad[:30], "invalid_count": len(bad)},
    )


def trust_summary(checks: list[TrustCheck]) -> dict[str, Any]:
    crit_fail = sum(1 for c in checks if c.critical and not c.ok)
    non_fail = sum(1 for c in checks if not c.critical and not c.ok)
    return {
        "total": len(checks),
        "critical_failed": crit_fail,
        "noncritical_failed": non_fail,
        "all_ok": crit_fail == 0,
    }
