from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    return module


def test_report_scripts_resolve_repo_root_and_canonical_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    scripts_root = repo_root / "scripts"

    run_all = _load_script(scripts_root / "reports" / "run_all_reports.py", "run_all_reports")
    gen = _load_script(
        scripts_root / "reports" / "generate_client_report.py",
        "generate_client_report",
    )

    assert run_all._repo_root() == repo_root
    assert gen._repo_root() == repo_root

    # Verify known derived locations now resolve under the app root.
    assert (run_all._repo_root() / "scripts" / "tools" / "dedupe_emails_by_message_id.py").is_file()
    assert (run_all._repo_root() / "scripts" / "reports" / "generate_client_report.py").is_file()
    assert (gen._repo_root() / "docs" / "REPORT_SCOPE_CLIENT.md").is_file()
