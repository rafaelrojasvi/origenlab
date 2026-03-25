#!/usr/bin/env python3
"""Scan emails.sqlite for Tatiana/Vivanco signals (headers + bodies) — discovery, not a label."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.business_mart import domain_of, primary_sender_email
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.progress import iter_sqlite_email_batches_with_progress
from origenlab_email_pipeline.tatiana_voice_cohort import (
    _RE_TATIANA,
    _RE_VIVANCO,
    load_voice_sender_domains,
    sender_domain_matches_voice_domains,
    trusted_domains_for_identity_mentions,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", type=int, default=8, help="examples per category (stdout)")
    args = ap.parse_args()

    settings = load_settings()
    db_path = settings.resolved_sqlite_path()
    if not db_path.is_file():
        print(f"SQLite DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    voice_domains = load_voice_sender_domains()
    trusted = trusted_domains_for_identity_mentions(voice_domains)

    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        """
        SELECT id, sender, subject,
               COALESCE(full_body_clean, '') AS full_body_clean,
               COALESCE(top_reply_clean, '') AS top_reply_clean
        FROM emails
        """
    )

    n = 0
    hit_sender_t = hit_sender_v = 0
    hit_subj_t = hit_subj_v = 0
    hit_full_t = hit_full_v = 0
    hit_top_t = hit_top_v = 0
    hit_any_t = hit_any_v = 0
    hit_trusted_identity_in_from_or_body = 0
    domain_trusted_identity: Counter[str] = Counter()
    domain_tatiana_in_from: Counter[str] = Counter()
    domain_vivanco_in_from: Counter[str] = Counter()
    sender_samples_t: list[str] = []
    sender_samples_v: list[str] = []

    for batch in iter_sqlite_email_batches_with_progress(
        conn, cur, desc="Audit Tatiana/Vivanco signals"
    ):
        for row in batch:
            n += 1
            sender = row["sender"] or ""
            subj = row["subject"] or ""
            full = row["full_body_clean"] or ""
            top = row["top_reply_clean"] or ""

            t_in_s = bool(_RE_TATIANA.search(sender))
            v_in_s = bool(_RE_VIVANCO.search(sender))
            t_in_sub = bool(_RE_TATIANA.search(subj))
            v_in_sub = bool(_RE_VIVANCO.search(subj))
            t_in_f = bool(_RE_TATIANA.search(full))
            v_in_f = bool(_RE_VIVANCO.search(full))
            t_in_top = bool(_RE_TATIANA.search(top))
            v_in_top = bool(_RE_VIVANCO.search(top))

            if t_in_s:
                hit_sender_t += 1
                pe = primary_sender_email(sender)
                dtf = domain_of(pe or "") or "(no address)"
                domain_tatiana_in_from[dtf] += 1
                if len(sender_samples_t) < args.sample:
                    sender_samples_t.append(sender[:200])
            if v_in_s:
                hit_sender_v += 1
                pev = primary_sender_email(sender)
                dvf = domain_of(pev or "") or "(no address)"
                domain_vivanco_in_from[dvf] += 1
                if len(sender_samples_v) < args.sample:
                    sender_samples_v.append(sender[:200])
            if t_in_sub:
                hit_subj_t += 1
            if v_in_sub:
                hit_subj_v += 1
            if t_in_f:
                hit_full_t += 1
            if v_in_f:
                hit_full_v += 1
            if t_in_top:
                hit_top_t += 1
            if v_in_top:
                hit_top_v += 1

            if t_in_s or t_in_sub or t_in_f or t_in_top:
                hit_any_t += 1
            if v_in_s or v_in_sub or v_in_f or v_in_top:
                hit_any_v += 1

            if sender_domain_matches_voice_domains(sender, trusted) and (
                t_in_s or v_in_s or t_in_f or v_in_f or t_in_top or v_in_top
            ):
                hit_trusted_identity_in_from_or_body += 1
                pe = primary_sender_email(sender)
                d = domain_of(pe or "") or "(no domain)"
                domain_trusted_identity[d] += 1

    print(f"DB: {db_path}")
    print(f"Rows scanned: {n:,}")
    print(f"Trusted sender domains (internal ∪ voice): {sorted(trusted)}")
    print()
    print("Counts — word-boundary Tatiana / Vivanco:")
    print(f"  From header contains 'Tatiana': {hit_sender_t:,}")
    if domain_tatiana_in_from:
        print("    → by parsed From-address domain (top 12):")
        for dom, c in domain_tatiana_in_from.most_common(12):
            print(f"       {dom}: {c:,}")
    print(f"  From header contains 'Vivanco': {hit_sender_v:,}")
    if domain_vivanco_in_from:
        print("    → by parsed From-address domain (top 12):")
        for dom, c in domain_vivanco_in_from.most_common(12):
            print(f"       {dom}: {c:,}")
    print(f"  Subject contains 'Tatiana': {hit_subj_t:,}")
    print(f"  Subject contains 'Vivanco': {hit_subj_v:,}")
    print(f"  full_body_clean contains 'Tatiana': {hit_full_t:,}")
    print(f"  full_body_clean contains 'Vivanco': {hit_full_v:,}")
    print(f"  top_reply_clean contains 'Tatiana': {hit_top_t:,}")
    print(f"  top_reply_clean contains 'Vivanco': {hit_top_v:,}")
    print(f"  Any field above — Tatiana: {hit_any_t:,}")
    print(f"  Any field above — Vivanco: {hit_any_v:,}")
    print()
    print(
        "Trusted-domain senders with Tatiana/Vivanco in From OR clean body "
        f"(cohort-style signal): {hit_trusted_identity_in_from_or_body:,}"
    )
    if domain_trusted_identity:
        print("  Sender domains (same rows):")
        for dom, c in domain_trusted_identity.most_common(15):
            print(f"    {dom}: {c:,}")
    print()
    if sender_samples_t:
        print(f"Sample From headers mentioning Tatiana (up to {args.sample}):")
        for s in sender_samples_t:
            print(f"  {s!r}")
    if sender_samples_v:
        print(f"Sample From headers mentioning Vivanco (up to {args.sample}):")
        for s in sender_samples_v:
            print(f"  {s!r}")
    print()
    print(
        "Note: client replies often say “Hola Tatiana” in body; those usually have "
        "external From domains and are not counted as trusted-domain signature hits."
    )


if __name__ == "__main__":
    main()
