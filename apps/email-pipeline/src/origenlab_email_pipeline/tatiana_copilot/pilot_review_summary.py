from __future__ import annotations

import csv
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .pilot_schemas import (
    PILOT_REVIEW_ALL_FIELDS,
    sentiment_numeric,
)


@dataclass(frozen=True)
class PilotReviewRow:
    case_id: str
    abstained: bool
    reviewer_decision: str
    reviewer_edit_level: str
    reviewer_sentiment: str
    reviewer_notes: str
    approved_for_send: str


def load_pilot_review_rows(path: Path) -> list[PilotReviewRow]:
    rows: list[PilotReviewRow] = []
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            cid = (row.get("case_id") or "").strip()
            if not cid:
                continue
            abst = (row.get("abstained") or "").strip().lower() == "y"
            rows.append(
                PilotReviewRow(
                    case_id=cid,
                    abstained=abst,
                    reviewer_decision=(row.get("reviewer_decision") or "").strip().lower(),
                    reviewer_edit_level=(row.get("reviewer_edit_level") or "").strip().lower(),
                    reviewer_sentiment=(row.get("reviewer_sentiment") or "").strip().lower(),
                    reviewer_notes=(row.get("reviewer_notes") or "").strip(),
                    approved_for_send=(row.get("approved_for_send") or "").strip().lower(),
                )
            )
    return rows


def _is_reviewed(rr: PilotReviewRow) -> bool:
    return bool(rr.reviewer_decision)


def _note_bucket(note: str) -> str | None:
    n = note.lower()
    rules = [
        ("grounding", ["invent", "alucin", "no respalda", "sin respaldo", "precisión", "dato"]),
        ("tone", ["tono", "formal", "informal"]),
        ("length", ["largo", "corto", "reducir"]),
        ("missing_context", ["falta", "contexto", "ambiguo", "poco claro"]),
        ("subject", ["asunto", "subject"]),
        ("retrieval", ["ejemplo", "precedente", "estilo"]),
    ]
    for bucket, kws in rules:
        if any(k in n for k in kws):
            return bucket
    return None


def recommend_pilot_phase(summary: dict[str, Any]) -> dict[str, Any]:
    """
    Transparent thresholds; labels: continue_pilot | tighten_prompting | tighten_retrieval |
    narrow_case_selection | stop_pilot | insufficient_review_data
    """
    total = int(summary["counts"]["total_cases"])
    reviewed = int(summary["counts"]["reviewed_cases"])
    if total == 0:
        return {
            "label": "insufficient_review_data",
            "rationale": ["No rows in pilot_review.csv"],
        }
    if reviewed < max(3, int(math.ceil(total * 0.3))):
        return {
            "label": "insufficient_review_data",
            "rationale": [
                f"Only {reviewed}/{total} cases have reviewer_decision; "
                "complete at least ~30% or 3 rows for a stable read."
            ],
            "thresholds": {"min_reviewed": max(3, int(math.ceil(total * 0.3))), "reviewed": reviewed},
        }

    rates = summary["rates"]
    rej = rates["reject_rate"]
    appr = rates["approve_rate"]
    aw = rates["approve_with_edits_rate"]
    ncl = rates["needs_clarification_rate"]
    abst = summary["counts"]["abstained_cases"] / max(total, 1)
    heavy_edits = summary["counts"]["edit_level_heavy"] + summary["counts"]["edit_level_moderate"]
    edit_burden = heavy_edits / max(reviewed, 1)

    rationale: list[str] = []
    label = "continue_pilot"

    if rej >= 0.35 or (appr + aw) < 0.25:
        return {
            "label": "stop_pilot",
            "rationale": [
                f"High reject_rate={rej:.2f} or low approval rates (approve={appr:.2f}, approve_with_edits={aw:.2f}).",
            ],
            "thresholds": {"reject_rate": rej, "approve_rate": appr},
        }

    if ncl >= 0.35 or abst >= 0.35:
        label = "narrow_case_selection"
        rationale.append(
            f"Many needs_clarification or abstains in batch (ncl_rate={ncl:.2f}, abstain_share={abst:.2f})."
        )

    if aw >= 0.45 or edit_burden >= 0.35:
        if label == "continue_pilot":
            label = "tighten_prompting"
        rationale.append(
            f"High approve_with_edits={aw:.2f} or edit burden moderate/heavy={edit_burden:.2f}; tune prompts/post-process."
        )

    if summary["counts"]["note_bucket_retrieval"] >= max(2, int(math.ceil(reviewed * 0.2))):
        if label == "continue_pilot":
            label = "tighten_retrieval"
        rationale.append("Several reviewer notes mention retrieval/precedent issues.")

    if label == "continue_pilot" and not rationale:
        rationale.append("Approvals healthy; reject rate low; proceed with small batches.")

    return {"label": label, "rationale": rationale or ["No strong negative signals."], "thresholds": {}}


def summarize_pilot_review(csv_path: Path) -> dict[str, Any]:
    rows = load_pilot_review_rows(csv_path)
    total = len(rows)
    reviewed = [r for r in rows if _is_reviewed(r)]
    abstained_cases = sum(1 for r in rows if r.abstained)

    dec_counts = Counter(r.reviewer_decision for r in reviewed if r.reviewer_decision)
    edit_counts = Counter(r.reviewer_edit_level for r in reviewed if r.reviewer_edit_level)
    sent_counts = Counter(r.reviewer_sentiment for r in reviewed if r.reviewer_sentiment)

    approve_n = dec_counts.get("approve", 0)
    aw_n = dec_counts.get("approve_with_edits", 0)
    rej_n = dec_counts.get("reject", 0)
    ncl_n = dec_counts.get("needs_clarification", 0)
    rev_n = len(reviewed)

    rates = {
        "approve_rate": approve_n / rev_n if rev_n else 0.0,
        "approve_with_edits_rate": aw_n / rev_n if rev_n else 0.0,
        "reject_rate": rej_n / rev_n if rev_n else 0.0,
        "needs_clarification_rate": ncl_n / rev_n if rev_n else 0.0,
        "approve_or_aw_rate": (approve_n + aw_n) / rev_n if rev_n else 0.0,
    }

    sent_vals = [sentiment_numeric(r.reviewer_sentiment) for r in reviewed]
    sent_vals = [x for x in sent_vals if x is not None]
    avg_sent = sum(sent_vals) / len(sent_vals) if sent_vals else None

    note_buckets = Counter()
    for r in reviewed:
        b = _note_bucket(r.reviewer_notes)
        if b:
            note_buckets[b] += 1

    top_rejects = [r.case_id for r in reviewed if r.reviewer_decision == "reject"]
    top_heavy = [
        r.case_id
        for r in reviewed
        if r.reviewer_edit_level in ("heavy", "moderate") and r.reviewer_decision != "reject"
    ]

    summary = {
        "counts": {
            "total_cases": total,
            "reviewed_cases": rev_n,
            "unreviewed_cases": total - rev_n,
            "abstained_cases": abstained_cases,
            "decision_approve": approve_n,
            "decision_approve_with_edits": aw_n,
            "decision_reject": rej_n,
            "decision_needs_clarification": ncl_n,
            "edit_level_none": edit_counts.get("none", 0),
            "edit_level_light": edit_counts.get("light", 0),
            "edit_level_moderate": edit_counts.get("moderate", 0),
            "edit_level_heavy": edit_counts.get("heavy", 0),
            "sentiment_good": sent_counts.get("good", 0),
            "sentiment_mixed": sent_counts.get("mixed", 0),
            "sentiment_poor": sent_counts.get("poor", 0),
            "approved_for_send_y": sum(1 for r in reviewed if r.approved_for_send == "y"),
            "approved_for_send_n": sum(1 for r in reviewed if r.approved_for_send == "n"),
            "note_bucket_grounding": note_buckets.get("grounding", 0),
            "note_bucket_tone": note_buckets.get("tone", 0),
            "note_bucket_length": note_buckets.get("length", 0),
            "note_bucket_missing_context": note_buckets.get("missing_context", 0),
            "note_bucket_subject": note_buckets.get("subject", 0),
            "note_bucket_retrieval": note_buckets.get("retrieval", 0),
        },
        "rates": rates,
        "averages": {
            "reviewer_sentiment_score_1_to_3": avg_sent,
        },
        "diagnostics": {
            "reject_case_ids": top_rejects,
            "heavy_edit_case_ids": top_heavy[:15],
            "note_keyword_buckets": dict(note_buckets),
        },
    }
    summary["recommendation"] = recommend_pilot_phase(summary)
    return summary


def write_pilot_review_outputs(*, summary: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pilot_review_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "pilot_review_summary.md").write_text(_render_review_md(summary), encoding="utf-8")


def _render_review_md(s: dict[str, Any]) -> str:
    c = s["counts"]
    r = s["rates"]
    rec = s["recommendation"]
    lines = [
        "# Tatiana pilot — human review summary",
        "",
        "## Headline",
        f"- **total_cases**: {c['total_cases']}",
        f"- **reviewed_cases**: {c['reviewed_cases']}",
        f"- **unreviewed_cases**: {c['unreviewed_cases']}",
        f"- **abstained_cases** (machine): {c['abstained_cases']}",
        "",
        "## Decisions (reviewed only)",
        f"- **approve**: {c['decision_approve']}",
        f"- **approve_with_edits**: {c['decision_approve_with_edits']}",
        f"- **reject**: {c['decision_reject']}",
        f"- **needs_clarification**: {c['decision_needs_clarification']}",
        "",
        "## Rates",
        f"- **approve_rate**: {r['approve_rate']:.3f}",
        f"- **approve_with_edits_rate**: {r['approve_with_edits_rate']:.3f}",
        f"- **approve + approve_with_edits**: {r['approve_or_aw_rate']:.3f}",
        f"- **reject_rate**: {r['reject_rate']:.3f}",
        f"- **needs_clarification_rate**: {r['needs_clarification_rate']:.3f}",
        "",
        "## Edit burden (reviewed)",
        f"- **none / light / moderate / heavy**: {c['edit_level_none']} / {c['edit_level_light']} / "
        f"{c['edit_level_moderate']} / {c['edit_level_heavy']}",
        "",
        "## Sentiment (reviewed)",
        f"- **good / mixed / poor**: {c['sentiment_good']} / {c['sentiment_mixed']} / {c['sentiment_poor']}",
        f"- **avg sentiment score (1=poor..3=good)**: {s['averages']['reviewer_sentiment_score_1_to_3']}",
        "",
        "## Tracking",
        f"- **approved_for_send=y / n**: {c['approved_for_send_y']} / {c['approved_for_send_n']}",
        "",
        "## Note buckets (keyword heuristic)",
        f"{s['diagnostics']['note_keyword_buckets']}",
        "",
        "## Recommendation",
        f"- **label**: `{rec['label']}`",
    ]
    for line in rec.get("rationale") or []:
        lines.append(f"  - {line}")
    lines.append("")
    lines.append("This file is diagnostic only — it does not send email.")
    return "\n".join(lines) + "\n"


def validate_pilot_review_csv_headers(path: Path) -> list[str]:
    """Return missing required columns, if any."""
    with path.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        have = set((r.fieldnames or []))
    missing = [c for c in PILOT_REVIEW_ALL_FIELDS if c not in have]
    return missing
