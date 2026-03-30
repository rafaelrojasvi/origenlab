#!/usr/bin/env python3
import csv
from pathlib import Path

CSV_PATH = Path("reports/out/tatiana_candidate_cohort_marketing_top200_review_queue.csv")
OUT_PATH = Path("reports/out/tatiana_candidate_cohort_marketing_top200_labeled_final.csv")

VALID = {"intro_marketing", "quote_followup", "tone_only", "exclude"}

def prompt_label(current: str) -> str:
    while True:
        v = input(f"label [{current}] (i/q/t/e, Enter=keep, s=skip, x=exit): ").strip().lower()
        if v == "":
            return current
        if v == "s":
            return current
        if v == "x":
            raise KeyboardInterrupt
        m = {"i": "intro_marketing", "q": "quote_followup", "t": "tone_only", "e": "exclude"}
        if v in m:
            return m[v]
        if v in VALID:
            return v
        print("Invalid. Use i/q/t/e, full label, Enter, s, or x.")

def main() -> None:
    rows = list(csv.DictReader(CSV_PATH.open(newline="", encoding="utf-8")))
    flagged = [r for r in rows if (r.get("needs_manual_review") or "").lower() == "y"]
    print(f"Loaded {len(rows)} rows; reviewing {len(flagged)} flagged rows.")

    try:
        for idx, r in enumerate(flagged, start=1):
            rank = r.get("review_priority_rank")
            cur = (r.get("human_label") or "").strip() or "quote_followup"
            print("\n" + "=" * 90)
            print(f"[{idx}/{len(flagged)}] rank={rank} terms={r.get('review_terms','')}")
            print("subject:", (r.get("subject") or "")[:160])
            body = (r.get("body_for_review") or "").replace("\r\n", "\n")
            print("preview:\n", body[:700])
            new_label = prompt_label(cur)
            r["human_label"] = new_label
            if not (r.get("human_notes") or "").strip():
                r["human_notes"] = "manual_review_ops_queue"
            if new_label == "exclude":
                r["keep_for_style_guide"] = "n"
                r["keep_for_retrieval_later"] = "n"
            elif new_label == "tone_only":
                r["keep_for_style_guide"] = "maybe"
                r["keep_for_retrieval_later"] = "maybe"
            else:
                if not (r.get("keep_for_style_guide") or "").strip():
                    r["keep_for_style_guide"] = "y"
                if not (r.get("keep_for_retrieval_later") or "").strip():
                    r["keep_for_retrieval_later"] = "y"

    except KeyboardInterrupt:
        print("\nStopped early; saving progress...")

    fieldnames = list(rows[0].keys())
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader(); w.writerows(rows)

    print(f"Saved: {OUT_PATH}")

if __name__ == "__main__":
    main()
