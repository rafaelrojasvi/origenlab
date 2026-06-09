"""Scan emails and rebuild ``contact_master`` / ``organization_master``."""

from __future__ import annotations

import sqlite3
import time
from collections import Counter, defaultdict
from typing import Any

from origenlab_email_pipeline.business_mart import (
    DocAgg,
    classify_email_intents,
    domain_of,
    emails_in,
    equipment_tags_from_text,
    guess_org_name_from_domain,
    guess_org_type_from_domain,
    is_noise_sender,
    primary_sender_email,
)
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source
from origenlab_email_pipeline.core.mart.build_options import MartBuildOptions
from origenlab_email_pipeline.freshness_dates import email_date_iso_for_mart_timeline
from origenlab_email_pipeline.progress import iter_with_progress

ContactAggRow = dict[str, Any]
ContactMap = dict[str, ContactAggRow]
OrgMap = dict[str, dict[str, Any]]


def fetch_full_body_clean_for_email(conn: sqlite3.Connection, email_id: int) -> str:
    row = conn.execute(
        "SELECT COALESCE(full_body_clean,'') FROM emails WHERE id = ?",
        (int(email_id),),
    ).fetchone()
    return str(row[0]) if row else ""


def _new_contact_row() -> ContactAggRow:
    return {
        "contact_name_best": None,
        "domain": None,
        "org_name": None,
        "org_type": None,
        "first_seen_at": None,
        "last_seen_at": None,
        "total": 0,
        "inbound": 0,
        "outbound": 0,
        "quote_email": 0,
        "invoice_email": 0,
        "purchase_email": 0,
        "business_doc_email": 0,
        "quote_doc": 0,
        "invoice_doc": 0,
        "equip": Counter(),
    }


def scan_email_contacts(
    conn: sqlite3.Connection,
    *,
    options: MartBuildOptions,
    doc_aggs: DocAgg,
) -> tuple[ContactMap, int]:
    """Scan ``emails`` and aggregate external contact rollups (in-memory)."""
    contact: ContactMap = defaultdict(_new_contact_row)

    stage_t0 = time.monotonic()
    sql = (
        "SELECT id, sender, recipients, subject, COALESCE(top_reply_clean,''), date_iso FROM emails"
    )
    where_clauses: list[str] = []
    params: list[object] = []
    if options.canonical_only or options.dashboard_fast:
        where_clauses.append(sql_predicate_contacto_gmail_source(table_alias=None, coalesce_null=False))
    if options.since_days is not None:
        days = max(1, min(int(options.since_days), 3650))
        where_clauses.append("substr(COALESCE(date_iso,''),1,10) >= date('now', ?)")
        params.append(f"-{days} day")
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    cur = conn.execute(sql, params)
    n = 0
    top_reply_nonempty_rows = 0
    top_reply_empty_rows = 0
    full_body_fallback_used_rows = 0
    top_reply_total_chars = 0
    full_body_fallback_total_chars = 0
    full_body_lazy_fetches = 0
    full_body_lazy_fetch_seconds = 0.0
    batch = cur.fetchmany(5000)
    internal_domains = set(options.internal_domains)
    mart_slack = options.mart_date_slack_days
    while batch:
        for email_id, sender, recipients, subject, top, date_iso in batch:
            n += 1
            if top:
                top_reply_nonempty_rows += 1
                top_reply_total_chars += len(top)
                body = top
            else:
                top_reply_empty_rows += 1
                fetch_t0 = time.monotonic()
                full = fetch_full_body_clean_for_email(conn, int(email_id))
                full_body_lazy_fetch_seconds += time.monotonic() - fetch_t0
                full_body_lazy_fetches += 1
                if full:
                    full_body_fallback_used_rows += 1
                    full_body_fallback_total_chars += len(full)
                body = full
            if options.limit_emails and n > options.limit_emails:
                batch = []
                break
            sender_s = sender or ""
            subj = subject or ""
            if is_noise_sender(sender_s, subj, body):
                continue

            sender_email = primary_sender_email(sender_s)
            sender_dom = domain_of(sender_email) or ""
            recip_emails = emails_in(recipients or "")

            intents = classify_email_intents(subj, body)
            equip = equipment_tags_from_text(subj + "\n" + body)
            has_business_doc = int(email_id) in doc_aggs.business_doc_email_ids
            dt_counts = doc_aggs.doc_counts_by_email.get(int(email_id), Counter())

            outbound = sender_dom in internal_domains
            inbound = bool(sender_dom) and not outbound

            targets: list[str] = []
            if outbound:
                for e in recip_emails:
                    d = domain_of(e) or ""
                    if d and d not in internal_domains:
                        targets.append(e)
            elif inbound and sender_email:
                if sender_dom and sender_dom not in internal_domains:
                    targets.append(sender_email)

            for e in targets:
                d = domain_of(e) or ""
                if not d:
                    continue
                row = contact[e]
                row["domain"] = d
                row["org_name"] = guess_org_name_from_domain(d)
                row["org_type"] = guess_org_type_from_domain(d)
                row["total"] += 1
                row["inbound"] += 1 if inbound else 0
                row["outbound"] += 1 if outbound else 0
                row["quote_email"] += 1 if intents["is_quote_email"] else 0
                row["invoice_email"] += 1 if intents["is_invoice_email"] else 0
                row["purchase_email"] += 1 if intents["is_purchase_email"] else 0
                row["business_doc_email"] += 1 if has_business_doc else 0
                row["quote_doc"] += int(dt_counts.get("quote", 0))
                row["invoice_doc"] += int(dt_counts.get("invoice", 0))
                for tag in equip:
                    row["equip"][tag] += 1

                d_iso = email_date_iso_for_mart_timeline(date_iso, slack_days=mart_slack)
                if d_iso:
                    if row["first_seen_at"] is None or d_iso < row["first_seen_at"]:
                        row["first_seen_at"] = d_iso
                    if row["last_seen_at"] is None or d_iso > row["last_seen_at"]:
                        row["last_seen_at"] = d_iso

        batch = cur.fetchmany(5000)

    print(f"Scanned emails (for mart): {n:,}")
    print(f"[timing] email_scan_seconds={time.monotonic() - stage_t0:.2f}")
    print(f"[mart-profile] top_reply_nonempty_rows={top_reply_nonempty_rows}")
    print(f"[mart-profile] top_reply_empty_rows={top_reply_empty_rows}")
    print(f"[mart-profile] full_body_fallback_used_rows={full_body_fallback_used_rows}")
    print(f"[mart-profile] top_reply_total_chars={top_reply_total_chars}")
    print(f"[mart-profile] full_body_fallback_total_chars={full_body_fallback_total_chars}")
    print(f"[mart-profile] full_body_lazy_fetches={full_body_lazy_fetches}")
    print(f"[timing] full_body_lazy_fetch_seconds={full_body_lazy_fetch_seconds:.2f}")
    return dict(contact), n


def rebuild_contact_master(conn: sqlite3.Connection, contact: ContactMap) -> None:
    stage_t0 = time.monotonic()
    conn.execute("DELETE FROM contact_master")
    for email, row in iter_with_progress(contact.items(), desc="contact_master"):
        d = row["domain"] or ""
        equip_top = ",".join([t for t, _ in row["equip"].most_common(5)])
        conf = min(1.0, (row["total"] or 0) / 25.0)
        conn.execute(
            """
            INSERT INTO contact_master
            (email, contact_name_best, domain, organization_name_guess, organization_type_guess,
             first_seen_at, last_seen_at,
             total_emails, inbound_emails, outbound_emails,
             quote_email_count, invoice_email_count, purchase_email_count,
             business_doc_email_count, quote_doc_count, invoice_doc_count,
             top_equipment_tags, confidence_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                row["contact_name_best"],
                d,
                row["org_name"],
                row["org_type"],
                row["first_seen_at"],
                row["last_seen_at"],
                row["total"],
                row["inbound"],
                row["outbound"],
                row["quote_email"],
                row["invoice_email"],
                row["purchase_email"],
                row["business_doc_email"],
                row["quote_doc"],
                row["invoice_doc"],
                equip_top,
                conf,
            ),
        )
    conn.commit()
    print(f"contact_master rows: {len(contact):,}")
    print(f"[timing] contact_master_seconds={time.monotonic() - stage_t0:.2f}")


def rebuild_organization_master(conn: sqlite3.Connection, contact: ContactMap) -> OrgMap:
    stage_t0 = time.monotonic()
    org: OrgMap = defaultdict(
        lambda: {
            "org_name": None,
            "org_type": None,
            "first": None,
            "last": None,
            "total_emails": 0,
            "contacts": 0,
            "quote_email": 0,
            "invoice_email": 0,
            "purchase_email": 0,
            "business_doc_email": 0,
            "quote_doc": 0,
            "invoice_doc": 0,
            "equip": Counter(),
            "contacts_by_volume": Counter(),
        }
    )

    for email, row in contact.items():
        d = row["domain"] or ""
        if not d:
            continue
        o = org[d]
        o["org_name"] = guess_org_name_from_domain(d)
        o["org_type"] = guess_org_type_from_domain(d)
        o["total_emails"] += row["total"]
        o["contacts"] += 1
        o["quote_email"] += row["quote_email"]
        o["invoice_email"] += row["invoice_email"]
        o["purchase_email"] += row["purchase_email"]
        o["business_doc_email"] += row["business_doc_email"]
        o["quote_doc"] += row["quote_doc"]
        o["invoice_doc"] += row["invoice_doc"]
        o["contacts_by_volume"][email] += row["total"]
        for tag, c in row["equip"].items():
            o["equip"][tag] += c
        if row["first_seen_at"]:
            if o["first"] is None or row["first_seen_at"] < o["first"]:
                o["first"] = row["first_seen_at"]
        if row["last_seen_at"]:
            if o["last"] is None or row["last_seen_at"] > o["last"]:
                o["last"] = row["last_seen_at"]

    conn.execute("DELETE FROM organization_master")
    for d, o in iter_with_progress(org.items(), desc="organization_master"):
        equip_top = ",".join([t for t, _ in o["equip"].most_common(5)])
        key_contacts = ",".join([e for e, _ in o["contacts_by_volume"].most_common(5)])
        conn.execute(
            """
            INSERT INTO organization_master
            (domain, organization_name_guess, organization_type_guess,
             first_seen_at, last_seen_at,
             total_emails, total_contacts,
             quote_email_count, invoice_email_count, purchase_email_count,
             business_doc_email_count, quote_doc_count, invoice_doc_count,
             top_equipment_tags, key_contacts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                d,
                o["org_name"],
                o["org_type"],
                o["first"],
                o["last"],
                o["total_emails"],
                o["contacts"],
                o["quote_email"],
                o["invoice_email"],
                o["purchase_email"],
                o["business_doc_email"],
                o["quote_doc"],
                o["invoice_doc"],
                equip_top,
                key_contacts,
            ),
        )
    conn.commit()
    print(f"organization_master rows: {len(org):,}")
    print(f"[timing] organization_master_seconds={time.monotonic() - stage_t0:.2f}")
    return dict(org)
