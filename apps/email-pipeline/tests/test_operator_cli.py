"""Tests for unified operator CLI wrapper (Phase 6B / 6D / 6G / 7A / 7B / 7C / 8B) — no heavy script execution."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from origenlab_email_pipeline.cli import (
    CLI_COMMAND_NAMES,
    GMAIL_INGEST_INBOX_FOLDER,
    GMAIL_INGEST_SENT_FOLDER,
    HELP_ONLY_SUBCOMMANDS,
    MIRROR_DASHBOARD_SYNC_SCRIPT,
    POSTGRES_ENV_VARS,
    SUBCOMMAND_SCRIPTS,
    REFRESH_DASHBOARD_USAGE,
    RefreshDashboardOptions,
    build_gmail_ingest_argv_list,
    build_mirror_dashboard_argv_list,
    build_mirror_dashboard_sync_argv,
    build_refresh_dashboard_steps,
    build_subcommand_argv,
    main,
    missing_postgres_env_message,
    mirror_dashboard_uses_cloud_postgres_only,
    normalize_passthrough_args,
    postgres_url_configured,
    repo_root,
    run_mirror_dashboard,
    run_refresh_dashboard,
    script_path_for,
    validate_gmail_ingest_passthrough,
)

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"

PASSTHROUGH_ADVANCED = ("export-dnr", "ndr-review", "audit-overlap", "build-mart")


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(_SRC)}


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "origenlab_email_pipeline.cli", *args],
        cwd=str(REPO),
        env=_env(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _run_origenlab_console(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "origenlab", *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_cli_main_importable_and_callable() -> None:
    assert callable(main)
    assert main(["--help"]) == 0


def test_console_script_help_exits_zero() -> None:
    cp = _run_origenlab_console("--help")
    assert cp.returncode == 0, cp.stderr
    assert "origenlab-email-pipeline" in cp.stdout or "command" in cp.stdout


def test_cli_help_exits_zero() -> None:
    cp = _run_cli("--help")
    assert cp.returncode == 0, cp.stderr
    assert "origenlab-email-pipeline" in cp.stdout or "Operator CLI" in cp.stdout


@pytest.mark.parametrize("name", CLI_COMMAND_NAMES)
def test_subcommand_appears_in_help(name: str) -> None:
    cp = _run_cli("--help")
    assert cp.returncode == 0
    assert name in cp.stdout


@pytest.mark.parametrize("name,rel", SUBCOMMAND_SCRIPTS.items())
def test_script_path_mapping_exists(name: str, rel: str) -> None:
    path = script_path_for(name)
    assert path == repo_root() / rel
    assert path.is_file(), f"missing script for {name}: {path}"


def test_build_subcommand_argv_no_passthrough() -> None:
    argv = build_subcommand_argv("status")
    assert argv[0] == sys.executable
    assert argv[1].endswith("scripts/qa/operator_status.py")
    assert len(argv) == 2


def test_build_subcommand_argv_with_double_dash_passthrough() -> None:
    argv = build_subcommand_argv("status", ["--", "--json"])
    assert argv[-1] == "--json"
    assert "--" not in argv[2:]


def test_build_subcommand_argv_strict_validate() -> None:
    argv = build_subcommand_argv("validate-csvs", ["--strict"])
    assert argv[-1] == "--strict"
    assert "validate_campaign_csvs.py" in argv[1]


@pytest.mark.parametrize("name", PASSTHROUGH_ADVANCED)
def test_advanced_subcommands_preserve_passthrough(name: str) -> None:
    argv = build_subcommand_argv(name, ["--", "--json-out", "/tmp/out.json"])
    assert argv[-2:] == ["--json-out", "/tmp/out.json"]
    assert SUBCOMMAND_SCRIPTS[name] in argv[1].replace("\\", "/")


def test_build_mart_passthrough_rebuild_flag() -> None:
    argv = build_subcommand_argv("build-mart", ["--rebuild"])
    assert argv[-1] == "--rebuild"
    assert argv[1].endswith("scripts/mart/build_business_mart.py")


def test_gmail_ingest_help_always_builds_script_help_only() -> None:
    argv = build_subcommand_argv("gmail-ingest-help")
    assert argv == [
        sys.executable,
        str(repo_root() / "scripts/ingest/05_workspace_gmail_imap_to_sqlite.py"),
        "--help",
    ]
    argv_ignored = build_subcommand_argv("gmail-ingest-help", ["--folder", "INBOX"])
    assert argv_ignored[-1] == "--help"
    assert "INBOX" not in argv_ignored


def test_gmail_ingest_help_rejects_passthrough_in_main(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["gmail-ingest-help", "--", "--folder", "INBOX"])
    err = capsys.readouterr().err
    assert "does not accept extra arguments" in err


def test_gmail_ingest_folders_wrapper_help_no_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "origenlab_email_pipeline.operator_cli.runner.subprocess.run",
        lambda *a, **k: pytest.fail("subprocess must not run for wrapper --help"),
    )
    assert main(["gmail-ingest-folders", "--help"]) == 0
    out = capsys.readouterr().out
    assert "gmail-ingest-folders" in out
    assert "--list-folders" in out


def test_gmail_ingest_help_wrapper_help_no_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "origenlab_email_pipeline.operator_cli.runner.subprocess.run",
        lambda *a, **k: pytest.fail("subprocess must not run for wrapper --help"),
    )
    assert main(["gmail-ingest-help", "--help"]) == 0
    out = capsys.readouterr().out
    assert "gmail-ingest-help" in out
    assert "gmail-ingest" in out


def test_run_gmail_ingest_folders_mocked_list_folders(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0

        return R()

    monkeypatch.setattr("origenlab_email_pipeline.operator_cli.runner.subprocess.run", fake_run)
    from origenlab_email_pipeline.cli import run_subcommand

    assert run_subcommand("gmail-ingest-folders") == 0
    assert len(calls) == 1
    assert calls[0][-1] == "--list-folders"
    assert calls[0][1].endswith("05_workspace_gmail_imap_to_sqlite.py")


def test_normalize_passthrough_strips_leading_separator() -> None:
    assert normalize_passthrough_args(["--", "--json", "--verbose"]) == ["--json", "--verbose"]
    assert normalize_passthrough_args(["--json"]) == ["--json"]


def test_help_only_subcommands_frozenset() -> None:
    assert HELP_ONLY_SUBCOMMANDS == frozenset({"gmail-ingest-help"})


def test_run_subcommand_not_invoked_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wrapper tests must not spawn heavy QA scripts."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0

        return R()

    monkeypatch.setattr("origenlab_email_pipeline.operator_cli.runner.subprocess.run", fake_run)
    from origenlab_email_pipeline.cli import run_subcommand

    assert run_subcommand("check-readiness", ["--help"]) == 0
    assert len(calls) == 1
    assert calls[0][-1] == "--help"
    assert calls[0][1].endswith("check_outbound_readiness.py")


def test_gmail_ingest_builds_two_commands_with_safe_defaults() -> None:
    cmds = build_gmail_ingest_argv_list()
    assert len(cmds) == 2
    for cmd in cmds:
        assert "--skip-duplicate-message-id" in cmd
        assert cmd[1].endswith("05_workspace_gmail_imap_to_sqlite.py")
    assert cmds[0][cmds[0].index("--folder") + 1] == GMAIL_INGEST_INBOX_FOLDER
    assert cmds[1][cmds[1].index("--folder") + 1] == GMAIL_INGEST_SENT_FOLDER


def test_gmail_ingest_passthrough_since_days_on_both() -> None:
    cmds = build_gmail_ingest_argv_list(["--", "--since-days", "14"])
    for cmd in cmds:
        assert "--since-days" in cmd
        assert "14" in cmd


def test_gmail_ingest_rejects_replace_source() -> None:
    with pytest.raises(ValueError, match="replace-source"):
        validate_gmail_ingest_passthrough(["--replace-source"])
    with pytest.raises(SystemExit):
        main(["gmail-ingest", "--", "--replace-source"])


def test_run_gmail_ingest_mocked_runs_inbox_then_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0

        return R()

    monkeypatch.setattr("origenlab_email_pipeline.operator_cli.gmail.subprocess.run", fake_run)
    from origenlab_email_pipeline.cli import run_gmail_ingest

    assert run_gmail_ingest() == 0
    assert len(calls) == 2
    assert calls[0][calls[0].index("--folder") + 1] == GMAIL_INGEST_INBOX_FOLDER
    assert calls[1][calls[1].index("--folder") + 1] == GMAIL_INGEST_SENT_FOLDER


def test_run_gmail_ingest_stops_on_first_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 3 if len(calls) == 1 else 0

        return R()

    monkeypatch.setattr("origenlab_email_pipeline.operator_cli.gmail.subprocess.run", fake_run)
    from origenlab_email_pipeline.cli import run_gmail_ingest

    assert run_gmail_ingest() == 3
    assert len(calls) == 1


def test_mirror_dashboard_default_builds_sync_dry_run() -> None:
    cmds = build_mirror_dashboard_argv_list()
    assert len(cmds) == 1
    sync = cmds[0]
    assert sync[1].endswith(MIRROR_DASHBOARD_SYNC_SCRIPT.replace("/", os.sep))
    assert "--dry-run" in sync
    assert sync.count("--dry-run") == 1


def test_mirror_dashboard_apply_omits_dry_run() -> None:
    sync = build_mirror_dashboard_argv_list(apply=True)[0]
    assert "--dry-run" not in sync
    assert sync[1].endswith("sync_dashboard_postgres_mirror.py")


def test_mirror_dashboard_alembic_apply_builds_alembic_then_sync() -> None:
    cmds = build_mirror_dashboard_argv_list(apply=True, alembic=True)
    assert len(cmds) == 2
    assert cmds[0][:4] == ["alembic", "-c", "alembic.ini", "upgrade"]
    assert cmds[0][4] == "head"
    assert "--dry-run" not in cmds[1]


def test_mirror_dashboard_passthrough_appended_to_sync_only() -> None:
    cmds = build_mirror_dashboard_argv_list(passthrough=["--", "--only", "mart", "--skip-outbound"])
    sync = cmds[-1]
    assert sync[sync.index("--only") :] == ["--only", "mart", "--skip-outbound"]
    if len(cmds) == 2:
        assert "--only" not in cmds[0]


def test_mirror_dashboard_missing_postgres_env_no_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in POSTGRES_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0

        return R()

    monkeypatch.setattr("origenlab_email_pipeline.operator_cli.mirror.subprocess.run", fake_run)
    assert not postgres_url_configured()
    assert run_mirror_dashboard() == 2
    assert calls == []


def test_mirror_dashboard_cloud_only_adds_allow_non_scratch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    monkeypatch.setenv("ORIGENLAB_CLOUD_POSTGRES_URL", "postgresql://u:p@host.example.com/prod")
    assert mirror_dashboard_uses_cloud_postgres_only()
    sync = build_mirror_dashboard_sync_argv(apply=False)
    assert "--allow-non-scratch-postgres" in sync
    assert sync.count("--allow-non-scratch-postgres") == 1


def test_mirror_dashboard_scratch_url_omits_allow_non_scratch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/scratch")
    monkeypatch.setenv("ORIGENLAB_CLOUD_POSTGRES_URL", "postgresql://u:p@host.example.com/prod")
    assert not mirror_dashboard_uses_cloud_postgres_only()
    sync = build_mirror_dashboard_sync_argv(apply=False)
    assert "--allow-non-scratch-postgres" not in sync


def test_mirror_dashboard_accepts_cloud_postgres_env_mocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "ORIGENLAB_CLOUD_POSTGRES_URL",
        "postgresql://u:p@host.example.com/origenlab_dashboard_prod",
    )
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0

        return R()

    monkeypatch.setattr("origenlab_email_pipeline.operator_cli.mirror.subprocess.run", fake_run)
    assert run_mirror_dashboard() == 0
    assert len(calls) == 1
    assert "--dry-run" in calls[0]


def test_mirror_dashboard_with_postgres_env_mocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/scratch")
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0

        return R()

    monkeypatch.setattr("origenlab_email_pipeline.operator_cli.mirror.subprocess.run", fake_run)
    assert run_mirror_dashboard(apply=True, alembic=True) == 0
    assert len(calls) == 2
    assert calls[0][0] == "alembic"
    assert "--dry-run" not in calls[1]


def test_mirror_dashboard_main_rejects_alembic_without_apply(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql://u:p@127.0.0.1:5432/scratch")
    with pytest.raises(SystemExit):
        main(["mirror-dashboard", "--alembic"])
    err = capsys.readouterr().err
    assert "requires --apply" in err


def test_mirror_dashboard_missing_env_via_main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in POSTGRES_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "origenlab_email_pipeline.operator_cli.mirror.subprocess.run",
        lambda *a, **k: pytest.fail("no subprocess"),
    )
    assert main(["mirror-dashboard"]) == 2
    err = capsys.readouterr().err
    assert "ORIGENLAB_POSTGRES_URL" in err or "ALEMBIC_DATABASE_URL" in err
    assert missing_postgres_env_message() in err


def _refresh_opts(**kwargs: object) -> RefreshDashboardOptions:
    return RefreshDashboardOptions(**kwargs)


def test_refresh_dashboard_default_plan_no_runner(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "origenlab_email_pipeline.operator_cli.runner.run_subcommand",
        lambda *a, **k: pytest.fail("run_subcommand must not run for plan-only"),
    )
    assert run_refresh_dashboard(_refresh_opts()) == 0
    out = capsys.readouterr().out
    assert "plan only" in out
    assert "build-mart -- --rebuild" in out
    assert "uv run origenlab refresh-dashboard --apply" in out
    assert "refresh-dashboard--apply" not in out


def test_refresh_dashboard_apply_full_workflow_order() -> None:
    calls: list[tuple[str, list[str] | None, bool]] = []

    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        calls.append((cmd, passthrough, mirror_apply))
        return 0

    opts = _refresh_opts(apply=True)
    assert run_refresh_dashboard(opts, runner=fake_runner) == 0
    assert [c[0] for c in calls] == [
        "gmail-ingest",
        "build-mart",
        "refresh-safety",
        "ndr-review",
        "post-send-digest",
        "status",
        "mirror-dashboard",
    ]
    assert calls[0][1] is None
    assert calls[1][1] == ["--", "--rebuild"]
    assert calls[-1][2] is True


def test_refresh_dashboard_apply_no_mirror_omits_mirror() -> None:
    calls: list[str] = []

    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        calls.append(cmd)
        return 0

    run_refresh_dashboard(_refresh_opts(apply=True, no_mirror=True), runner=fake_runner)
    assert calls[-1] == "status"
    assert "mirror-dashboard" not in calls


def test_refresh_dashboard_apply_mirror_dry_run_no_mirror_apply() -> None:
    calls: list[tuple[str, bool]] = []

    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        calls.append((cmd, mirror_apply))
        return 0

    run_refresh_dashboard(_refresh_opts(apply=True, mirror_dry_run=True), runner=fake_runner)
    assert calls[-1] == ("mirror-dashboard", False)


def test_refresh_dashboard_apply_skip_ingest() -> None:
    calls: list[str] = []

    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        calls.append(cmd)
        return 0

    run_refresh_dashboard(_refresh_opts(apply=True, skip_ingest=True), runner=fake_runner)
    assert calls[0] == "build-mart"
    assert "gmail-ingest" not in calls


def test_refresh_dashboard_apply_since_days_only_on_ingest() -> None:
    calls: list[tuple[str, list[str] | None]] = []

    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        calls.append((cmd, passthrough))
        return 0

    run_refresh_dashboard(_refresh_opts(apply=True, since_days=14), runner=fake_runner)
    assert calls[0] == ("gmail-ingest", ["--", "--since-days", "14"])
    assert all(c[1] != ["--", "--since-days", "14"] for c in calls[1:])


def test_refresh_dashboard_stops_on_first_failure() -> None:
    calls: list[str] = []

    def fake_runner(cmd, passthrough=None, *, mirror_apply=False, mirror_alembic=False):
        calls.append(cmd)
        return 3 if cmd == "build-mart" else 0

    rc = run_refresh_dashboard(_refresh_opts(apply=True), runner=fake_runner)
    assert rc == 3
    assert calls == ["gmail-ingest", "build-mart"]


def test_refresh_dashboard_main_default_no_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "origenlab_email_pipeline.operator_cli.runner.run_subcommand",
        lambda *a, **k: pytest.fail("no subprocess"),
    )
    assert main(["refresh-dashboard"]) == 0
    assert "plan only" in capsys.readouterr().out


def test_refresh_dashboard_build_steps_count() -> None:
    assert len(build_refresh_dashboard_steps(_refresh_opts())) == 7
    assert len(build_refresh_dashboard_steps(_refresh_opts(no_mirror=True))) == 6
    assert len(build_refresh_dashboard_steps(_refresh_opts(skip_ingest=True))) == 6


def test_run_gmail_ingest_help_mocked_only_help(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0

        return R()

    monkeypatch.setattr("origenlab_email_pipeline.operator_cli.runner.subprocess.run", fake_run)
    from origenlab_email_pipeline.cli import run_subcommand

    assert run_subcommand("gmail-ingest-help") == 0
    assert calls[0][-1] == "--help"
    assert calls[0][1].endswith("05_workspace_gmail_imap_to_sqlite.py")
