"""Client pack summary vs SQLite consistency checks."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.lead_provenance import read_operational_run_id_from_env
from origenlab_email_pipeline.lead_upstream_reconcile import sql_upstream_active_bare
from origenlab_email_pipeline.leads_schema import ensure_leads_tables

from origenlab_email_pipeline.operational_trust_csv import load_client_pack_summary
from origenlab_email_pipeline.operational_trust_types import TrustCheck

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
    active_pred = sql_upstream_active_bare()
    total = conn.execute(f"SELECT COUNT(*) FROM lead_master WHERE {active_pred}").fetchone()[0]
    fit_rows = conn.execute(
        f"""
        SELECT {_FIT_BUCKET_GROUP_SQL} AS fb, COUNT(*)
        FROM lead_master
        WHERE {active_pred}
        GROUP BY fb
        """
    ).fetchall()
    fit_counts = {str(r[0]): int(r[1]) for r in fit_rows}
    return {"lead_master_rows": int(total), "fit_bucket": fit_counts}


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
    prov = summary.get("provenance")
    if isinstance(prov, dict):
        spr = prov.get("db_path_resolved")
        if isinstance(spr, str) and spr.strip():
            try:
                prov_ok = Path(spr).resolve() == db_path.resolve()
            except OSError:
                prov_ok = False
            checks.append(
                TrustCheck(
                    "pack_summary_provenance_db_matches_session",
                    ok=prov_ok,
                    critical=False,
                    message=(
                        "summary.json provenance db_path_resolved matches SQLite used in this check"
                        if prov_ok
                        else f"provenance db_path_resolved {spr!r} != session db {db_path!r}"
                    ),
                    details={"provenance_path": spr, "session_db": str(db_path.resolve())},
                )
            )
    env_run_id = read_operational_run_id_from_env()
    if env_run_id:
        pack_raw = prov.get("operational_run_id") if isinstance(prov, dict) else None
        pack_run_id = (str(pack_raw).strip() if pack_raw is not None else "")
        rid_ok = bool(pack_run_id) and pack_run_id == env_run_id
        checks.append(
            TrustCheck(
                "pack_operational_run_id_matches_env",
                ok=rid_ok,
                critical=True,
                message=(
                    "summary.json provenance.operational_run_id matches ORIGENLAB_LEADS_OPERATIONAL_RUN_ID"
                    if rid_ok
                    else (
                        "summary.json missing or mismatched provenance.operational_run_id vs "
                        f"ORIGENLAB_LEADS_OPERATIONAL_RUN_ID (env={env_run_id!r}, pack={pack_run_id!r})"
                    )
                ),
                details={"env_run_id": env_run_id, "pack_run_id": pack_run_id or None},
            )
        )
    return checks
