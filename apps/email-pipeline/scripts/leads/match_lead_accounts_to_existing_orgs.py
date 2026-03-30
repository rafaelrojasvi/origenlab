#!/usr/bin/env python3
"""Match lead_account_master rows to organization_master (mart). Idempotent rebuild.

Uses organization_master.domain as the stable key (TEXT PRIMARY KEY).

Matching order (deterministic first):
1) exact primary_domain == organization_master.domain
2) official_website host == domain
3) exact normalized canonical_name vs normalized organization_name_guess
4) exact normalized alias vs organization_name_guess
5) optional fuzzy name match only if ratio >= 0.97 and similar length (needs_review)
"""

from __future__ import annotations

import argparse
import difflib
import json
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.leads_ingest import now_iso
from origenlab_email_pipeline.pipeline_run_recorder import finish_run, set_kv, start_run
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema
from origenlab_email_pipeline.org_normalize import normalize_domain, normalize_org_name


def _norm_name_map(
    conn: sqlite3.Connection,
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Map normalized_name_guess -> domain (first wins), and list of (domain, norm_guess)."""
    cur = conn.execute(
        "SELECT domain, organization_name_guess FROM organization_master WHERE domain IS NOT NULL"
    )
    rows = cur.fetchall()
    nmap: dict[str, str] = {}
    pairs: list[tuple[str, str]] = []
    for dom, guess in rows:
        if not dom:
            continue
        d = dom.strip().lower()
        ng = normalize_org_name(guess or "")
        pairs.append((d, ng))
        if ng and ng not in nmap:
            nmap[ng] = d
    return nmap, pairs


def _aliases_by_account(conn: sqlite3.Connection) -> dict[int, list[str]]:
    cur = conn.execute(
        "SELECT lead_account_id, normalized_alias FROM lead_account_aliases"
    )
    out: dict[int, list[str]] = {}
    for aid, na in cur.fetchall():
        if not na:
            continue
        out.setdefault(int(aid), []).append(na)
    return out


def _pick_fuzzy(norm_account: str, pairs: list[tuple[str, str]]) -> tuple[str, float] | None:
    if len(norm_account) < 8:
        return None
    ln = len(norm_account)
    best: tuple[str, float] | None = None
    best_r = 0.0
    for dom, ng in pairs:
        if not ng:
            continue
        if min(ln, len(ng)) / max(ln, len(ng), 1) < 0.82:
            continue
        r = difflib.SequenceMatcher(None, norm_account, ng).ratio()
        if r > best_r:
            best_r = r
            best = (dom, r)
    if best is None or best_r < 0.97:
        return None
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description="Match lead accounts to organization_master")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--allow-fuzzy",
        action="store_true",
        help="Allow high-threshold fuzzy name match (always review_status=needs_review)",
    )
    args = ap.parse_args()
    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    conn.execute("PRAGMA busy_timeout=300000")
    migrate_sqlite_schema(conn, layers={SchemaLayer.LEAD_ACCOUNTS})

    run_id = start_run(
        conn,
        script_name="scripts/leads/match_lead_accounts_to_existing_orgs.py",
        notes="match lead_account_master to organization_master",
    )

    try:
        try:
            conn.execute("SELECT 1 FROM organization_master LIMIT 1")
        except sqlite3.OperationalError:
            print("organization_master missing; build mart first.", file=sys.stderr)
            return 1

        name_to_domain, pairs = _norm_name_map(conn)
        aliases = _aliases_by_account(conn)
        ts = now_iso()

        conn.execute("DELETE FROM lead_account_matches_existing_orgs")
        conn.commit()

        accounts = conn.execute(
            """
            SELECT id, primary_domain, official_website, normalized_name, canonical_name
            FROM lead_account_master
            """
        ).fetchall()

        inserted = 0
        for aid, pdom, oweb, norm_name, canonical in accounts:
            pdom = (pdom or "").strip().lower()
            web_dom = normalize_domain(oweb or "") or ""
            nn = norm_name or normalize_org_name(canonical or "")

            chosen: tuple[str, str, float, str, str] | None = None  # domain, method, conf, review, evidence_json

            # 1) Primary domain
            if pdom:
                row = conn.execute(
                    "SELECT 1 FROM organization_master WHERE lower(domain) = ?", (pdom,)
                ).fetchone()
                if row:
                    chosen = (
                        pdom,
                        "domain_exact",
                        1.0,
                        "auto",
                        json.dumps({"primary_domain": pdom}, ensure_ascii=False),
                    )

            # 2) Website host
            if chosen is None and web_dom:
                row = conn.execute(
                    "SELECT 1 FROM organization_master WHERE lower(domain) = ?", (web_dom,)
                ).fetchone()
                if row:
                    chosen = (
                        web_dom,
                        "official_website_domain",
                        0.98,
                        "auto",
                        json.dumps({"website_domain": web_dom}, ensure_ascii=False),
                    )

            # 3) Exact normalized org name
            if chosen is None and nn:
                dom = name_to_domain.get(nn)
                if dom:
                    chosen = (
                        dom,
                        "normalized_name_exact",
                        0.95,
                        "auto",
                        json.dumps({"normalized_name": nn}, ensure_ascii=False),
                    )

            # 4) Aliases
            if chosen is None and nn:
                for al in aliases.get(int(aid), []):
                    dom = name_to_domain.get(al)
                    if dom:
                        chosen = (
                            dom,
                            "alias_normalized_exact",
                            0.93,
                            "auto",
                            json.dumps({"normalized_alias": al}, ensure_ascii=False),
                        )
                        break

            # 5) Fuzzy
            if chosen is None and args.allow_fuzzy and nn:
                fz = _pick_fuzzy(nn, pairs)
                if fz:
                    dom, ratio = fz
                    chosen = (
                        dom,
                        "fuzzy_name_high_threshold",
                        round(0.75 + 0.2 * ratio, 4),
                        "needs_review",
                        json.dumps({"normalized_name": nn, "fuzzy_ratio": ratio}, ensure_ascii=False),
                    )

            if chosen is None:
                continue

            dom, method, conf, review, evid = chosen
            evid_obj = json.loads(evid) if evid else {}
            evid_obj["match_script"] = "match_lead_accounts_to_existing_orgs.py"
            evid_obj["rule_order"] = method
            evid_out = json.dumps(evid_obj, ensure_ascii=False)
            try:
                conn.execute(
                    """
                    INSERT INTO lead_account_matches_existing_orgs (
                      lead_account_id, organization_domain, match_method, confidence, evidence_json, review_status, created_at, pipeline_run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (aid, dom, method, conf, evid_out, review, ts, run_id),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass

        conn.commit()
        set_kv(conn, "last_account_match_run_id", str(run_id))
        print(f"Inserted {inserted} lead_account -> organization_master matches.")
        return 0
    finally:
        finish_run(conn, run_id)
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
