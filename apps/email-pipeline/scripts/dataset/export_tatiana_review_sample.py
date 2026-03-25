#!/usr/bin/env python3
"""Export a stratified CSV for manual labeling (LabDelivery / voice cohort QA)."""

from __future__ import annotations

import argparse
import csv
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.business_mart import is_noise_sender
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.progress import iter_sqlite_email_batches_with_progress
from origenlab_email_pipeline.tatiana_voice_cohort import (
    bucket_body_length,
    default_allowlist_path,
    default_voice_domains_path,
    hybrid_style_body,
    is_voice_candidate_row,
    load_tatiana_allowlist,
    load_voice_sender_domains,
    subject_is_reply_or_forward,
    trusted_domains_for_identity_mentions,
)

# Manual review columns (empty until filled by a human reviewer).
REVIEW_COLUMNS = [
    "label_author_confidence",  # high / medium / low / not_tatiana
    "label_commercial_marketing",  # y/n
    "label_operational",  # y/n
    "label_mostly_quoted_or_forward",  # y/n
    "label_third_party_template",  # y/n
    "notes",
]


def _preview(text: str, max_len: int = 500) -> str:
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = " ".join(t.split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--per-bucket", type=int, default=10, help="target rows per stratification bucket")
    ap.add_argument("--min-len-top", type=int, default=0)
    ap.add_argument("--exclude-noise", action="store_true")
    ap.add_argument("--allow-shared-mailboxes", action="store_true")
    ap.add_argument(
        "--no-voice-domains",
        action="store_true",
        help="address allowlist only; ignore config/voice_sender_domains*.txt and env domains",
    )
    ap.add_argument(
        "--include-tatiana-text-signals",
        action="store_true",
        help="also include trusted-domain mail with whole-word Tatiana/Vivanco in From or clean body",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="CSV path (default: reports/out/tatiana_review_sample_<ts>.csv)",
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
            "No cohort definition: configure "
            f"{default_voice_domains_path()} and/or an address allowlist "
            f"({default_allowlist_path()}), or use --include-tatiana-text-signals, "
            "or audit: scripts/dataset/audit_tatiana_identity_signals.py",
            file=sys.stderr,
        )
        sys.exit(2)

    trusted_mention = trusted_domains_for_identity_mentions(voice_domains)
    settings = load_settings()
    db_path = settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    rng = random.Random(args.seed)

    # bucket key: (length_bucket, reply_flag) -> list of row dicts
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)

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

    for batch in iter_sqlite_email_batches_with_progress(
        conn, cur, desc="Build review strata"
    ):
        for row in batch:
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
            subj = row["subject"] or ""
            body_for_noise = top or full
            if args.exclude_noise and is_noise_sender(sender or "", subj, body_for_noise):
                continue
            lt = len(top.strip())
            if args.min_len_top and lt < args.min_len_top:
                continue

            hybrid = hybrid_style_body(full, top)
            lb = bucket_body_length(len(hybrid.strip()))
            rf = "re_or_fwd" if subject_is_reply_or_forward(subj) else "no_re_fwd"
            key = (lb, rf)
            buckets[key].append(
                {
                    "id": row["id"],
                    "message_id": row["message_id"] or "",
                    "date_iso": row["date_iso"] or "",
                    "sender": sender or "",
                    "subject": subj,
                    "folder": row["folder"] or "",
                    "len_top_reply_clean": lt,
                    "len_full_body_clean": len(full.strip()),
                    "len_hybrid_style_body": len(hybrid.strip()),
                    "top_reply_clean_preview": _preview(top),
                    "full_body_clean_preview": _preview(full),
                    "hybrid_style_body_preview": _preview(hybrid),
                }
            )

    out_rows: list[dict] = []
    for key, rows in buckets.items():
        rng.shuffle(rows)
        take = rows[: args.per_bucket]
        for r in take:
            r["stratum"] = f"{key[0]}|{key[1]}"
            out_rows.append(r)

    if not out_rows:
        print("No rows matched filters; widen criteria or check allowlist.", file=sys.stderr)
        sys.exit(1)

    rng.shuffle(out_rows)
    out_path = args.output
    if out_path is None:
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = settings.resolved_reports_dir() / f"tatiana_review_sample_{ts}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "id",
        "message_id",
        "date_iso",
        "sender",
        "subject",
        "folder",
        "stratum",
        "len_top_reply_clean",
        "len_full_body_clean",
        "len_hybrid_style_body",
        "top_reply_clean_preview",
        "full_body_clean_preview",
        "hybrid_style_body_preview",
    ] + REVIEW_COLUMNS

    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in out_rows:
            row = {k: r.get(k, "") for k in fieldnames}
            for col in REVIEW_COLUMNS:
                row[col] = ""
            w.writerow(row)

    print(f"Wrote {len(out_rows)} rows to {out_path}")
    print("Fill review columns manually (UTF-8 CSV).")


if __name__ == "__main__":
    main()
