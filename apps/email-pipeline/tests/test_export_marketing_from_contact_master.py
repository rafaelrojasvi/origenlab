"""CLI tests for export_marketing_from_contact_master (audit-only default)."""

from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "leads" / "advanced" / "export_marketing_from_contact_master.py"


class _FakeGateContext:
    supplier_domains: frozenset[str] = frozenset({"supplier.example"})


class _Eligible:
    eligible = True
    reasons: list[str] = []


def _load_script():
    spec = importlib.util.spec_from_file_location("export_marketing_from_contact_master", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_rows(n: int = 1):
    for i in range(n):
        yield (
            f"buyer{i}@cliente.cl",
            f"Contact {i}",
            f"Org {i}",
            3,
            "2026-01-15T12:00:00+00:00",
            0.85,
        )


class _FakeCursor:
    description = [
        ("contact_email",),
        ("recipient_name",),
        ("institution_name",),
        ("total_emails",),
        ("last_seen_at",),
        ("confidence_score",),
    ]

    def __init__(self, n: int = 1) -> None:
        self._rows = list(_fake_rows(n))

    def __iter__(self):
        return iter(self._rows)


class _FakeConn:
    def __init__(self, n: int = 1) -> None:
        self._n = n

    def execute(self, sql, params):
        return _FakeCursor(self._n)

    def close(self) -> None:
        pass


def _install_mocks(monkeypatch: pytest.MonkeyPatch, mod, *, rows: int = 1) -> None:
    settings = SimpleNamespace(
        gmail_workspace_user="contacto@origenlab.cl",
        resolved_sqlite_path=lambda: Path("/tmp/unused.sqlite"),
    )

    monkeypatch.setattr(mod, "load_settings", lambda: settings)
    monkeypatch.setattr(mod, "connect", lambda *_a, **_k: _FakeConn(rows))
    monkeypatch.setattr(mod, "build_marketing_export_gate_context", lambda *_a, **_k: _FakeGateContext())
    monkeypatch.setattr(mod, "load_sent_recipient_norms", lambda *_a, **_k: {"sent@cliente.cl"})
    monkeypatch.setattr(mod, "load_suppressed_norms", lambda *_a, **_k: {"blocked@cliente.cl"})
    monkeypatch.setattr(mod, "load_outreach_state_map", lambda *_a, **_k: {"snoozed@cliente.cl": "snoozed"})
    monkeypatch.setattr(mod, "evaluate_export_eligibility", lambda **_k: _Eligible())
    monkeypatch.setattr(
        mod,
        "build_marketing_outreach_seed_body",
        lambda **_k: "seed body",
    )


def _run_main(mod, argv: list[str]) -> tuple[int | None, str, str]:
    old = sys.argv
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    code: int | None = 0
    try:
        sys.argv = argv
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            code = mod.main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = old
    return code, out_buf.getvalue(), err_buf.getvalue()


def test_default_audit_only_does_not_write_and_prints_export_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load_script()
    _install_mocks(monkeypatch, mod)
    out_csv = tmp_path / "summary.csv"
    code, stdout, _stderr = _run_main(
        mod,
        ["prog", "--db", str(tmp_path / "t.sqlite"), "--limit", "1", "--out", str(out_csv)],
    )
    assert code == 0
    assert not out_csv.is_file()
    assert "Audit only: pass --export to write marketing CSVs." in stdout
    assert "--export" in stdout
    assert "candidates kept=1" in stdout


def test_out_without_export_does_not_write_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_script()
    _install_mocks(monkeypatch, mod)
    out_csv = tmp_path / "planned.csv"
    _run_main(
        mod,
        ["prog", "--limit", "1", "--out", str(out_csv)],
    )
    assert not out_csv.is_file()


def test_export_out_writes_summary_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_script()
    _install_mocks(monkeypatch, mod)
    out_csv = tmp_path / "summary.csv"
    code, stdout, _stderr = _run_main(
        mod,
        ["prog", "--limit", "1", "--export", "--out", str(out_csv)],
    )
    assert code == 0
    assert out_csv.is_file()
    text = out_csv.read_text(encoding="utf-8")
    assert "contact_email" in text
    assert "buyer0@cliente.cl" in text
    assert "Wrote 1 rows to" in stdout


def test_export_out_pilot_csv_writes_both_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_script()
    _install_mocks(monkeypatch, mod)
    out_csv = tmp_path / "summary.csv"
    pilot_csv = tmp_path / "pilot.csv"
    code, stdout, _stderr = _run_main(
        mod,
        [
            "prog",
            "--limit",
            "1",
            "--export",
            "--out",
            str(out_csv),
            "--pilot-csv",
            str(pilot_csv),
        ],
    )
    assert code == 0
    assert out_csv.is_file()
    assert pilot_csv.is_file()
    assert "Pilot CSV:" in stdout
    assert "seed body" in pilot_csv.read_text(encoding="utf-8")


def test_pilot_csv_without_export_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_script()
    _install_mocks(monkeypatch, mod)
    pilot_csv = tmp_path / "pilot.csv"
    code, _stdout, stderr = _run_main(
        mod,
        ["prog", "--limit", "1", "--pilot-csv", str(pilot_csv)],
    )
    assert code == 2
    assert "--pilot-csv requires --export" in stderr
    assert not pilot_csv.is_file()


def test_export_without_out_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_script()
    _install_mocks(monkeypatch, mod)
    code, _stdout, stderr = _run_main(
        mod,
        ["prog", "--limit", "1", "--export"],
    )
    assert code == 2
    assert "--export requires --out" in stderr
