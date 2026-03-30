#!/usr/bin/env python3
"""
Export all unique email addresses (from sender + recipients) to a CSV with counts.
Useful to list one-off contacts (e.g. teachers, universities, organisations).

  uv run python scripts/tools/export_unique_emails_csv.py
  uv run python scripts/tools/export_unique_emails_csv.py --out reports/out/unique_emails.csv

Output: CSV with columns email, domain, count_as_sender, count_in_recipients, total_occurrences
        and prints total unique email count.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings

EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", re.I)


def extract_emails(text: str) -> list[str]:
    """Return list of email addresses found in text (e.g. From or To/Cc)."""
    return EMAIL_RE.findall(text or "")


def is_plausible_email(addr: str) -> bool:
    """Drop malformed captures (e.g. local part starting with dot, empty local)."""
    addr = addr.strip()
    if not addr or "@" not in addr:
        return False
    local, _, domain = addr.partition("@")
    local = local.strip()
    domain = domain.strip()
    if not local or not domain:
        return False
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    if len(domain) < 4 or "." not in domain:
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Export unique emails (sender + recipients) to CSV with counts")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None, help="Output CSV path (default: reports/out/unique_emails.csv)")
    args = ap.parse_args()

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    if not db_path.is_file():
        print("DB not found:", db_path, file=sys.stderr)
        sys.exit(1)

    out_path = args.out or (_ROOT / "reports" / "out" / "unique_emails.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # count_as_sender[email], count_in_recipients[email] (lowercase for uniqueness)
    count_as_sender: dict[str, int] = defaultdict(int)
    count_in_recipients: dict[str, int] = defaultdict(int)

    conn = __import__("sqlite3").connect(str(db_path))
    cur = conn.execute("SELECT sender, recipients FROM emails")
    for row in cur:
        sender_str = row[0] or ""
        recip_str = row[1] or ""
        for addr in extract_emails(sender_str):
            addr = addr.lower()
            if is_plausible_email(addr):
                count_as_sender[addr] += 1
        for addr in extract_emails(recip_str):
            addr = addr.lower()
            if is_plausible_email(addr):
                count_in_recipients[addr] += 1
    conn.close()

    all_emails = sorted(set(count_as_sender) | set(count_in_recipients))

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_NONNUMERIC)
        w.writerow(["email", "domain", "count_as_sender", "count_in_recipients", "total_occurrences"])
        for addr in all_emails:
            s = count_as_sender[addr]
            r = count_in_recipients[addr]
            domain = addr.split("@")[-1].lower() if "@" in addr else ""
            w.writerow([addr, domain, s, r, s + r])

    print("Wrote:", out_path)
    print("Total unique emails:", len(all_emails))


if __name__ == "__main__":
    main()
