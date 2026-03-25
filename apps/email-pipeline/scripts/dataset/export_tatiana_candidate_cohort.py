#!/usr/bin/env python3
"""
Export the Tatiana **candidate writing** cohort to CSV (+ JSON summary) for manual review.

This is the primary reviewable dataset for style / phrase work — not strict SQL `voice`
From-domain sampling (see docs/dataset/TATIANA_REVIEW_COHORT.md).

Requires cohort configuration (allowlist and/or voice domains), same as other Tatiana scripts.

Use `--target-use-case marketing` (or `--prefer-marketing`) for a marketing / intro / prospecting-first
sort: same inclusion filters and `review_quality_score`, but reorder with `marketing_rank_*` columns
and demotions for payment, logistics, and supplier-coordination prose (see TATIANA_REVIEW_COHORT.md).
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.business_mart import is_noise_sender, primary_sender_email
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.progress import iter_sqlite_email_batches_with_progress
from origenlab_email_pipeline.tatiana_review_cohort import (
    TATIANA_CANDIDATE_COHORT_VERSION,
    build_review_signals,
    cohort_export_dedup_key,
    compute_marketing_export_rank_meta,
)
from origenlab_email_pipeline.tatiana_voice_cohort import (
    default_allowlist_path,
    default_voice_domains_path,
    hybrid_style_body,
    is_voice_candidate_row,
    load_tatiana_allowlist,
    load_voice_sender_domains,
    trusted_domains_for_identity_mentions,
)

REVIEW_COLUMNS = [
    "label_author_confidence",
    "label_useful_writing_example",
    "label_mostly_third_party_text",
    "notes",
]


def _y(v: bool) -> str:
    return "y" if v else "n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exclude-noise", action="store_true", help="drop is_noise_sender rows")
    ap.add_argument("--allow-shared-mailboxes", action="store_true")
    ap.add_argument(
        "--no-voice-domains",
        action="store_true",
        help="address allowlist only unless --include-tatiana-text-signals",
    )
    ap.add_argument("--include-tatiana-text-signals", action="store_true")
    ap.add_argument(
        "--min-len-hybrid",
        type=int,
        default=120,
        help="minimum characters in hybrid_style_body (default 120)",
    )
    ap.add_argument(
        "--max-rows",
        type=int,
        default=0,
        help="cap exported rows after sort (0 = no cap)",
    )
    ap.add_argument(
        "--high-confidence-min-score",
        type=float,
        default=62.0,
        help="summary threshold for high_confidence_count",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="CSV path (default: reports/out/tatiana_candidate_cohort_<ts>.csv)",
    )
    ap.add_argument(
        "--target-use-case",
        choices=("general", "marketing"),
        default="general",
        help="marketing = payment/logistics demotion + tie-break columns; general = unchanged ranking",
    )
    ap.add_argument(
        "--prefer-marketing",
        action="store_true",
        help="same as --target-use-case marketing",
    )
    args = ap.parse_args()
    use_marketing = args.target_use_case == "marketing" or args.prefer_marketing

    allowlist = load_tatiana_allowlist()
    voice_domains = frozenset() if args.no_voice_domains else load_voice_sender_domains()
    if not allowlist and not voice_domains and not args.include_tatiana_text_signals:
        print(
            "No cohort definition: configure "
            f"{default_voice_domains_path()} and/or "
            f"{default_allowlist_path()}, or pass --include-tatiana-text-signals.",
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
        SELECT id, message_id, sender, recipients, subject, folder, date_iso,
               COALESCE(full_body_clean, '') AS full_body_clean,
               COALESCE(top_reply_clean, '') AS top_reply_clean
        FROM emails
        """
    )

    rows_out: list[dict[str, str | float | int]] = []
    total_scanned = 0
    cohort_in = 0
    dropped_short = 0
    dropped_noise = 0

    for batch in iter_sqlite_email_batches_with_progress(conn, cur, desc="Candidate cohort"):
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
            cohort_in += 1
            subj = row["subject"] or ""
            hybrid = hybrid_style_body(full, top)
            if args.exclude_noise and is_noise_sender(sender, subj, top or full):
                dropped_noise += 1
                continue
            lh = len(hybrid.strip())
            if lh < args.min_len_hybrid:
                dropped_short += 1
                continue

            sig = build_review_signals(
                sender=sender or "",
                recipients=row["recipients"],
                subject=subj,
                full_body_clean=full,
                top_reply_clean=top,
                hybrid_body=hybrid,
                allowlist=allowlist,
                voice_domains=voice_domains,
                trusted_mention_domains=trusted_mention,
                include_tatiana_text_signals=args.include_tatiana_text_signals,
            )
            primary_pe = primary_sender_email(sender or "") or ""

            rows_out.append(
                {
                    "id": row["id"],
                    "message_id": (row["message_id"] or "").strip(),
                    "date_iso": row["date_iso"] or "",
                    "sender": sender or "",
                    "recipients": (row["recipients"] or "").strip(),
                    "subject": subj,
                    "folder": row["folder"] or "",
                    "body_for_review": hybrid,
                    "body_field": "hybrid_style_body",
                    "len_body_for_review": lh,
                    "len_top_reply_clean": len(top.strip()),
                    "len_full_body_clean": len(full.strip()),
                    "primary_sender_email": primary_pe,
                    "inclusion_reasons": ";".join(sig.inclusion_reasons),
                    "identity_tatiana_header": _y(sig.identity_mention_in_header),
                    "identity_tatiana_body_not_header": _y(sig.identity_mention_in_body_only),
                    "likely_outbound_external": _y(sig.likely_outbound_to_external),
                    "risk_flags": ";".join(sig.risk_flags),
                    "quote_line_ratio_full_body": sig.quote_line_ratio_full,
                    "heavy_reply_tail": _y(sig.heavy_reply_tail),
                    "trivial_one_liner": _y(sig.trivial_one_liner),
                    "intent_primary_category": sig.intent_primary,
                    "intent_commercial_subtype": sig.commercial_subtype,
                    "intent_quote": _y(sig.intent_quote),
                    "intent_invoice": _y(sig.intent_invoice),
                    "intent_purchase": _y(sig.intent_purchase),
                    "review_quality_score": sig.score,
                }
            )
            if use_marketing:
                mm = compute_marketing_export_rank_meta(
                    subject=subj,
                    hybrid_body=hybrid,
                    risk_flags=sig.risk_flags,
                    commercial_subtype=sig.commercial_subtype,
                    intent_quote=sig.intent_quote,
                    intent_invoice=sig.intent_invoice,
                    recipients=row["recipients"],
                    voice_domains=voice_domains,
                )
                entry = rows_out[-1]
                entry["_mk"] = mm
                entry["marketing_rank_delta"] = mm.rank_delta
                entry["marketing_export_tier"] = mm.export_tier
                entry["subject_reply_or_forward"] = _y(mm.subject_threaded)
                entry["marketing_rank_score"] = round(float(sig.score) + mm.rank_delta, 2)
                entry["marketing_rank_notes"] = ";".join(mm.notes)

    if not rows_out:
        print("No candidate rows after filters.", file=sys.stderr)
        sys.exit(1)

    if use_marketing:

        def _marketing_sort_key(r: dict) -> tuple:
            m = r["_mk"]
            c = float(r["review_quality_score"]) + m.rank_delta
            fresh = 0 if m.subject_threaded else 1
            return (
                c,
                m.export_tier,
                fresh,
                -m.ops_noise_hits,
                -m.hybrid_contam_flags,
                m.external_domain_count,
                m.body_len,
                int(r["id"]),
            )

        rows_out.sort(key=_marketing_sort_key, reverse=True)
    else:
        rows_out.sort(key=lambda r: (float(r["review_quality_score"]), int(r["id"])), reverse=True)

    for r in rows_out:
        r.pop("_mk", None)

    rows_before_dedup = len(rows_out)
    seen_dedup: set[str] = set()
    deduped: list[dict[str, str | float | int]] = []
    for r in rows_out:
        k = cohort_export_dedup_key(
            str(r.get("body_for_review", "")),
            str(r.get("subject", "")),
            str(r.get("date_iso", "")),
        )
        if k in seen_dedup:
            continue
        seen_dedup.add(k)
        deduped.append(r)
    rows_out = deduped
    dropped_duplicate = rows_before_dedup - len(rows_out)

    for i, r in enumerate(rows_out, start=1):
        r["review_priority_rank"] = i

    capped = False
    if args.max_rows and len(rows_out) > args.max_rows:
        rows_out = rows_out[: args.max_rows]
        capped = True

    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = args.output
    if out_csv is None:
        stem = (
            "tatiana_candidate_cohort_marketing"
            if use_marketing
            else "tatiana_candidate_cohort"
        )
        out_csv = settings.resolved_reports_dir() / f"{stem}_{ts}.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_json = out_csv.with_suffix("").resolve().as_posix() + "_summary.json"

    fieldnames = [
        "review_priority_rank",
        "id",
        "message_id",
        "date_iso",
        "sender",
        "recipients",
        "subject",
        "folder",
        "body_field",
        "len_body_for_review",
        "len_top_reply_clean",
        "len_full_body_clean",
        "primary_sender_email",
        "inclusion_reasons",
        "identity_tatiana_header",
        "identity_tatiana_body_not_header",
        "likely_outbound_external",
        "intent_primary_category",
        "intent_commercial_subtype",
        "intent_quote",
        "intent_invoice",
        "intent_purchase",
        "risk_flags",
        "quote_line_ratio_full_body",
        "heavy_reply_tail",
        "trivial_one_liner",
        "review_quality_score",
    ]
    if use_marketing:
        fieldnames.extend(
            [
                "marketing_rank_delta",
                "marketing_export_tier",
                "subject_reply_or_forward",
                "marketing_rank_score",
                "marketing_rank_notes",
            ]
        )
    fieldnames.append("body_for_review")
    fieldnames.extend(REVIEW_COLUMNS)

    for r in rows_out:
        for c in REVIEW_COLUMNS:
            r.setdefault(c, "")

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows_out:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    # --- Summary metrics ---
    hi_thr = float(args.high_confidence_min_score)
    high_conf = sum(1 for r in rows_out if float(r["review_quality_score"]) >= hi_thr)
    no_spoof = sum(1 for r in rows_out if "spoof_" not in str(r.get("risk_flags", "")))
    short_lt = sum(1 for r in rows_out if int(r["len_body_for_review"]) < 200)

    sender_dom = Counter()
    for r in rows_out:
        pe = (r.get("primary_sender_email") or "").lower()
        if "@" in pe:
            sender_dom[pe.split("@")[-1]] += 1

    primary_cat = Counter(str(r["intent_primary_category"]) for r in rows_out)
    risk_keys: Counter[str] = Counter()
    for r in rows_out:
        for part in str(r.get("risk_flags", "")).split(";"):
            p = part.strip()
            if p:
                risk_keys[p] += 1

    len_buckets = Counter()
    for r in rows_out:
        L = int(r["len_body_for_review"])
        if L < 120:
            len_buckets["lt_120"] += 1
        elif L < 250:
            len_buckets["120_249"] += 1
        elif L < 500:
            len_buckets["250_499"] += 1
        else:
            len_buckets["ge_500"] += 1

    summary = {
        "tatiana_candidate_cohort_version": TATIANA_CANDIDATE_COHORT_VERSION,
        "db_path": str(db_path),
        "exported_at": ts,
        "filters": {
            "exclude_noise": bool(args.exclude_noise),
            "allow_shared_mailboxes": bool(args.allow_shared_mailboxes),
            "no_voice_domains": bool(args.no_voice_domains),
            "include_tatiana_text_signals": bool(args.include_tatiana_text_signals),
            "min_len_hybrid": args.min_len_hybrid,
            "max_rows_cap": args.max_rows or None,
            "output_capped": capped,
            "target_use_case": "marketing" if use_marketing else "general",
        },
        "counts": {
            "emails_scanned": total_scanned,
            "cohort_voice_rules_matched": cohort_in,
            "dropped_noise": dropped_noise,
            "dropped_short_hybrid": dropped_short,
            "rows_before_exact_dedup": rows_before_dedup,
            "rows_dropped_duplicate_exact": dropped_duplicate,
            "exported_rows": len(rows_out),
            "high_confidence_rows_score_gte": high_conf,
            "high_confidence_threshold": hi_thr,
            "rows_without_spoof_risk_substring": no_spoof,
            "rows_hybrid_lt_200_chars": short_lt,
        },
        "top_primary_sender_domains": [
            {"domain": d, "count": c} for d, c in sender_dom.most_common(25)
        ],
        "hybrid_length_buckets": dict(len_buckets),
        "intent_primary_category_mix": dict(primary_cat),
        "top_risk_flags": [{"flag": k, "count": v} for k, v in risk_keys.most_common(25)],
    }

    Path(out_json).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {len(rows_out)} rows → {out_csv}")
    print(f"Summary → {out_json}")
    mode = "marketing" if use_marketing else "general"
    print(
        f"Exported {len(rows_out)} candidates ({mode}) | high-confidence (score>={hi_thr}): {high_conf} | "
        f"scanned={total_scanned:,} cohort_in={cohort_in:,} dropped_noise={dropped_noise} "
        f"dropped_short={dropped_short} dedup_dropped={dropped_duplicate}"
    )


if __name__ == "__main__":
    main()
