"""Static checks for public-repository security guardrails."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HYGIENE_SCRIPT = _REPO_ROOT / "scripts/security/check-public-repo-hygiene.sh"
_SECURITY_DOC = _REPO_ROOT / "docs/SECURITY_PUBLIC_REPO.md"
_WORKFLOWS = (
    _REPO_ROOT / ".github/workflows/email-pipeline.yml",
    _REPO_ROOT / ".github/workflows/api.yml",
    _REPO_ROOT / ".github/workflows/dashboard.yml",
    _REPO_ROOT / ".github/workflows/secret-scan.yml",
)


def test_hygiene_script_exists_and_uses_git_ls_files_only() -> None:
    assert _HYGIENE_SCRIPT.is_file()
    text = _HYGIENE_SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert "git ls-files" in text
    assert "apps/email-pipeline/reports/out/" in text
    assert "docs/client/" in text
    assert "contents: read" in text
    assert "curl" not in text
    assert "wget" not in text


def test_security_public_repo_doc_exists() -> None:
    text = _SECURITY_DOC.read_text(encoding="utf-8")
    assert "public" in text.lower()
    assert ".env" in text
    assert "check-public-repo-hygiene.sh" in text


def test_operator_workflows_declare_read_only_permissions() -> None:
    for workflow in _WORKFLOWS:
        assert workflow.is_file(), workflow
        text = workflow.read_text(encoding="utf-8")
        assert "permissions:" in text, workflow.name
        assert "contents: read" in text, workflow.name


def test_secret_scan_workflow_uses_gitleaks() -> None:
    text = (_REPO_ROOT / ".github/workflows/secret-scan.yml").read_text(encoding="utf-8")
    assert "gitleaks/gitleaks-action" in text
    assert "pull_request" in text


def test_readme_documents_hygiene_script() -> None:
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "./scripts/security/check-public-repo-hygiene.sh" in readme
    assert "SECURITY_PUBLIC_REPO.md" in readme
