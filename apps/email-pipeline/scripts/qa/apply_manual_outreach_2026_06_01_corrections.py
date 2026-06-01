#!/usr/bin/env python3
"""Apply post-send corrections for 2026-06-01 manual outreach (hannelore bounce, mle false positive)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.contact_email_suppression import (
    delete_contact_email_suppression,
    fetch_contact_email_suppression_row,
)
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.outreach_contact_state import (
    delete_outreach_contact_state_row,
    fetch_outreach_contact_state_row,
    outreach_touch_timestamps_for_upsert,
    upsert_outreach_contact_state,
    validate_outreach_contact_state_payload,
)
from origenlab_email_pipeline.timeutil import now_iso

HANNELORE = "hannelore.valentin@sgs.com"
MLE = "mle@mlelab.cl"
DFUENTE = "dfuente@durandin.cl"
UPDATED_BY = "manual_outreach_2026_06_01_corrections"


def _snapshot(conn, email: str) -> dict[str, object]:
    sup = fetch_contact_email_suppression_row(conn, email)
    ocs = fetch_outreach_contact_state_row(conn, email)
    return {
        "suppression": dict(sup) if sup else None,
        "outreach_state": dict(ocs) if ocs else None,
    }


def apply_corrections(conn, *, dry_run: bool = False) -> dict[str, object]:
    before = {
        HANNELORE: _snapshot(conn, HANNELORE),
        MLE: _snapshot(conn, MLE),
        DFUENTE: _snapshot(conn, DFUENTE),
    }
    actions: list[str] = []

    if not dry_run:
        if delete_outreach_contact_state_row(conn, HANNELORE):
            actions.append(f"deleted outreach_contact_state for {HANNELORE}")
        delete_contact_email_suppression(conn, MLE)
        actions.append(f"deleted bounce suppression for {MLE} (false positive from NDR 710676)")
        ts = now_iso()
        existing = fetch_outreach_contact_state_row(conn, MLE)
        if existing is None:
            first, last = outreach_touch_timestamps_for_upsert(
                new_state="contacted",
                existing_row=None,
                touch_at_iso=ts,
            )
            upsert_outreach_contact_state(
                conn,
                payload=validate_outreach_contact_state_payload(
                    contact_email=MLE,
                    state="contacted",
                    first_contacted_at=first,
                    last_contacted_at=last,
                    source="cyber_bcc_extra_2026_06_01",
                    notes="campaign_outreach/cyber_bcc_extra",
                    updated_by=UPDATED_BY,
                    lead_id=None,
                ),
                at_iso=ts,
            )
            actions.append(f"ensured outreach contacted for {MLE}")
        conn.commit()

    after = {
        HANNELORE: _snapshot(conn, HANNELORE),
        MLE: _snapshot(conn, MLE),
        DFUENTE: _snapshot(conn, DFUENTE),
    }
    return {"dry_run": dry_run, "before": before, "after": after, "actions": actions}


def write_corrections_report(out_dir: Path, result: dict[str, object]) -> Path:
    out_dir = out_dir.resolve()
    path = out_dir / "manual_outreach_2026-06-01_corrections.md"
    before = result["before"]
    after = result["after"]
    lines = [
        "# Manual outreach corrections — 2026-06-01",
        "",
        "## hannelore.valentin@sgs.com",
        "- **Action:** keep `bounce_no_such_user` suppression; remove `outreach_contact_state` contacted row.",
        "- **NDR:** email_id 710678 — recipient not found at sgs.com (real bounce).",
        "",
        "### Before",
        f"```json\n{json.dumps(before[HANNELORE], indent=2, ensure_ascii=False)}\n```",
        "",
        "### After",
        f"```json\n{json.dumps(after[HANNELORE], indent=2, ensure_ascii=False)}\n```",
        "",
        "## mle@mlelab.cl",
        "- **Action:** remove bounce suppression tied to NDR 710676 (failure was for dfuente@durandin.cl only).",
        "- **Keep:** `outreach_contact_state` contacted / `cyber_bcc_extra_2026_06_01`.",
        "",
        "### Before",
        f"```json\n{json.dumps(before[MLE], indent=2, ensure_ascii=False)}\n```",
        "",
        "### After",
        f"```json\n{json.dumps(after[MLE], indent=2, ensure_ascii=False)}\n```",
        "",
        "## dfuente@durandin.cl (unchanged)",
        f"```json\n{json.dumps(after[DFUENTE], indent=2, ensure_ascii=False)}\n```",
        "",
        "## Actions applied",
    ]
    for act in result.get("actions") or []:
        lines.append(f"- {act}")
    if result.get("dry_run"):
        lines.append("- (dry-run — no writes)")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active" / "current",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    conn = connect(args.db or load_settings().resolved_sqlite_path())
    try:
        result = apply_corrections(conn, dry_run=args.dry_run)
        report = write_corrections_report(args.out_dir, result)
        result["report_path"] = str(report)
    finally:
        conn.close()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
