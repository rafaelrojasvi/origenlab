#!/usr/bin/env python3
"""Rebuild lead account rollup from lead_master (idempotent full rebuild).

Does not modify external_leads_raw or lead_master. Clears and repopulates:
lead_account_master, lead_account_aliases, lead_account_membership.

Run match_lead_accounts_to_existing_orgs.py after this to refresh mart links.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_upstream_reconcile import sql_upstream_active_bare
from origenlab_email_pipeline.leads_ingest import now_iso
from origenlab_email_pipeline.pipeline_run_recorder import finish_run, set_kv, start_run
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema
from origenlab_email_pipeline.org_normalize import (
    account_dedupe_key,
    better_canonical_name,
    is_junk_org_name,
    normalize_domain,
    normalize_org_name,
)


def _load_overrides(conn: sqlite3.Connection) -> dict[str, str]:
    """normalized_source -> target_account_name (canonical intent)."""
    cur = conn.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(normalized_source_value), ''), ''),
               NULLIF(TRIM(target_account_name), ''),
               NULLIF(TRIM(source_value), '')
        FROM lead_account_overrides
        WHERE is_active = 1 AND override_type IN ('remap_raw_name', 'merge', 'manual')
        """
    )
    out: dict[str, str] = {}
    for ns, tn, sv in cur.fetchall():
        if tn is None:
            continue
        if ns:
            out[normalize_org_name(ns) or ns.lower()] = tn
        if sv:
            out[normalize_org_name(sv)] = tn
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Build lead account rollup from lead_master")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    args = ap.parse_args()
    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    conn.execute("PRAGMA busy_timeout=300000")
    migrate_sqlite_schema(
        conn,
        layers={SchemaLayer.LEADS, SchemaLayer.LEAD_ACCOUNTS},
    )

    run_id = start_run(
        conn,
        script_name="scripts/build_lead_account_rollup.py",
        notes="lead account rollup full rebuild",
    )

    try:
        overrides = _load_overrides(conn)

        # Full rebuild of rollup tables (memberships + accounts + aliases).
        conn.execute("DELETE FROM lead_account_matches_existing_orgs")
        conn.execute("DELETE FROM lead_account_membership")
        conn.execute("DELETE FROM lead_account_aliases")
        conn.execute("DELETE FROM lead_account_master")
        conn.commit()

        ts = now_iso()
        cur = conn.execute(
            f"""
            SELECT id, source_name, org_name, domain, website, region, city,
                   organization_type_guess, first_seen_at, last_seen_at
            FROM lead_master
            WHERE {sql_upstream_active_bare()}
            ORDER BY id
            """
        )

        # account_dedupe_key -> lead_account_id
        key_to_id: dict[str, int] = {}
        # account_id -> canonical_name (display)
        id_canonical: dict[int, str] = {}
        # account_id -> set of (alias_display, normalized_alias, source_name)
        alias_buf: dict[int, set[tuple[str, str, str]]] = {}

        inserted_members = 0
        skipped_junk = 0

        for row in cur:
            (
                lead_id,
                source_name,
                org_name,
                domain_col,
                website,
                region,
                city,
                org_type,
                first_seen,
                last_seen,
            ) = row

            raw_org = (org_name or "").strip()
            pd = normalize_domain(website) or normalize_domain(domain_col)

            override_target = None
            if raw_org:
                override_target = overrides.get(normalize_org_name(raw_org))

            membership_method = "org_name_domain"
            evidence: dict = {"raw_org_name": raw_org, "primary_domain": pd}

            if override_target:
                display_name = override_target
                norm_cluster = normalize_org_name(display_name)
                membership_method = "override_remap"
                evidence["override_target"] = override_target
            elif not is_junk_org_name(raw_org):
                display_name = raw_org
                norm_cluster = normalize_org_name(raw_org)
            elif pd:
                # Junk name but we have a domain: group by domain for review.
                display_name = pd
                norm_cluster = normalize_org_name(pd) or pd.lower()
                membership_method = "domain_only_fallback"
                evidence["junk_name_fallback"] = True
            else:
                skipped_junk += 1
                continue

            if not norm_cluster and not pd:
                skipped_junk += 1
                continue

            dkey = account_dedupe_key(norm_cluster or (pd or ""), pd)
            if not dkey.strip("|"):
                skipped_junk += 1
                continue

            aid = key_to_id.get(dkey)
            if aid is None:
                conn.execute(
                    """
                    INSERT INTO lead_account_master (
                      account_dedupe_key, canonical_name, normalized_name, primary_domain,
                      official_website, org_type, region, city, country,
                      source_count, lead_count, first_seen_at, last_seen_at,
                      quality_status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CL', 0, 0, ?, ?, ?, ?, ?)
                    """,
                    (
                        dkey,
                        display_name,
                        norm_cluster or (pd or ""),
                        pd,
                        (website or "").strip() or None,
                        org_type,
                        region,
                        city,
                        first_seen,
                        last_seen,
                        "needs_review" if membership_method == "domain_only_fallback" else "ok",
                        ts,
                        ts,
                    ),
                )
                aid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
                key_to_id[dkey] = aid
                id_canonical[aid] = display_name
            else:
                id_canonical[aid] = better_canonical_name(id_canonical.get(aid, ""), display_name)
                conn.execute(
                    """
                    UPDATE lead_account_master SET
                      canonical_name = ?,
                      updated_at = ?,
                      region = COALESCE(?, region),
                      city = COALESCE(?, city),
                      org_type = COALESCE(?, org_type),
                      official_website = COALESCE(?, official_website),
                      first_seen_at = CASE
                        WHEN first_seen_at IS NULL OR ? < first_seen_at THEN ?
                        ELSE first_seen_at END,
                      last_seen_at = CASE
                        WHEN last_seen_at IS NULL OR ? > last_seen_at THEN ?
                        ELSE last_seen_at END
                    WHERE id = ?
                    """,
                    (
                        id_canonical[aid],
                        ts,
                        region,
                        city,
                        org_type,
                        (website or "").strip() or None,
                        first_seen,
                        first_seen,
                        last_seen,
                        last_seen,
                        aid,
                    ),
                )

            conn.execute(
                """
                INSERT INTO lead_account_membership (
                  lead_id, lead_account_id, membership_method, confidence, is_primary, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(lead_id, lead_account_id) DO UPDATE SET
                  membership_method = excluded.membership_method,
                  confidence = excluded.confidence,
                  evidence_json = excluded.evidence_json
                """,
                (lead_id, aid, membership_method, 1.0 if membership_method != "domain_only_fallback" else 0.6, json.dumps(evidence, ensure_ascii=False), ts),
            )
            inserted_members += 1

            # Alias: raw org string differs from canonical (and is not junk label).
            if raw_org and normalize_org_name(raw_org) != normalize_org_name(id_canonical[aid]):
                if not is_junk_org_name(raw_org):
                    alias_buf.setdefault(aid, set()).add((raw_org, normalize_org_name(raw_org), source_name or ""))

        conn.commit()

        for aid, pairs in alias_buf.items():
            for alias_name, norm_al, src in pairs:
                try:
                    conn.execute(
                        """
                        INSERT INTO lead_account_aliases (
                          lead_account_id, alias_name, normalized_alias, alias_type, source_name, confidence, created_at
                        ) VALUES (?, ?, ?, 'raw_org_name', ?, 0.85, ?)
                        """,
                        (aid, alias_name, norm_al, src, ts),
                    )
                except sqlite3.IntegrityError:
                    pass
        conn.commit()

        # Recompute aggregates
        conn.executescript(
            """
            UPDATE lead_account_master SET
              lead_count = (SELECT COUNT(*) FROM lead_account_membership m WHERE m.lead_account_id = lead_account_master.id),
              source_count = (
                SELECT COUNT(DISTINCT l.source_name)
                FROM lead_account_membership m
                JOIN lead_master l ON l.id = m.lead_id
                WHERE m.lead_account_id = lead_account_master.id
              ),
              first_seen_at = (
                SELECT MIN(COALESCE(l.first_seen_at, l.last_seen_at))
                FROM lead_account_membership m
                JOIN lead_master l ON l.id = m.lead_id
                WHERE m.lead_account_id = lead_account_master.id
              ),
              last_seen_at = (
                SELECT MAX(COALESCE(l.last_seen_at, l.first_seen_at))
                FROM lead_account_membership m
                JOIN lead_master l ON l.id = m.lead_id
                WHERE m.lead_account_id = lead_account_master.id
              );
            """
        )
        conn.execute("UPDATE lead_account_master SET updated_at = ?", (ts,))
        conn.commit()

        n_accounts = conn.execute("SELECT COUNT(*) FROM lead_account_master").fetchone()[0]
        set_kv(conn, "last_lead_account_rollup_run_id", str(run_id))
        print(f"Lead accounts: {n_accounts}, memberships: {inserted_members}, skipped (junk/no key): {skipped_junk}")
        return 0
    finally:
        finish_run(conn, run_id)
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
