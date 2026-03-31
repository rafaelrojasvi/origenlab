#!/usr/bin/env python3
"""Build the client-facing business mart tables (reproducible).

This script materializes:
- contact_master
- organization_master
- document_master
- opportunity_signals

Raw archive tables are not modified.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.freshness_dates import (
    MART_DATE_SLACK_DAYS_DEFAULT,
    email_date_iso_for_mart_timeline,
)
from origenlab_email_pipeline.business_mart import (
    classify_email_intents,
    clean_document_preview,
    doc_aggregates,
    domain_of,
    emails_in,
    equipment_tags_from_text,
    guess_org_name_from_domain,
    guess_org_type_from_domain,
    is_noise_sender,
    now_iso,
    primary_sender_email,
    signal_row,
)
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.pipeline_run_recorder import finish_run, get_git_describe, set_kv, start_run
from origenlab_email_pipeline.sqlite_migrate import SchemaLayer, migrate_sqlite_schema
from origenlab_email_pipeline.progress import iter_with_progress


def _derive_internal_domains(conn: sqlite3.Connection, *, max_n: int = 3) -> set[str]:
    # Use most common sender *addresses* (parsed) as a default internal guess.
    # We avoid brittle SQL string slicing because `sender` is often `"Name" <a@b>` etc.
    top_senders = conn.execute(
        """
        SELECT sender, COUNT(*) AS c
        FROM emails
        WHERE sender IS NOT NULL AND length(trim(sender)) > 0
        GROUP BY sender
        ORDER BY c DESC
        LIMIT 50
        """
    ).fetchall()
    dom_counts: Counter[str] = Counter()
    for sender, c in top_senders:
        se = primary_sender_email(sender or "")
        d = domain_of(se)
        if d:
            dom_counts[d] += int(c or 0)
    return {d for d, _ in dom_counts.most_common(max_n)}


def _ext(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    if "." not in s:
        return ""
    return s.rsplit(".", 1)[-1][:12]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--internal-domain", action="append", default=[], help="repeatable; add internal domains (default: inferred)")
    ap.add_argument("--limit-emails", type=int, default=None, help="debug: limit emails scanned")
    ap.add_argument("--rebuild", action="store_true", help="truncate and rebuild mart tables")
    ap.add_argument(
        "--mart-date-slack-days",
        type=int,
        default=MART_DATE_SLACK_DAYS_DEFAULT,
        help=(
            "Exclude email date_iso from mart first/last_seen (and document sent_at) when "
            "parsed calendar date is more than this many days after local today (default: "
            f"{MART_DATE_SLACK_DAYS_DEFAULT}). Raw emails table is never modified."
        ),
    )
    args = ap.parse_args()

    settings = load_settings()
    db_path = settings.resolved_sqlite_path()
    conn = connect(db_path)
    migrate_sqlite_schema(conn, layers={SchemaLayer.ARCHIVE_AND_MART})

    run_id = start_run(
        conn,
        script_name="scripts/mart/build_business_mart.py",
        notes="business mart build",
    )

    internal_domains = {d.lower().strip() for d in (args.internal_domain or []) if d.strip()}
    if not internal_domains:
        internal_domains = _derive_internal_domains(conn)

    print(f"DB: {db_path}")
    print(f"Internal domains (guess): {sorted(internal_domains)[:10]}")
    mart_slack = int(args.mart_date_slack_days)
    if mart_slack < 0 or mart_slack > 3660:
        mart_slack = MART_DATE_SLACK_DAYS_DEFAULT
    print(f"Mart date slack days (plausible timeline): {mart_slack}")

    if args.rebuild:
        conn.executescript(
            """
            DELETE FROM opportunity_signals;
            DELETE FROM document_master;
            DELETE FROM contact_master;
            DELETE FROM organization_master;
            """
        )
        conn.commit()

    # ---- document_master from attachment_extracts (success only) ----
    try:
        doc_rows = conn.execute(
            """
            SELECT
              a.id AS attachment_id,
              a.email_id,
              a.filename,
              a.content_type,
              e.sender,
              e.recipients,
              e.date_iso,
              e.subject,
              e.top_reply_clean,
              ae.detected_doc_type,
              ae.text_preview,
              ae.has_quote_terms,
              ae.has_invoice_terms,
              ae.has_purchase_terms,
              ae.has_price_list_terms
            FROM attachment_extracts ae
            JOIN attachments a ON a.id = ae.attachment_id
            JOIN emails e ON e.id = a.email_id
            WHERE ae.extract_status='success'
            """
        ).fetchall()

        inserted_docs = 0
        for r in iter_with_progress(doc_rows, desc="document_master"):
            attachment_id = int(r[0])
            email_id = int(r[1])
            filename = r[2] or ""
            sender_email = primary_sender_email(r[4] or "") or ""
            sender_domain = domain_of(sender_email) or ""
            recip_domains = [domain_of(x) for x in emails_in(r[5] or "")]
            recip_domains = [d for d in recip_domains if d]
            # pick the first external recipient domain as recipient_domain (best-effort)
            recipient_domain = ""
            for d in recip_domains:
                if d not in internal_domains:
                    recipient_domain = d
                    break
            if not recipient_domain and recip_domains:
                recipient_domain = recip_domains[0]

            subj = r[7] or ""
            top = r[8] or ""
            preview_raw = (r[10] or "")[:2000]
            preview_clean, preview_q = clean_document_preview(preview_raw)
            tags = equipment_tags_from_text(subj + "\n" + top + "\n" + preview_clean)
            conn.execute(
                """
                INSERT OR REPLACE INTO document_master
                (attachment_id, email_id, filename, extension, sender_email, sender_domain,
                 recipient_domain, sent_at, doc_type, extracted_preview_raw, extracted_preview_clean, preview_quality_score,
                 has_quote_terms, has_invoice_terms, has_purchase_terms, has_price_list_terms,
                 equipment_tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attachment_id,
                    email_id,
                    filename,
                    _ext(filename),
                    sender_email,
                    sender_domain,
                    recipient_domain,
                    email_date_iso_for_mart_timeline(r[6], slack_days=mart_slack),
                    (r[9] or "unknown"),
                    preview_raw,
                    preview_clean,
                    float(preview_q),
                    int(r[11] or 0),
                    int(r[12] or 0),
                    int(r[13] or 0),
                    int(r[14] or 0),
                    ",".join(tags),
                ),
            )
            inserted_docs += 1
        conn.commit()
        print(f"document_master rows: {inserted_docs:,}")

        # ---- precompute doc aggregates per email_id ----
        doc_aggs = doc_aggregates(
            conn.execute(
                """
                SELECT a.email_id, ae.detected_doc_type,
                       COALESCE(ae.has_quote_terms,0),
                       COALESCE(ae.has_invoice_terms,0),
                       COALESCE(ae.has_purchase_terms,0),
                       COALESCE(ae.has_price_list_terms,0)
                FROM attachment_extracts ae
                JOIN attachments a ON a.id = ae.attachment_id
                WHERE ae.extract_status='success'
                """
            )
        )

        # ---- scan emails to build contact_master + org aggregation ----
        contact = defaultdict(lambda: {
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
        })

        # We'll treat internal vs external based on internal_domains guess.
        sql = """
          SELECT id, sender, recipients, subject, COALESCE(top_reply_clean,''), COALESCE(full_body_clean,''), date_iso
          FROM emails
        """
        cur = conn.execute(sql)
        n = 0
        batch = cur.fetchmany(5000)
        while batch:
            for email_id, sender, recipients, subject, top, full, date_iso in batch:
                n += 1
                if args.limit_emails and n > args.limit_emails:
                    batch = []
                    break
                sender_s = sender or ""
                subj = subject or ""
                body = top or full or ""
                if is_noise_sender(sender_s, subj, body):
                    continue

                sender_email = primary_sender_email(sender_s)
                sender_dom = domain_of(sender_email) or ""
                recip_emails = emails_in(recipients or "")

                intents = classify_email_intents(subj, body)
                equip = equipment_tags_from_text(subj + "\n" + body)
                has_business_doc = int(email_id) in doc_aggs.business_doc_email_ids
                dt_counts = doc_aggs.doc_counts_by_email.get(int(email_id), Counter())

                # Inbound/outbound: outbound if sender is internal; inbound if sender is external.
                outbound = sender_dom in internal_domains
                inbound = bool(sender_dom) and not outbound

                # Update external contacts: if outbound -> recipients external; if inbound -> sender external.
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

        conn.execute("DELETE FROM contact_master")
        for email, row in iter_with_progress(contact.items(), desc="contact_master"):
            d = row["domain"] or ""
            equip_top = ",".join([t for t, _ in row["equip"].most_common(5)])
            # simple confidence: more interactions => higher (bounded)
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

        # ---- organization_master from contact_master rollup ----
        org = defaultdict(lambda: {
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
        })

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

        # ---- opportunity_signals (simple heuristics) ----
        conn.execute("DELETE FROM opportunity_signals")

        # 1) contacts with quote activity and quote docs
        sig_rows = []
        for email, row in contact.items():
            if row["quote_email"] >= 2 and row["quote_doc"] >= 1:
                sig_rows.append(
                    signal_row(
                        signal_type="quote_email_plus_quote_doc",
                        entity_kind="contact",
                        entity_key=email,
                        score=min(1.0, 0.2 + 0.1 * row["quote_email"] + 0.2 * min(row["quote_doc"], 3)),
                        details={"quote_email_count": row["quote_email"], "quote_doc_count": row["quote_doc"]},
                    )
                )

        # 2) orgs that are education + quote activity
        for d, o in org.items():
            if o["org_type"] == "education" and (o["quote_email"] >= 3 or o["quote_doc"] >= 1):
                sig_rows.append(
                    signal_row(
                        signal_type="education_with_quote_activity",
                        entity_kind="organization",
                        entity_key=d,
                        score=min(1.0, 0.2 + 0.05 * o["quote_email"] + 0.2 * min(o["quote_doc"], 3)),
                        details={"quote_email_count": o["quote_email"], "quote_doc_count": o["quote_doc"]},
                    )
                )

        # 3) dormant contacts (last_seen older than 24 months, but had volume)
        cutoff = "2024-03-01"  # simple static cutoff; documented as heuristic
        for email, row in contact.items():
            if (row["total"] or 0) >= 15 and row["last_seen_at"] and row["last_seen_at"] < cutoff:
                sig_rows.append(
                    signal_row(
                        signal_type="dormant_contact",
                        entity_kind="contact",
                        entity_key=email,
                        score=0.6,
                        details={"last_seen_at": row["last_seen_at"], "total_emails": row["total"]},
                    )
                )

        # 4) equipment theme repetition per contact
        for email, row in contact.items():
            top_tag, top_cnt = (row["equip"].most_common(1) or [("", 0)])[0]
            if top_tag and top_cnt >= 5:
                sig_rows.append(
                    signal_row(
                        signal_type="repeated_equipment_theme",
                        entity_kind="contact",
                        entity_key=email,
                        score=min(1.0, 0.25 + 0.05 * top_cnt),
                        details={"equipment_tag": top_tag, "mentions": top_cnt},
                    )
                )

        conn.executemany(
            """
            INSERT INTO opportunity_signals
            (signal_type, entity_kind, entity_key, email_id, attachment_id, score, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            sig_rows,
        )
        conn.commit()
        print(f"opportunity_signals rows: {len(sig_rows):,}")

        built_at = now_iso()
        set_kv(conn, "mart_built_at", built_at)
        set_kv(conn, "mart_build_git_describe", get_git_describe())
        set_kv(conn, "last_mart_pipeline_run_id", str(run_id))
    finally:
        finish_run(conn, run_id)
    conn.close()
    print("Done.")
    print(f"created_at|{built_at}")


if __name__ == "__main__":
    main()

