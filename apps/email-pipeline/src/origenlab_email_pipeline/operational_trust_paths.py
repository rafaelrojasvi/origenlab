"""Standard repo paths for hunt, readiness, top20, client pack."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LeadsActivePaths:
    """Standard repo locations for hunt, readiness exports, top20, client pack."""

    repo_root: Path
    hunt: Path
    ready: Path
    needs: Path
    not_ready: Path
    top20: Path
    merged_hunt: Path
    contact_audit_md: Path
    client_pack_summary: Path


def leads_active_paths(repo_root: Path) -> LeadsActivePaths:
    active = repo_root / "reports" / "out" / "active"
    return LeadsActivePaths(
        repo_root=repo_root,
        hunt=active / "leads_contact_hunt_current.csv",
        ready=active / "leads_ready_to_contact.csv",
        needs=active / "leads_needs_contact_research.csv",
        not_ready=active / "leads_not_ready.csv",
        top20=active / "leads_top20_for_client_report.csv",
        merged_hunt=active / "leads_contact_hunt_current_merged.csv",
        contact_audit_md=repo_root / "docs" / "generated" / "CONTACT_READINESS_AUDIT.md",
        client_pack_summary=repo_root / "reports" / "out" / "client_pack_latest" / "summary.json",
    )
