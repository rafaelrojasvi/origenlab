"""Scan emails and rebuild ``contact_master`` / ``organization_master``."""

from __future__ import annotations

import json
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


class EmailMartFeaturesEmptyError(RuntimeError):
    """Feature scan requested but ``email_mart_features`` has no rows."""


def fetch_full_body_clean_for_email(conn: sqlite3.Connection, email_id: int) -> str:
    row = conn.execute(
        "SELECT COALESCE(full_body_clean,'') FROM emails WHERE id = ?",
        (int(email_id),),
    ).fetchone()
    return str(row[0]) if row else ""


def _parse_feature_json_array(raw: str | None) -> tuple[list[str], bool]:
    """Parse a JSON string list from feature columns; invalid JSON → empty + invalid flag."""
    if not raw:
        return [], False
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return [], True
    if not isinstance(val, list):
        return [], True
    return [str(x) for x in val], False


def _rollup_contact_target(
    contact: ContactMap,
    *,
    target_email: str,
    inbound: bool,
    outbound: bool,
    is_quote_email: bool,
    is_invoice_email: bool,
    is_purchase_email: bool,
    has_business_doc: bool,
    quote_doc: int,
    invoice_doc: int,
    equipment_tags: list[str],
    mart_date_iso: str | None,
) -> None:
    d = domain_of(target_email) or ""
    if not d:
        return
    row = contact[target_email]
    row["domain"] = d
    row["org_name"] = guess_org_name_from_domain(d)
    row["org_type"] = guess_org_type_from_domain(d)
    row["total"] += 1
    row["inbound"] += 1 if inbound else 0
    row["outbound"] += 1 if outbound else 0
    row["quote_email"] += 1 if is_quote_email else 0
    row["invoice_email"] += 1 if is_invoice_email else 0
    row["purchase_email"] += 1 if is_purchase_email else 0
    row["business_doc_email"] += 1 if has_business_doc else 0
    row["quote_doc"] += quote_doc
    row["invoice_doc"] += invoice_doc
    for tag in equipment_tags:
        row["equip"][tag] += 1
    if mart_date_iso:
        if row["first_seen_at"] is None or mart_date_iso < row["first_seen_at"]:
            row["first_seen_at"] = mart_date_iso
        if row["last_seen_at"] is None or mart_date_iso > row["last_seen_at"]:
            row["last_seen_at"] = mart_date_iso


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
    mart_scan_body_seconds = 0.0
    mart_scan_noise_seconds = 0.0
    mart_scan_address_parse_seconds = 0.0
    mart_scan_intent_seconds = 0.0
    mart_scan_equipment_seconds = 0.0
    mart_scan_doc_lookup_seconds = 0.0
    mart_scan_target_build_seconds = 0.0
    mart_scan_contact_update_seconds = 0.0
    mart_scan_date_seconds = 0.0
    body_total_chars = 0
    body_max_chars = 0
    body_rows_gt_2k = 0
    body_rows_gt_5k = 0
    body_rows_gt_10k = 0
    body_rows_gt_50k = 0
    mart_scan_fetchmany_seconds = 0.0
    mart_scan_loop_total_seconds = 0.0
    mart_scan_batches = 0
    mart_target_candidate_rows = 0
    mart_no_target_rows = 0
    mart_target_candidate_body_chars = 0
    mart_no_target_body_chars = 0
    mart_target_candidate_rows_gt_2k = 0
    mart_no_target_rows_gt_2k = 0
    mart_target_candidate_rows_gt_10k = 0
    mart_no_target_rows_gt_10k = 0
    mart_pre_noise_target_preview_seconds = 0.0
    mart_pre_noise_target_candidate_rows = 0
    mart_pre_noise_no_target_rows = 0
    mart_pre_noise_target_candidate_body_chars = 0
    mart_pre_noise_no_target_body_chars = 0
    mart_pre_noise_target_candidate_rows_gt_2k = 0
    mart_pre_noise_no_target_rows_gt_2k = 0
    mart_pre_noise_target_candidate_rows_gt_10k = 0
    mart_pre_noise_no_target_rows_gt_10k = 0
    batch_size = 5000
    fetch_t0 = time.monotonic()
    batch = cur.fetchmany(batch_size)
    mart_scan_fetchmany_seconds += time.monotonic() - fetch_t0
    mart_scan_batches += 1
    internal_domains = set(options.internal_domains)
    mart_slack = options.mart_date_slack_days
    while batch:
        for email_id, sender, recipients, subject, top, date_iso in batch:
            row_t0 = time.monotonic()
            n += 1
            body_t0 = time.monotonic()
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
            mart_scan_body_seconds += time.monotonic() - body_t0

            body_len = len(body)
            body_total_chars += body_len
            if body_len > body_max_chars:
                body_max_chars = body_len
            if body_len > 2000:
                body_rows_gt_2k += 1
            if body_len > 5000:
                body_rows_gt_5k += 1
            if body_len > 10000:
                body_rows_gt_10k += 1
            if body_len > 50000:
                body_rows_gt_50k += 1

            if options.limit_emails and n > options.limit_emails:
                mart_scan_loop_total_seconds += time.monotonic() - row_t0
                batch = []
                break
            sender_s = sender or ""
            subj = subject or ""

            preview_t0 = time.monotonic()
            preview_sender_email = primary_sender_email(sender_s)
            preview_sender_dom = domain_of(preview_sender_email) or ""
            preview_recip_emails = emails_in(recipients or "")
            preview_outbound = preview_sender_dom in internal_domains
            preview_inbound = bool(preview_sender_dom) and not preview_outbound
            preview_targets: list[str] = []
            if preview_outbound:
                for e in preview_recip_emails:
                    d = domain_of(e) or ""
                    if d and d not in internal_domains:
                        preview_targets.append(e)
            elif preview_inbound and preview_sender_email:
                if preview_sender_dom and preview_sender_dom not in internal_domains:
                    preview_targets.append(preview_sender_email)
            mart_pre_noise_target_preview_seconds += time.monotonic() - preview_t0

            if preview_targets:
                mart_pre_noise_target_candidate_rows += 1
                mart_pre_noise_target_candidate_body_chars += body_len
                if body_len > 2000:
                    mart_pre_noise_target_candidate_rows_gt_2k += 1
                if body_len > 10000:
                    mart_pre_noise_target_candidate_rows_gt_10k += 1
            else:
                mart_pre_noise_no_target_rows += 1
                mart_pre_noise_no_target_body_chars += body_len
                if body_len > 2000:
                    mart_pre_noise_no_target_rows_gt_2k += 1
                if body_len > 10000:
                    mart_pre_noise_no_target_rows_gt_10k += 1

            noise_t0 = time.monotonic()
            if is_noise_sender(sender_s, subj, body):
                mart_scan_noise_seconds += time.monotonic() - noise_t0
                mart_scan_loop_total_seconds += time.monotonic() - row_t0
                continue
            mart_scan_noise_seconds += time.monotonic() - noise_t0

            addr_t0 = time.monotonic()
            sender_email = primary_sender_email(sender_s)
            sender_dom = domain_of(sender_email) or ""
            recip_emails = emails_in(recipients or "")
            mart_scan_address_parse_seconds += time.monotonic() - addr_t0

            intent_t0 = time.monotonic()
            intents = classify_email_intents(subj, body)
            mart_scan_intent_seconds += time.monotonic() - intent_t0

            equip_t0 = time.monotonic()
            equip = equipment_tags_from_text(subj + "\n" + body)
            mart_scan_equipment_seconds += time.monotonic() - equip_t0

            doc_t0 = time.monotonic()
            has_business_doc = int(email_id) in doc_aggs.business_doc_email_ids
            dt_counts = doc_aggs.doc_counts_by_email.get(int(email_id), Counter())
            mart_scan_doc_lookup_seconds += time.monotonic() - doc_t0

            outbound = sender_dom in internal_domains
            inbound = bool(sender_dom) and not outbound

            target_t0 = time.monotonic()
            targets: list[str] = []
            if outbound:
                for e in recip_emails:
                    d = domain_of(e) or ""
                    if d and d not in internal_domains:
                        targets.append(e)
            elif inbound and sender_email:
                if sender_dom and sender_dom not in internal_domains:
                    targets.append(sender_email)
            mart_scan_target_build_seconds += time.monotonic() - target_t0

            if targets:
                mart_target_candidate_rows += 1
                mart_target_candidate_body_chars += body_len
                if body_len > 2000:
                    mart_target_candidate_rows_gt_2k += 1
                if body_len > 10000:
                    mart_target_candidate_rows_gt_10k += 1
            else:
                mart_no_target_rows += 1
                mart_no_target_body_chars += body_len
                if body_len > 2000:
                    mart_no_target_rows_gt_2k += 1
                if body_len > 10000:
                    mart_no_target_rows_gt_10k += 1

            for e in targets:
                d = domain_of(e) or ""
                if not d:
                    continue
                row = contact[e]

                update_t0 = time.monotonic()
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
                mart_scan_contact_update_seconds += time.monotonic() - update_t0

                date_t0 = time.monotonic()
                d_iso = email_date_iso_for_mart_timeline(date_iso, slack_days=mart_slack)
                if d_iso:
                    if row["first_seen_at"] is None or d_iso < row["first_seen_at"]:
                        row["first_seen_at"] = d_iso
                    if row["last_seen_at"] is None or d_iso > row["last_seen_at"]:
                        row["last_seen_at"] = d_iso
                mart_scan_date_seconds += time.monotonic() - date_t0

            mart_scan_loop_total_seconds += time.monotonic() - row_t0

        fetch_t0 = time.monotonic()
        batch = cur.fetchmany(batch_size)
        mart_scan_fetchmany_seconds += time.monotonic() - fetch_t0
        mart_scan_batches += 1

    email_scan_seconds = time.monotonic() - stage_t0
    mart_scan_measured_stage_seconds = (
        mart_scan_body_seconds
        + mart_scan_noise_seconds
        + mart_scan_address_parse_seconds
        + mart_scan_intent_seconds
        + mart_scan_equipment_seconds
        + mart_scan_doc_lookup_seconds
        + mart_scan_target_build_seconds
        + mart_scan_contact_update_seconds
        + mart_scan_date_seconds
    )
    mart_scan_unattributed_seconds = (
        email_scan_seconds
        - mart_scan_fetchmany_seconds
        - mart_scan_measured_stage_seconds
    )

    print(f"Scanned emails (for mart): {n:,}")
    print(f"[timing] email_scan_seconds={email_scan_seconds:.2f}")
    print(f"[mart-profile] top_reply_nonempty_rows={top_reply_nonempty_rows}")
    print(f"[mart-profile] top_reply_empty_rows={top_reply_empty_rows}")
    print(f"[mart-profile] full_body_fallback_used_rows={full_body_fallback_used_rows}")
    print(f"[mart-profile] top_reply_total_chars={top_reply_total_chars}")
    print(f"[mart-profile] full_body_fallback_total_chars={full_body_fallback_total_chars}")
    print(f"[mart-profile] full_body_lazy_fetches={full_body_lazy_fetches}")
    print(f"[timing] full_body_lazy_fetch_seconds={full_body_lazy_fetch_seconds:.2f}")
    print(f"[timing] mart_scan_body_seconds={mart_scan_body_seconds:.2f}")
    print(f"[timing] mart_scan_noise_seconds={mart_scan_noise_seconds:.2f}")
    print(f"[timing] mart_scan_address_parse_seconds={mart_scan_address_parse_seconds:.2f}")
    print(f"[timing] mart_scan_intent_seconds={mart_scan_intent_seconds:.2f}")
    print(f"[timing] mart_scan_equipment_seconds={mart_scan_equipment_seconds:.2f}")
    print(f"[timing] mart_scan_doc_lookup_seconds={mart_scan_doc_lookup_seconds:.2f}")
    print(f"[timing] mart_scan_target_build_seconds={mart_scan_target_build_seconds:.2f}")
    print(f"[timing] mart_scan_contact_update_seconds={mart_scan_contact_update_seconds:.2f}")
    print(f"[timing] mart_scan_date_seconds={mart_scan_date_seconds:.2f}")
    print(f"[mart-profile] body_total_chars={body_total_chars}")
    print(f"[mart-profile] body_max_chars={body_max_chars}")
    print(f"[mart-profile] body_rows_gt_2k={body_rows_gt_2k}")
    print(f"[mart-profile] body_rows_gt_5k={body_rows_gt_5k}")
    print(f"[mart-profile] body_rows_gt_10k={body_rows_gt_10k}")
    print(f"[mart-profile] body_rows_gt_50k={body_rows_gt_50k}")
    print(f"[timing] mart_scan_fetchmany_seconds={mart_scan_fetchmany_seconds:.2f}")
    print(f"[timing] mart_scan_measured_stage_seconds={mart_scan_measured_stage_seconds:.2f}")
    print(f"[timing] mart_scan_unattributed_seconds={mart_scan_unattributed_seconds:.2f}")
    print(f"[mart-profile] mart_scan_batches={mart_scan_batches}")
    print(f"[mart-profile] mart_scan_batch_size={batch_size}")
    print(f"[mart-profile] mart_target_candidate_rows={mart_target_candidate_rows}")
    print(f"[mart-profile] mart_no_target_rows={mart_no_target_rows}")
    print(f"[mart-profile] mart_target_candidate_body_chars={mart_target_candidate_body_chars}")
    print(f"[mart-profile] mart_no_target_body_chars={mart_no_target_body_chars}")
    print(f"[mart-profile] mart_target_candidate_rows_gt_2k={mart_target_candidate_rows_gt_2k}")
    print(f"[mart-profile] mart_no_target_rows_gt_2k={mart_no_target_rows_gt_2k}")
    print(f"[mart-profile] mart_target_candidate_rows_gt_10k={mart_target_candidate_rows_gt_10k}")
    print(f"[mart-profile] mart_no_target_rows_gt_10k={mart_no_target_rows_gt_10k}")
    print(f"[mart-profile] mart_pre_noise_target_candidate_rows={mart_pre_noise_target_candidate_rows}")
    print(f"[mart-profile] mart_pre_noise_no_target_rows={mart_pre_noise_no_target_rows}")
    print(
        f"[mart-profile] mart_pre_noise_target_candidate_body_chars="
        f"{mart_pre_noise_target_candidate_body_chars}"
    )
    print(f"[mart-profile] mart_pre_noise_no_target_body_chars={mart_pre_noise_no_target_body_chars}")
    print(
        f"[mart-profile] mart_pre_noise_target_candidate_rows_gt_2k="
        f"{mart_pre_noise_target_candidate_rows_gt_2k}"
    )
    print(f"[mart-profile] mart_pre_noise_no_target_rows_gt_2k={mart_pre_noise_no_target_rows_gt_2k}")
    print(
        f"[mart-profile] mart_pre_noise_target_candidate_rows_gt_10k="
        f"{mart_pre_noise_target_candidate_rows_gt_10k}"
    )
    print(f"[mart-profile] mart_pre_noise_no_target_rows_gt_10k={mart_pre_noise_no_target_rows_gt_10k}")
    print(f"[timing] mart_pre_noise_target_preview_seconds={mart_pre_noise_target_preview_seconds:.2f}")
    return dict(contact), n


def scan_email_contacts_from_features(
    conn: sqlite3.Connection,
    *,
    options: MartBuildOptions,
    doc_aggs: DocAgg,
) -> tuple[ContactMap, int]:
    """Scan ``email_mart_features`` and aggregate external contact rollups (in-memory)."""
    feature_count = int(conn.execute("SELECT COUNT(*) FROM email_mart_features").fetchone()[0])
    if feature_count == 0:
        raise EmailMartFeaturesEmptyError(
            "email_mart_features is empty; run build-email-mart-features --apply first"
        )

    contact: ContactMap = defaultdict(_new_contact_row)
    stage_t0 = time.monotonic()

    use_email_join = options.since_days is not None
    join_sql = " JOIN emails e ON e.id = f.email_id" if use_email_join else ""
    sql = (
        "SELECT f.email_id, f.external_targets_json, f.direction, f.is_noise, "
        "f.is_quote_email, f.is_invoice_email, f.is_purchase_email, "
        "f.equipment_tags_json, f.mart_date_iso, f.body_len "
        f"FROM email_mart_features f{join_sql}"
    )
    where_clauses: list[str] = []
    params: list[object] = []
    if options.canonical_only or options.dashboard_fast:
        where_clauses.append(
            sql_predicate_contacto_gmail_source(table_alias="f", coalesce_null=False)
        )
    if options.since_days is not None:
        days = max(1, min(int(options.since_days), 3650))
        where_clauses.append("substr(COALESCE(e.date_iso,''),1,10) >= date('now', ?)")
        params.append(f"-{days} day")
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)
    sql += " ORDER BY f.email_id"

    cur = conn.execute(sql, params)
    batch_size = 5000
    n = 0
    feature_noise_rows = 0
    feature_invalid_json_rows = 0
    feature_total_targets = 0
    feature_rows_with_targets = 0
    body_total_chars = 0

    while True:
        batch = cur.fetchmany(batch_size)
        if not batch:
            break
        for (
            email_id,
            external_targets_json,
            direction,
            is_noise,
            is_quote_email,
            is_invoice_email,
            is_purchase_email,
            equipment_tags_json,
            mart_date_iso,
            body_len,
        ) in batch:
            n += 1
            body_total_chars += int(body_len or 0)

            if options.limit_emails and n > options.limit_emails:
                batch = []
                break

            if int(is_noise or 0):
                feature_noise_rows += 1
                continue

            targets, targets_invalid = _parse_feature_json_array(external_targets_json)
            equip_tags, equip_invalid = _parse_feature_json_array(equipment_tags_json)
            if targets_invalid or equip_invalid:
                feature_invalid_json_rows += 1

            inbound = direction == "inbound"
            outbound = direction == "outbound"
            has_business_doc = int(email_id) in doc_aggs.business_doc_email_ids
            dt_counts = doc_aggs.doc_counts_by_email.get(int(email_id), Counter())
            quote_doc = int(dt_counts.get("quote", 0))
            invoice_doc = int(dt_counts.get("invoice", 0))

            if targets:
                feature_rows_with_targets += 1
            feature_total_targets += len(targets)

            for target_email in targets:
                _rollup_contact_target(
                    contact,
                    target_email=target_email,
                    inbound=inbound,
                    outbound=outbound,
                    is_quote_email=bool(int(is_quote_email or 0)),
                    is_invoice_email=bool(int(is_invoice_email or 0)),
                    is_purchase_email=bool(int(is_purchase_email or 0)),
                    has_business_doc=has_business_doc,
                    quote_doc=quote_doc,
                    invoice_doc=invoice_doc,
                    equipment_tags=equip_tags,
                    mart_date_iso=mart_date_iso,
                )

    email_feature_scan_seconds = time.monotonic() - stage_t0
    print(f"Scanned email mart features: {n:,}")
    print(f"[timing] email_feature_scan_seconds={email_feature_scan_seconds:.2f}")
    print(f"[mart-profile] feature_noise_rows={feature_noise_rows}")
    print(f"[mart-profile] feature_invalid_json_rows={feature_invalid_json_rows}")
    print(f"[mart-profile] feature_total_targets={feature_total_targets}")
    print(f"[mart-profile] feature_rows_with_targets={feature_rows_with_targets}")
    print(f"[mart-profile] body_total_chars={body_total_chars}")
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


def build_organization_map(contact: ContactMap) -> OrgMap:
    """Aggregate organization rollups from a contact map (in-memory only)."""
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
    return dict(org)


def rebuild_organization_master(conn: sqlite3.Connection, contact: ContactMap) -> OrgMap:
    stage_t0 = time.monotonic()
    org = build_organization_map(contact)

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
