"""Shared targets and report builder for Phase 2 script removal evidence (read-only)."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MONOREPO = REPO.parents[1]

DEPRECATED_REMOVAL_TARGETS: tuple[dict[str, str], ...] = (
    {
        "path": "scripts/tools/flag_reported_non_delivery_from_contacto.py",
        "replacement": "flag_ndr_bounces_from_contacto.py (NDR) + human review queue",
        "suggested_phase": "5",
    },
    {
        "path": "scripts/leads/advanced/export_archive_outreach_candidates.py",
        "replacement": "build_archive_send_batch.py --audit-only",
        "suggested_phase": "5",
    },
)

REMOVED_PHASE5C_TARGETS: tuple[dict[str, str], ...] = (
    {
        "path": "scripts/qa/build_buyer_opportunity_queue.py",
        "replacement": (
            "scripts/qa/build_equipment_first_opportunity_queue.py + "
            "scripts/qa/build_equipment_first_operator_queue.py"
        ),
        "removed_phase": "5C",
    },
)

REMOVED_PHASE5A_TARGETS: tuple[dict[str, str], ...] = (
    {
        "path": "scripts/ops/run_post_send_2026_06_01_refresh.sh",
        "replacement": "docs/pipeline/POST_SEND_SAFE_LOOP.md step-by-step loop",
        "removed_phase": "5A",
    },
    {
        "path": "scripts/ops/run_manual_outreach_2026_06_01_post_send_refresh.sh",
        "replacement": "docs/pipeline/POST_SEND_SAFE_LOOP.md step-by-step loop",
        "removed_phase": "5A",
    },
)

REMOVED_PHASE5B_TARGETS: tuple[dict[str, str], ...] = (
    {
        "path": "scripts/build_lead_account_rollup.py",
        "replacement": "scripts/leads/advanced/build_lead_account_rollup.py",
        "removed_phase": "5B",
    },
    {
        "path": "scripts/match_lead_accounts_to_existing_orgs.py",
        "replacement": "scripts/leads/advanced/match_lead_accounts_to_existing_orgs.py",
        "removed_phase": "5B",
    },
    {
        "path": "scripts/validate_lead_account_rollup.py",
        "replacement": "scripts/leads/advanced/validate_lead_account_rollup.py",
        "removed_phase": "5B",
    },
    {
        "path": "scripts/audit_lead_org_quality.py",
        "replacement": "scripts/leads/advanced/audit_lead_org_quality.py",
        "removed_phase": "5B",
    },
)

REFACTOR_PHASE3_TARGETS: tuple[dict[str, str], ...] = (
    {"path": "scripts/mart/build_business_mart.py", "note": "Split main() → src; tests in test_build_business_mart.py"},
    {
        "path": "scripts/ingest/05_workspace_gmail_imap_to_sqlite.py",
        "note": "Extract IMAP helpers; tests in test_workspace_gmail_imap_ingest.py",
    },
    {
        "path": "scripts/qa/export_contacted_lead_overlap_audit.py",
        "note": "Golden CSV columns locked in test_export_contacted_lead_overlap_audit.py",
    },
    {
        "path": "scripts/qa/export_email_conversation_intelligence.py",
        "note": "Golden CSV columns locked in test_export_email_conversation_intelligence.py",
    },
)

_TEST_LOCK_PATTERNS: dict[str, str] = {
    "scripts/tools/flag_reported_non_delivery_from_contacto.py": "flag_reported_non_delivery",
    "scripts/leads/advanced/export_archive_outreach_candidates.py": "export_archive_outreach_candidates",
}


@dataclass(frozen=True, slots=True)
class ReferenceCounts:
    docs: int
    tests: int
    scripts: int
    in_script_map: bool
    test_locked: bool


def _rg_files(pattern: str, roots: list[Path]) -> list[str]:
    hits: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        cp = subprocess.run(
            ["rg", "-l", pattern, str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.returncode in (0, 1):
            hits.extend(cp.stdout.splitlines())
    return sorted(set(hits))


def reference_counts(rel_path: str) -> ReferenceCounts:
    rel = rel_path.replace("\\", "/")
    base = Path(rel).name
    docs_roots = [REPO / "docs", MONOREPO / "docs", MONOREPO / "apps" / "dashboard" / "docs"]
    test_roots = [REPO / "tests", MONOREPO / "apps" / "api" / "tests"]
    script_roots = [REPO / "scripts", REPO / "Makefile", REPO / "AGENTS.md"]

    docs_hits = _rg_files(re.escape(rel), docs_roots) + _rg_files(re.escape(base), docs_roots)
    test_hits = _rg_files(re.escape(rel), test_roots) + _rg_files(re.escape(base), test_roots)
    script_hits = _rg_files(re.escape(rel), script_roots) + _rg_files(re.escape(base), script_roots)

    map_text = (REPO / "docs/SCRIPT_MAP.md").read_text(encoding="utf-8", errors="replace")
    in_map = rel in map_text or base in map_text

    lock_pat = _TEST_LOCK_PATTERNS.get(rel, base)
    critical = (REPO / "tests/test_critical_script_paths.py").read_text(encoding="utf-8", errors="replace")
    test_locked = lock_pat in critical or any(
        lock_pat in (REPO / "tests" / p).read_text(encoding="utf-8", errors="replace")
        for p in ("test_lead_compatibility_wrappers.py",)
        if (REPO / "tests" / p).is_file()
    )

    return ReferenceCounts(
        docs=len(set(docs_hits)),
        tests=len(set(test_hits)),
        scripts=len(set(script_hits)),
        in_script_map=in_map,
        test_locked=test_locked,
    )


def build_removal_evidence_markdown() -> str:
    lines: list[str] = [
        "# Phase 2 — script removal evidence",
        "",
        "Status: generated reference (read-only audit)",
        "Owner: email-pipeline-maintainers",
        "Last reviewed: 2026-06-02",
        "",
        "**Purpose:** Evidence for Phase 4–5 deprecation/removal. Phase **5A** removed dated post-send shell orchestrators; Phase **5B** removed root lead-account wrappers; Phase **5C** removed legacy buyer opportunity queue builder.",
        "",
        "Regenerate: `uv run pytest tests/test_script_removal_evidence.py::test_generate_removal_evidence_report -q`",
        "",
        "---",
        "",
        "## Deprecated / wrapper removal candidates",
        "",
        "| Path | SCRIPT_MAP | Test-locked | Doc refs | Test refs | Script refs | Replacement | Suggested phase |",
        "|------|------------|-------------|----------|-----------|-------------|-------------|-----------------|",
    ]
    for row in DEPRECATED_REMOVAL_TARGETS:
        rel = row["path"]
        rc = reference_counts(rel)
        lines.append(
            f"| `{rel}` | {'yes' if rc.in_script_map else 'no'} | "
            f"{'yes' if rc.test_locked else 'no'} | {rc.docs} | {rc.tests} | {rc.scripts} | "
            f"{row['replacement']} | {row['suggested_phase']} |"
        )
    lines.extend(
        [
            "",
            "## Removed in Phase 5A (2026-06-02)",
            "",
            "| Path | Replacement | Removed phase |",
            "|------|-------------|---------------|",
        ]
    )
    for row in REMOVED_PHASE5A_TARGETS:
        lines.append(
            f"| `{row['path']}` | {row['replacement']} | {row['removed_phase']} |",
        )
    lines.extend(
        [
            "",
            "## Removed in Phase 5B (2026-06-02)",
            "",
            "| Path | Replacement | Removed phase |",
            "|------|-------------|---------------|",
        ]
    )
    for row in REMOVED_PHASE5B_TARGETS:
        lines.append(
            f"| `{row['path']}` | {row['replacement']} | {row['removed_phase']} |",
        )
    lines.extend(
        [
            "",
            "## Removed in Phase 5C (2026-06-02)",
            "",
            "| Path | Replacement | Removed phase |",
            "|------|-------------|---------------|",
        ]
    )
    for row in REMOVED_PHASE5C_TARGETS:
        lines.append(
            f"| `{row['path']}` | {row['replacement']} | {row['removed_phase']} |",
        )
    lines.extend(
        [
            "",
            "## Phase 3 refactor targets (keep entrypoints; lock behavior first)",
            "",
            "| Path | Notes |",
            "|------|-------|",
        ]
    )
    for row in REFACTOR_PHASE3_TARGETS:
        lines.append(f"| `{row['path']}` | {row['note']} |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- **Test-locked yes** → remove only after updating `test_critical_script_paths.py`, "
            "`test_lead_compatibility_wrappers.py`, or other contract tests in the same PR.",
            "- **High doc refs** → update RUNBOOK/SCRIPT_MAP/AGENTS in Phase 1-style doc PR before deletion.",
            "- **Wrappers** → Phase 4 deprecation stderr first; Phase 5 removal when root paths have zero external refs.",
            "",
        ]
    )
    return "\n".join(lines)


def write_removal_evidence_report(path: Path | None = None) -> Path:
    out = path or (REPO / "docs/audits/PHASE2_SCRIPT_REMOVAL_EVIDENCE_20260602.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_removal_evidence_markdown(), encoding="utf-8")
    return out
