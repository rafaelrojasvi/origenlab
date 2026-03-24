"""Hunt / readiness / top20 cohort checks."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from origenlab_email_pipeline.operational_trust_csv import (
    duplicate_ids,
    id_leads_from_rows,
    read_csv_rows,
)
from origenlab_email_pipeline.operational_trust_types import (
    ALLOWED_BUYER_KINDS,
    ALLOWED_FIT_BUCKETS,
    TrustCheck,
)


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
