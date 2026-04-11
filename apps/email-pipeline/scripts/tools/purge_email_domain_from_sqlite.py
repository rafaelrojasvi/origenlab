#!/usr/bin/env python3
"""Remove archived mail and derived rows tied to an email domain (e.g. proveedor Ohaus).

Deletes from ``emails`` (and, with foreign keys on, cascades attachments /
attachment_extracts / document_master / commercial_email_signal_fact where FKs exist).
Also removes ``opportunity_signals`` rows pointing at those emails (no FK).

Optionally cleans ``contact_master``, ``organization_master``, ``supplier_master``,
and ``lead_master``-related rows for the same domain.

**This does not delete anything from Gmail.** Ingest scripts only download mail. To remove
messages from the mailbox, use Gmail (example search)::

  from:*ohaus.com OR to:*ohaus.com OR from:*.ohaus.com OR to:*.ohaus.com

Select all → Move to trash → Empty trash. Then re-ingest or leave SQLite as-is.

Example (preview)::

  uv run python scripts/tools/purge_email_domain_from_sqlite.py --domain ohaus.com

Apply::

  uv run python scripts/tools/purge_email_domain_from_sqlite.py --domain ohaus.com --apply

After a large purge, rebuild the mart if you use it::

  uv run python scripts/mart/build_business_mart.py
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.timeutil import now_iso


def _domain_like_patterns(dom: str) -> tuple[str, str]:
    """SQL LIKE patterns for matching RFC-style headers and mailbox strings.

    SQLite LIKE matches the **entire** string. Pattern ``%@ohaus.com`` therefore misses
    ``Name <user@ohaus.com>`` (trailing ``>``). Use ``%@domain%`` and ``%@%.domain%``
    (subdomains: ``user@mail.example.com``).
    """
    d = dom.lower().strip().lstrip("@")
    if not d or "." not in d:
        raise ValueError(f"Invalid domain: {dom!r}")
    at_domain = f"%@{d}%"
    at_subdomain = f"%@%.{d}%"
    return at_domain, at_subdomain


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def main() -> int:
    ap = argparse.ArgumentParser(description="Purge emails + related SQLite rows for one email domain.")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument("--domain", required=True, help="Bare domain, e.g. ohaus.com")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Execute deletes (default: print counts only).",
    )
    ap.add_argument(
        "--no-mart",
        action="store_true",
        help="Do not delete contact_master / organization_master / supplier_master for this domain.",
    )
    ap.add_argument(
        "--no-leads",
        action="store_true",
        help="Do not delete lead_master (and junction) rows for this domain.",
    )
    ap.add_argument(
        "--purge-suppressions",
        action="store_true",
        help="Also delete contact_email_suppression rows for addresses on this domain.",
    )
    ap.add_argument(
        "--retain-supplier-row",
        action="store_true",
        help="After purge, upsert supplier_master for this domain (proveedor → still excluded from marketing).",
    )
    args = ap.parse_args()

    db_path = args.db or load_settings().resolved_sqlite_path()
    if not db_path.is_file():
        print("Database file not found:", db_path, file=sys.stderr)
        return 1

    try:
        at_dom, at_sub = _domain_like_patterns(args.domain)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path), timeout=120.0)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        # ---- emails matching domain (sender or recipients) ----
        email_match_sql = """
            SELECT id FROM emails
            WHERE lower(COALESCE(sender, '')) LIKE ?
               OR lower(COALESCE(sender, '')) LIKE ?
               OR lower(COALESCE(recipients, '')) LIKE ?
               OR lower(COALESCE(recipients, '')) LIKE ?
        """
        params = (at_dom, at_sub, at_dom, at_sub)
        ids = [int(r[0]) for r in conn.execute(email_match_sql, params).fetchall()]
        print(f"emails matching @{args.domain}: {len(ids):,}")

        if not args.apply:
            if _table_exists(conn, "contact_master") and not args.no_mart:
                c = conn.execute(
                    """
                    SELECT COUNT(*) FROM contact_master
                    WHERE lower(email) LIKE ? OR lower(email) LIKE ? OR lower(COALESCE(domain,'')) = ?
                    """,
                    (at_dom, at_sub, args.domain.strip().lower().lstrip("@")),
                ).fetchone()[0]
                print(f"contact_master rows (would delete): {c:,}")
            if _table_exists(conn, "organization_master") and not args.no_mart:
                c = conn.execute(
                    "SELECT COUNT(*) FROM organization_master WHERE lower(domain) = ?",
                    (args.domain.strip().lower().lstrip("@"),),
                ).fetchone()[0]
                print(f"organization_master rows (would delete): {c:,}")
            if _table_exists(conn, "supplier_master") and not args.no_mart:
                if args.retain_supplier_row:
                    print("supplier_master: would upsert row (--retain-supplier-row), not delete")
                else:
                    c = conn.execute(
                        "SELECT COUNT(*) FROM supplier_master WHERE lower(trim(domain_norm)) = ?",
                        (args.domain.strip().lower().lstrip("@"),),
                    ).fetchone()[0]
                    print(f"supplier_master rows (would delete): {c:,}")
            if args.purge_suppressions and _table_exists(conn, "contact_email_suppression"):
                c = conn.execute(
                    """
                    SELECT COUNT(*) FROM contact_email_suppression
                    WHERE lower(email) LIKE ? OR lower(email) LIKE ?
                    """,
                    (at_dom, at_sub),
                ).fetchone()[0]
                print(f"contact_email_suppression rows (would delete): {c:,}")
            print("\nDry run. Pass --apply to delete.")
            return 0

        dnorm = args.domain.strip().lower().lstrip("@")
        if not ids:
            print("No matching emails; still running mart/lead cleanup if enabled.")
        else:
            placeholders = ",".join("?" * len(ids))
            if _table_exists(conn, "opportunity_signals"):
                n_sig = conn.execute(
                    f"DELETE FROM opportunity_signals WHERE email_id IN ({placeholders})",
                    ids,
                ).rowcount
                print(f"Deleted opportunity_signals rows: {n_sig:,}")
            conn.execute(f"DELETE FROM emails WHERE id IN ({placeholders})", ids)
            print(f"Deleted emails rows: {len(ids):,}")

        if not args.no_mart:
            if _table_exists(conn, "contact_master"):
                cur = conn.execute(
                    """
                    DELETE FROM contact_master
                    WHERE lower(email) LIKE ? OR lower(email) LIKE ? OR lower(COALESCE(domain,'')) = ?
                    """,
                    (at_dom, at_sub, dnorm),
                )
                print(f"Deleted contact_master rows: {cur.rowcount:,}")
            if _table_exists(conn, "organization_master"):
                cur = conn.execute(
                    "DELETE FROM organization_master WHERE lower(domain) = ?",
                    (dnorm,),
                )
                print(f"Deleted organization_master rows: {cur.rowcount:,}")
            if _table_exists(conn, "supplier_master") and not args.retain_supplier_row:
                cur = conn.execute(
                    "DELETE FROM supplier_master WHERE lower(trim(domain_norm)) = ?",
                    (dnorm,),
                )
                print(f"Deleted supplier_master rows: {cur.rowcount:,}")
            elif _table_exists(conn, "supplier_master") and args.retain_supplier_row:
                print("Skipped supplier_master delete (--retain-supplier-row).")

        if not args.no_leads:
            lead_where = """
                lower(COALESCE(email,'')) LIKE ? OR lower(COALESCE(email,'')) LIKE ?
                OR lower(COALESCE(domain_norm,'')) = ? OR lower(COALESCE(domain,'')) = ?
            """
            lead_params = (at_dom, at_sub, dnorm, dnorm)
            if _table_exists(conn, "lead_upstream_reconcile_log"):
                cur = conn.execute(
                    f"DELETE FROM lead_upstream_reconcile_log WHERE lead_id IN (SELECT id FROM lead_master WHERE {lead_where})",
                    lead_params,
                )
                print(f"Deleted lead_upstream_reconcile_log rows: {cur.rowcount:,}")
            if _table_exists(conn, "lead_matches_existing_contacts"):
                cur = conn.execute(
                    """
                    DELETE FROM lead_matches_existing_contacts
                    WHERE lower(matched_contact_email) LIKE ?
                       OR lower(matched_contact_email) LIKE ?
                    """,
                    (at_dom, at_sub),
                )
                print(f"Deleted lead_matches_existing_contacts rows: {cur.rowcount:,}")
            if _table_exists(conn, "lead_matches_existing_orgs"):
                cur = conn.execute(
                    "DELETE FROM lead_matches_existing_orgs WHERE lower(matched_domain) = ?",
                    (dnorm,),
                )
                print(f"Deleted lead_matches_existing_orgs rows: {cur.rowcount:,}")
            if _table_exists(conn, "lead_master"):
                cur = conn.execute(
                    f"DELETE FROM lead_master WHERE {lead_where}",
                    lead_params,
                )
                print(f"Deleted lead_master rows: {cur.rowcount:,}")

        if args.purge_suppressions and _table_exists(conn, "contact_email_suppression"):
            cur = conn.execute(
                """
                DELETE FROM contact_email_suppression
                WHERE lower(email) LIKE ? OR lower(email) LIKE ?
                """,
                (at_dom, at_sub),
            )
            print(f"Deleted contact_email_suppression rows: {cur.rowcount:,}")

        if args.retain_supplier_row and _table_exists(conn, "supplier_master"):
            ts = now_iso()
            trade = dnorm.split(".")[0].title() if dnorm else dnorm
            conn.execute(
                """
                INSERT INTO supplier_master (
                  domain_norm, trade_name, website, region_label, country_label,
                  equipment_focus, notes, is_exclusion, created_at, updated_at
                ) VALUES (?, ?, NULL, NULL, NULL, NULL, ?, 0, ?, ?)
                ON CONFLICT(domain_norm) DO UPDATE SET
                  updated_at = excluded.updated_at,
                  notes = COALESCE(supplier_master.notes, excluded.notes)
                """,
                (
                    dnorm,
                    trade,
                    "Retained for marketing exclusion after domain purge (proveedor).",
                    ts,
                    ts,
                ),
            )
            print(f"Upserted supplier_master row for domain_norm={dnorm!r} (marketing skip).")

        conn.commit()
    finally:
        conn.close()

    print("Done. Rebuild mart if needed: uv run python scripts/mart/build_business_mart.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
