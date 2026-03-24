#!/usr/bin/env python3
"""Cohort integrity, readiness fields, freshness, taxonomy, and trust scorecard.

This is **operational** validation (partition, nulls, stale pack, merged hunt, provenance). It does
**not** replace ``verify_client_pack_consistency.py``, which covers pack vs DB and top20
cross-checks. For the **final combined** pass/fail, run ``publish_gate.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.hunt_csv_alignment import describe_hunt_misalignment
from origenlab_email_pipeline.lead_provenance import (
    operational_stack_last_run_path,
    read_operational_run_id_from_env,
    read_operational_stack_last_run,
    try_git_revision,
)
from origenlab_email_pipeline.operational_trust import (
    TrustCheck,
    any_critical_failed,
    check_cohort_partition,
    check_provenance_db_path,
    check_readiness_critical_fields,
    check_stale_client_pack,
    check_taxonomy_hunt,
    leads_active_paths,
    trust_summary,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=REPO)
    p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (for provenance compare; default from settings)",
    )
    p.add_argument(
        "--max-pack-age-hours",
        type=float,
        default=168.0,
        help="Fail if client_pack summary generated_at_utc is older than this (default: 168h = 7d)",
    )
    p.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Scorecard JSON (default: reports/out/active/operational_trust_scorecard.json)",
    )
    p.add_argument(
        "--md-out",
        type=Path,
        default=None,
        help="Scorecard Markdown (default: docs/generated/operational_trust_scorecard.md)",
    )
    return p


def check_hunt_merged_alignment(current: Path, merged: Path) -> list[TrustCheck]:
    if not current.is_file():
        return [
            TrustCheck(
                "hunt_current_file",
                False,
                True,
                f"Missing hunt cohort file: {current}",
            )
        ]
    if not merged.is_file():
        return [
            TrustCheck(
                "hunt_merged_file",
                False,
                True,
                f"Missing merged hunt file: {merged}",
            )
        ]
    try:
        msg = describe_hunt_misalignment(current, merged)
    except (OSError, ValueError) as e:
        return [
            TrustCheck(
                "hunt_merged_read",
                False,
                True,
                f"Could not compare hunt CSVs: {e}",
            )
        ]
    hint = (
        " Remediation: re-run merge from current (e.g. "
        "`uv run python scripts/leads/merge_contact_hunt_enrichment.py -b reports/out/active/leads_contact_hunt_current.csv "
        "-e <enrichment.csv> -o reports/out/active/leads_contact_hunt_current_merged.csv`) "
        "or align merged `id_lead` set to current before import."
    )
    return [
        TrustCheck(
            "hunt_merged_id_alignment",
            msg is None,
            True,
            "current and merged id_lead sets match"
            if msg is None
            else msg.split("\n", 1)[0] + hint,
            details={"full_message": msg} if msg else {},
        )
    ]


def write_scorecard_json(
    path: Path,
    checks: list[TrustCheck],
    summary: dict,
    *,
    provenance: dict | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {
        "summary": summary,
        "checks": [c.to_dict() for c in checks],
    }
    if provenance is not None:
        payload["provenance"] = provenance
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_scorecard_md(
    path: Path,
    checks: list[TrustCheck],
    summary: dict,
    *,
    operational_run_id: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    run_line = (
        f"- **Operational run ID:** `{operational_run_id}`"
        if operational_run_id
        else "- **Operational run ID:** _(not set; run publish_gate from `run_leads_operational_stack.sh` or export ORIGENLAB_LEADS_OPERATIONAL_RUN_ID)_"
    )
    lines = [
        "# Operational trust scorecard",
        "",
        run_line,
        "",
        f"- **Total checks:** {summary['total']}",
        f"- **Critical failed:** {summary['critical_failed']}",
        f"- **Non-critical failed:** {summary['noncritical_failed']}",
        "",
        "| Status | Critical | Check | Message |",
        "|--------|----------|-------|---------|",
    ]
    for c in checks:
        st = "pass" if c.ok else "**fail**"
        cr = "yes" if c.critical else "no"
        msg = c.message.replace("|", "\\|")
        lines.append(f"| {st} | {cr} | `{c.check_id}` | {msg} |")
    lines.append("")
    lines.append("_Generated by `scripts/qa/audit_operational_trust.py`._")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    repo = args.repo_root.resolve()
    db = args.db
    if db is None:
        db = load_settings().resolved_sqlite_path()
    else:
        db = db.resolve()
    paths = leads_active_paths(repo)
    json_out = getattr(args, "json_out", None) or (
        repo / "reports" / "out" / "active" / "operational_trust_scorecard.json"
    )
    md_out = getattr(args, "md_out", None) or (
        repo / "docs" / "generated" / "operational_trust_scorecard.md"
    )

    checks: list[TrustCheck] = []
    checks.extend(
        check_cohort_partition(
            paths.hunt.resolve(),
            paths.ready.resolve(),
            paths.needs.resolve(),
            paths.not_ready.resolve(),
        )
    )
    checks.extend(
        check_readiness_critical_fields(
            paths.ready.resolve(),
            paths.needs.resolve(),
            paths.not_ready.resolve(),
        )
    )
    checks.extend(check_taxonomy_hunt(paths.hunt.resolve()))
    checks.append(
        check_stale_client_pack(
            paths.client_pack_summary.resolve(),
            max_age_hours=args.max_pack_age_hours,
        )
    )
    checks.append(
        check_provenance_db_path(
            resolved_db=db,
            audit_md_path=paths.contact_audit_md.resolve(),
        )
    )
    checks.extend(
        check_hunt_merged_alignment(
            paths.hunt.resolve(),
            paths.merged_hunt.resolve(),
        )
    )

    summary = trust_summary(checks)
    operational_run_id = read_operational_run_id_from_env()
    audit_prov = {
        "audit_generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sqlite_path_resolved": str(db),
        "operational_run_id": operational_run_id,
        "client_pack_summary_path": str(paths.client_pack_summary.resolve()),
        "operational_stack_last_run_path": str(operational_stack_last_run_path(repo)),
        "operational_stack_last_run": read_operational_stack_last_run(repo),
        "git_revision": try_git_revision(repo),
        "caveat": (
            "Links this audit run to paths on disk. operational_run_id is taken from "
            "ORIGENLAB_LEADS_OPERATIONAL_RUN_ID when set (operational stack). "
            "operational_stack_last_run is the latest manifest on disk; it may be from a different run "
            "unless you just finished the stack. Provenance does not replace validation."
        ),
    }
    write_scorecard_json(json_out.resolve(), checks, summary, provenance=audit_prov)
    write_scorecard_md(
        md_out.resolve(),
        checks,
        summary,
        operational_run_id=operational_run_id,
    )
    print(f"Wrote {json_out}")
    print(f"Wrote {md_out}")

    for c in checks:
        mark = "OK  " if c.ok else "FAIL"
        crit = " [critical]" if c.critical else ""
        print(f"{mark}{crit} {c.check_id}: {c.message}")

    return 1 if any_critical_failed(checks) else 0


def main() -> None:
    raise SystemExit(run(build_parser().parse_args()))


if __name__ == "__main__":
    main()
