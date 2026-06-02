"""Phase 5K: dated 2026-06-01 manual outreach registry removed; generic failure types remain."""

from __future__ import annotations

from pathlib import Path

import pytest

from origenlab_email_pipeline.campaigns.manual_outreach_failure_types import classify_failure_type

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "src" / "origenlab_email_pipeline" / "campaigns"
REMOVED_MODULE = PKG / "manual_outreach_2026_06_01.py"
REMOVED_SCRIPTS = (
    REPO / "scripts" / "qa" / "build_manual_outreach_2026_06_01_digest.py",
    REPO / "scripts" / "qa" / "apply_manual_outreach_2026_06_01_corrections.py",
)


def test_phase5k_manual_outreach_registry_module_removed() -> None:
    assert not REMOVED_MODULE.is_file()


@pytest.mark.parametrize("path", REMOVED_SCRIPTS, ids=lambda p: p.name)
def test_phase5k_dated_manual_outreach_scripts_removed(path: Path) -> None:
    assert not path.is_file()


def test_classify_failure_type_no_such_user() -> None:
    assert classify_failure_type("550 5.1.1 User unknown") == "no_such_user"


def test_classify_failure_type_group_permission() -> None:
    assert (
        classify_failure_type("You do not have permission to post to this Google group")
        == "group_or_permission"
    )


def test_classify_failure_type_domain_not_found() -> None:
    assert classify_failure_type("Domain mrlab.cl not found") == "domain_not_found"


def test_classify_failure_type_remote_server_misconfigured() -> None:
    assert classify_failure_type("Remote server misconfigured") == "remote_server_misconfigured"


def test_classify_failure_type_unknown_fallback() -> None:
    assert classify_failure_type("something else entirely") == "unknown"


def test_post_send_digest_imports_failure_types_from_generic_module() -> None:
    text = (PKG / "post_send_digest.py").read_text(encoding="utf-8")
    assert "manual_outreach_failure_types" in text
    assert "manual_outreach_2026_06_01" not in text
