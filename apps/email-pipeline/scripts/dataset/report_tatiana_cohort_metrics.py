#!/usr/bin/env python3
"""SQLite metrics for voice / drafting cohort (LabDelivery domain and/or address allowlist)."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.business_mart import is_noise_sender
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.email_business_filters import classify_email
from origenlab_email_pipeline.progress import iter_sqlite_email_batches_with_progress
from origenlab_email_pipeline.tatiana_voice_cohort import (
    default_allowlist_path,
    default_voice_domains_path,
    hybrid_style_body,
    is_voice_candidate_row,
    load_tatiana_allowlist,
    load_voice_sender_domains,
    subject_is_reply_or_forward,
    trusted_domains_for_identity_mentions,
)


def _year(date_iso: str | None) -> str:
    if not date_iso or len(date_iso) < 4:
        return "(unknown)"
    return date_iso[:4]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--min-len-top",
        type=int,
        default=0,
        help="only count rows with length(trim(top_reply_clean)) >= this (0 = no filter)",
    )
    ap.add_argument(
        "--min-len-hybrid",
        type=int,
        default=0,
        help="only count rows with length(hybrid_style_body(full, top)) >= this",
    )
    ap.add_argument(
        "--exclude-noise",
        action="store_true",
        help="exclude rows that match is_noise_sender (mart-style noise)",
    )
    ap.add_argument(
        "--allow-shared-mailboxes",
        action="store_true",
        help="include role mailboxes if they appear on the allowlist",
    )
    ap.add_argument(
        "--no-voice-domains",
        action="store_true",
        help="do not use sender-domain cohort (config/voice_sender_domains*.txt / env); address allowlist required",
    )
    ap.add_argument(
        "--include-tatiana-text-signals",
        action="store_true",
        help="also include trusted-domain mail where From line or full_body_clean/top_reply_clean "
        "contains whole-word Tatiana or Vivanco (signatures / display names)",
    )
    args = ap.parse_args()

    allowlist = load_tatiana_allowlist()
    voice_domains = frozenset() if args.no_voice_domains else load_voice_sender_domains()
    if (
        not allowlist
        and not voice_domains
        and not args.include_tatiana_text_signals
    ):
        print(
            "No cohort definition: configure sender domains (see "
            f"{default_voice_domains_path()}) and/or an address allowlist "
            f"({default_allowlist_path()}), or run with --include-tatiana-text-signals, "
            "or audit the DB: scripts/dataset/audit_tatiana_identity_signals.py",
            file=sys.stderr,
        )
        sys.exit(2)

    trusted_mention = trusted_domains_for_identity_mentions(voice_domains)
    settings = load_settings()
    db_path = settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT id, message_id, sender, subject, folder, date_iso,
               COALESCE(full_body_clean, '') AS full_body_clean,
               COALESCE(top_reply_clean, '') AS top_reply_clean
        FROM emails
        """
    )

    total_scanned = 0
    cohort_raw = 0
    cohort_after_filters = 0
    msg_ids: list[str | None] = []
    years = Counter()
    len_top_buckets = Counter()
    len_hybrid_buckets = Counter()
    primary_cat = Counter()
    nonempty_top = 0
    nonempty_full = 0
    nonempty_hybrid = 0
    reply_subj = 0

    for batch in iter_sqlite_email_batches_with_progress(
        conn, cur, desc="Voice cohort metrics"
    ):
        for row in batch:
            total_scanned += 1
            sender = row["sender"]
            full = row["full_body_clean"] or ""
            top = row["top_reply_clean"] or ""
            if not is_voice_candidate_row(
                sender,
                allowlist,
                voice_domains=voice_domains,
                full_body_clean=full,
                top_reply_clean=top,
                include_tatiana_text_signals=args.include_tatiana_text_signals,
                trusted_domains_for_text_signals=trusted_mention,
                allow_shared_mailboxes=args.allow_shared_mailboxes,
            ):
                continue
            cohort_raw += 1

            subj = row["subject"] or ""
            body_for_noise = top or full
            if args.exclude_noise and is_noise_sender(sender or "", subj, body_for_noise):
                continue

            lt, lf = len(top.strip()), len(full.strip())
            hybrid = hybrid_style_body(full, top)
            lh = len(hybrid.strip())

            if args.min_len_top and lt < args.min_len_top:
                continue
            if args.min_len_hybrid and lh < args.min_len_hybrid:
                continue

            cohort_after_filters += 1
            msg_ids.append(row["message_id"])
            years[_year(row["date_iso"])] += 1
            if lt > 0:
                nonempty_top += 1
            if lf > 0:
                nonempty_full += 1
            if lh > 0:
                nonempty_hybrid += 1
            if subject_is_reply_or_forward(subj):
                reply_subj += 1

            if lt < 200:
                len_top_buckets["lt_200"] += 1
            elif lt < 400:
                len_top_buckets["200_399"] += 1
            else:
                len_top_buckets["ge_400"] += 1

            if lh < 200:
                len_hybrid_buckets["lt_200"] += 1
            elif lh < 400:
                len_hybrid_buckets["200_399"] += 1
            else:
                len_hybrid_buckets["ge_400"] += 1

            cls = classify_email(sender=sender, subject=subj, body=body_for_noise)
            primary_cat[cls.get("primary_category", "?")] += 1

    mids_nonempty = [m.strip() for m in msg_ids if m and str(m).strip()]
    mid_counter = Counter(mids_nonempty)
    mids_with_duplicates = sum(1 for c in mid_counter.values() if c > 1)
    duplicate_extra_rows = sum(c - 1 for c in mid_counter.values() if c > 1)
    null_mid = sum(1 for m in msg_ids if not (m or "").strip())

    print(f"DB: {db_path}")
    print(f"Address allowlist size: {len(allowlist)}")
    print(f"Voice sender domains: {sorted(voice_domains) if voice_domains else '(none)'}")
    print(f"Include Tatiana/Vivanco text signals (trusted From + body/From line): {args.include_tatiana_text_signals}")
    print(f"Emails scanned: {total_scanned:,}")
    print(f"Cohort (domain and/or allowlist, shared-mailbox policy): {cohort_raw:,}")
    print(f"Cohort after length/noise filters: {cohort_after_filters:,}")
    print(f"  non-empty top_reply_clean: {nonempty_top:,}")
    print(f"  non-empty full_body_clean: {nonempty_full:,}")
    print(f"  non-empty hybrid_style_body: {nonempty_hybrid:,}")
    print(f"  subject Re:/Fwd: (heuristic): {reply_subj:,}")
    print(f"Message-ID null/empty in cohort: {null_mid:,}")
    print(f"Distinct non-empty Message-IDs: {len(mid_counter):,}")
    print(f"Message-ID values with duplicates: {mids_with_duplicates:,}")
    print(f"Extra rows from Message-ID duplicates (total rows - unique IDs): {duplicate_extra_rows:,}")
    print("Year distribution (date_iso prefix):")
    for y in sorted(years.keys()):
        print(f"  {y}: {years[y]:,}")
    print("top_reply_clean length buckets (cohort after filters):")
    for k in ("lt_200", "200_399", "ge_400"):
        print(f"  {k}: {len_top_buckets[k]:,}")
    print("hybrid_style_body length buckets:")
    for k in ("lt_200", "200_399", "ge_400"):
        print(f"  {k}: {len_hybrid_buckets[k]:,}")
    print("classify_email primary_category (noise body = top or full):")
    for cat, c in primary_cat.most_common():
        print(f"  {cat}: {c:,}")


if __name__ == "__main__":
    main()
