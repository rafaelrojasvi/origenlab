#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import sys
from collections import Counter
from pathlib import Path


DECISIONS = {"accept", "edit_light", "edit_heavy", "reject"}

_REVIEWER_COPY_KEYS = (
    "reviewer_score_tone",
    "reviewer_score_usefulness",
    "reviewer_score_groundedness",
    "reviewer_score_edit_distance_estimate",
    "reviewer_decision",
    "notes",
)


def _draft_body_fingerprint(draft: str) -> str:
    """Hash email body only so mock drafts match across rows when only Asunto/MIME differs."""
    t = (draft or "").replace("\r\n", "\n").strip()
    if not t:
        return ""
    lines = t.split("\n")
    j = 0
    if lines and lines[0].lstrip().lower().startswith("asunto:"):
        j = 1
    while j < len(lines) and lines[j].strip() == "":
        j += 1
    body = "\n".join(lines[j:]).strip()
    if not body:
        return ""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _prompt_score(name: str, current: str) -> str:
    cur = (current or "").strip()
    while True:
        v = input(f"{name} [1-5] (current={cur or 'blank'}, Enter=keep, s=skip): ").strip()
        if v == "":
            return cur
        if v.lower() == "s":
            return cur
        try:
            n = int(v)
        except ValueError:
            print("Invalid: enter 1-5, Enter, or s.")
            continue
        if 1 <= n <= 5:
            return str(n)
        print("Invalid: enter 1-5.")


def _prompt_decision(current: str) -> str:
    cur = (current or "").strip().lower()
    while True:
        v = input(
            f"decision (a/l/h/r) [current={cur or 'blank'}] (Enter=keep, s=skip): "
        ).strip().lower()
        if v == "":
            return cur
        if v == "s":
            return cur
        m = {"a": "accept", "l": "edit_light", "h": "edit_heavy", "r": "reject"}
        if v in m:
            return m[v]
        if v in DECISIONS:
            return v
        print("Invalid: use a/l/h/r, accept/edit_light/edit_heavy/reject, Enter, or s.")


def _is_scored(row: dict[str, str]) -> bool:
    for k in (
        "reviewer_score_tone",
        "reviewer_score_usefulness",
        "reviewer_score_groundedness",
        "reviewer_score_edit_distance_estimate",
        "reviewer_decision",
    ):
        if (row.get(k) or "").strip():
            return True
    return False


def _save_atomic(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Interactive terminal scorer for Tatiana eval_cases.csv")
    ap.add_argument(
        "--eval-dir",
        type=Path,
        required=True,
        help="Folder containing eval_cases.csv (reports/out/<ts>_tatiana_draft_eval)",
    )
    ap.add_argument(
        "--only-unscored",
        action="store_true",
        help="Only prompt for rows that have no reviewer fields set",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after N prompted rows (0 = no limit)",
    )
    ap.add_argument(
        "--batch-same-body",
        action="store_true",
        help=(
            "After scoring a row, offer to copy reviewer fields + notes to other rows whose "
            "draft body matches (Asunto line ignored — use for mock templates)."
        ),
    )
    ap.add_argument(
        "--show-draft-groups",
        action="store_true",
        help="Print draft-body group sizes (ignoring Asunto line) and exit; does not modify CSV.",
    )
    ap.add_argument(
        "--case-ids",
        type=str,
        default="",
        help=(
            "Comma-separated eval_case_id values (e.g. eval_001,eval_009). "
            "Only those rows are prompted; combine with --only-unscored to skip already-filled rows."
        ),
    )
    ap.add_argument(
        "--list-unscored",
        action="store_true",
        help="Print eval_case_id for rows with no reviewer fields; exit without modifying CSV.",
    )
    args = ap.parse_args()
    case_id_filter = {x.strip() for x in args.case_ids.split(",") if x.strip()}

    eval_csv = args.eval_dir / "eval_cases.csv"
    if not eval_csv.is_file():
        print("eval_cases.csv not found:", eval_csv, file=sys.stderr)
        raise SystemExit(1)

    with eval_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if args.show_draft_groups:
        fps = [_draft_body_fingerprint(r.get("generated_draft", "")) for r in rows]
        counts = Counter(fp for fp in fps if fp)
        empty = sum(1 for fp in fps if not fp)
        print("Draft body groups (Asunto line stripped for comparison):")
        for fp, n in counts.most_common():
            short = fp[:12] + "…" if len(fp) > 12 else fp
            print(f"  {n:4d} rows  fingerprint={short}")
        if empty:
            print(f"  {empty:4d} rows  (empty draft)")
        print(f"Total rows: {len(rows)}")
        return

    if args.list_unscored:
        unscored = [r for r in rows if not _is_scored(r)]
        for r in unscored:
            aid = (r.get("eval_case_id") or "").strip()
            abst = (r.get("abstained") or "").strip()
            print(f"{aid}\tabstained={abst}")
        print(f"Unscored: {len(unscored)} / {len(rows)}")
        return

    # Backup once per run (skipped for read-only --show-draft-groups)
    bak = args.eval_dir / "eval_cases.bak.csv"
    if not bak.exists():
        shutil.copyfile(eval_csv, bak)

    needed = [
        "reviewer_score_tone",
        "reviewer_score_usefulness",
        "reviewer_score_groundedness",
        "reviewer_score_edit_distance_estimate",
        "reviewer_decision",
        "notes",
        "system_notes",
    ]
    for c in needed:
        if c not in fieldnames:
            fieldnames.append(c)
            for r in rows:
                r.setdefault(c, "")

    prompted = 0
    for i, r in enumerate(rows, start=1):
        eid = (r.get("eval_case_id") or "").strip()
        if case_id_filter and eid not in case_id_filter:
            continue
        if args.only_unscored and _is_scored(r):
            continue

        print("\n" + "=" * 100)
        print(f"ROW {i}/{len(rows)} eval_case_id={r.get('eval_case_id','')}")
        print("expected_label:", r.get("label_expected", ""))
        print("abstained:", r.get("abstained", ""))
        print("retrieved_style_ids:", r.get("retrieved_style_ids", "")[:200])
        print("retrieved_example_ids:", r.get("retrieved_example_ids", "")[:200])
        if (r.get("system_notes") or "").strip():
            print("system_notes:", r.get("system_notes"))
        print("\n--- generated_draft (preview) ---\n")
        draft = (r.get("generated_draft") or "").strip()
        print((draft[:1200] + ("..." if len(draft) > 1200 else "")) or "(empty)")

        r["reviewer_score_tone"] = _prompt_score("tone", r.get("reviewer_score_tone", ""))
        r["reviewer_score_usefulness"] = _prompt_score(
            "usefulness", r.get("reviewer_score_usefulness", "")
        )
        r["reviewer_score_groundedness"] = _prompt_score(
            "groundedness", r.get("reviewer_score_groundedness", "")
        )
        r["reviewer_score_edit_distance_estimate"] = _prompt_score(
            "edit_distance_estimate", r.get("reviewer_score_edit_distance_estimate", "")
        )
        r["reviewer_decision"] = _prompt_decision(r.get("reviewer_decision", ""))
        note_cur = (r.get("notes") or "").strip()
        note_new = input(f"notes [free text] (current={note_cur[:60]!r}, Enter=keep): ").strip()
        if note_new != "":
            r["notes"] = note_new

        _save_atomic(eval_csv, fieldnames, rows)

        if args.batch_same_body:
            fp = _draft_body_fingerprint(r.get("generated_draft", ""))
            idx = i - 1
            peer_idxs: list[int] = []
            if fp:
                for j, row in enumerate(rows):
                    if j == idx:
                        continue
                    if _draft_body_fingerprint(row.get("generated_draft", "")) != fp:
                        continue
                    if args.only_unscored and _is_scored(row):
                        continue
                    peer_idxs.append(j)
            if peer_idxs:
                ans = input(
                    f"Apply these reviewer scores + notes to {len(peer_idxs)} other row(s) "
                    f"with the same draft body (Asunto ignored)? [y/N]: "
                ).strip().lower()
                if ans == "y":
                    for j in peer_idxs:
                        for k in _REVIEWER_COPY_KEYS:
                            rows[j][k] = r.get(k, "")
                    _save_atomic(eval_csv, fieldnames, rows)
                    print(f"Updated {len(peer_idxs)} row(s).")

        prompted += 1
        if args.limit and prompted >= args.limit:
            break

    print("\nSaved:", eval_csv)
    print("Backup:", bak)


if __name__ == "__main__":
    main()

