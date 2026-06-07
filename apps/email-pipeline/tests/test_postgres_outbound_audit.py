from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MOD_PATH = REPO / "src" / "origenlab_email_pipeline" / "postgres_outbound_audit.py"
LEAD_SCRIPT = REPO / "scripts" / "leads" / "export_next_marketing_recipients.py"
ARCHIVE_SCRIPT = REPO / "scripts" / "leads" / "build_archive_send_batch.py"


def _load_mod(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


audit = _load_mod(MOD_PATH, "postgres_outbound_audit")


def test_url_resolution_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", "postgresql+psycopg://u:p@h/db1")
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "postgresql+psycopg://u:p@h/db2")
    assert (
        audit.resolve_postgres_url(None, require_when_requested=True, audit_requested=True)
        == "postgresql://u:p@h/db1"
    )
    assert (
        audit.resolve_postgres_url(
            "postgresql+psycopg://u:p@h/db_explicit",
            require_when_requested=True,
            audit_requested=True,
        )
        == "postgresql://u:p@h/db_explicit"
    )


def test_missing_url_fails_only_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORIGENLAB_POSTGRES_URL", raising=False)
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    assert (
        audit.resolve_postgres_url(None, require_when_requested=True, audit_requested=False)
        is None
    )
    with pytest.raises(audit.OutboundAuditError):
        audit.resolve_postgres_url(None, require_when_requested=True, audit_requested=True)


def test_password_redaction() -> None:
    red = audit.redact_postgres_url("postgresql://user:secret@db.example:5432/name")
    assert "secret" not in red
    assert "***" in red
    assert "db.example:5432" in red


def test_payload_builders() -> None:
    b = audit.build_outbound_batch_payload(
        lane="lead",
        created_by="me",
        gmail_user="contacto@origenlab.cl",
        sent_folders=["[Gmail]/Enviados"],
        sent_preflight_json={"ok": True},
        gate_version="v1",
        output_artifact_path="/tmp/x.csv",
        notes="n",
    )
    assert b.lane == "lead"
    assert b.gate_version == "v1"
    recs = audit.build_outbound_recipient_payloads(
        [
            {
                "email_norm": "A@X.COM",
                "lead_id": 10,
                "source_kind": "lead",
                "source_key": "10",
                "organization_name": "Org",
                "organization_domain": "x.com",
                "metadata_json": {"k": "v"},
            }
        ]
    )
    assert recs[0]["email_norm"] == "a@x.com"
    assert recs[0]["eligibility_result"] == "eligible"


def test_mocked_insert_returns_batch_id(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCur:
        def __init__(self):
            self._q: list[tuple[str, tuple | None]] = []
            self._fetch = [(1,), (1,), (42,)]

        def execute(self, q, p=None):
            self._q.append((q, p))

        def executemany(self, q, rows):
            self._q.append((q, tuple(rows)))

        def fetchone(self):
            return self._fetch.pop(0)

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class FakeConn:
        def __init__(self):
            self.cur = FakeCur()
            self.committed = False

        def cursor(self):
            return self.cur

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

        def close(self):
            pass

    fake_conn = FakeConn()
    monkeypatch.setattr(audit, "psycopg", type("P", (), {"connect": lambda *a, **k: fake_conn}))
    batch = audit.build_outbound_batch_payload(
        lane="lead",
        created_by=None,
        gmail_user="u@x.com",
        sent_folders=["[Gmail]/Enviados"],
        sent_preflight_json={},
    )
    bid = audit.write_postgres_outbound_audit(
        postgres_url="postgresql://u:p@h/db",
        batch=batch,
        recipients=[{"email_norm": "a@x.com", "eligibility_result": "eligible", "metadata_json": {}}],
    )
    assert bid == 42
    assert fake_conn.committed is True


def test_lead_export_calls_audit_when_flag_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lead_mod = _load_mod(LEAD_SCRIPT, "lead_export_script")
    called = {"n": 0}

    class _S:
        n_scanned = 1
        n_sent_folder_recipients = 0
        n_suppressed = 0
        n_outreach_state = 0
        gmail_user = "contacto@origenlab.cl"

    class _P:
        ok = True
        warnings = []

    class _Cfg:
        def resolved_sqlite_path(self):
            return tmp_path / "x.sqlite"

    class _Conn:
        def close(self):
            pass

    monkeypatch.setattr(lead_mod, "load_settings", lambda: _Cfg())
    monkeypatch.setattr(lead_mod, "connect", lambda *_: _Conn())
    monkeypatch.setattr(lead_mod, "ensure_leads_tables", lambda *_: None)
    monkeypatch.setattr(lead_mod, "resolve_outbound_gmail_user", lambda *a, **k: "contacto@origenlab.cl")
    monkeypatch.setattr(lead_mod, "sent_folder_defaults_were_used", lambda *_: True)
    monkeypatch.setattr(lead_mod, "resolve_outbound_sent_folders", lambda *_: ("[Gmail]/Enviados",))
    monkeypatch.setattr(lead_mod, "probe_sent_history", lambda *a, **k: object())
    monkeypatch.setattr(lead_mod, "evaluate_sent_history_preflight", lambda *a, **k: _P())
    monkeypatch.setattr(
        lead_mod,
        "compute_next_marketing_recipients",
        lambda *a, **k: (
            [
                {
                    "case_id": "c1",
                    "id_lead": 11,
                    "contact_email": "a@x.com",
                    "recipient_name": "A",
                    "institution_name": "Org",
                    "sector": "health",
                    "fit_bucket": "high_fit",
                    "priority_score": "9",
                    "already_in_archive_flag": "0",
                    "source_name": "s",
                    "website": "",
                    "evidence_summary": "",
                    "variant_type": "general",
                    "domain": "x.com",
                }
            ],
            _S(),
        ),
    )
    monkeypatch.setattr(lead_mod, "sent_preflight_summary_dict", lambda *_: {"ok": True})
    monkeypatch.setattr(lead_mod, "build_marketing_outreach_seed_body", lambda **_: "x")
    monkeypatch.setattr(lead_mod, "build_outbound_run_envelope", lambda **_: {})

    def _audit(**kwargs):
        called["n"] += 1
        return 123

    monkeypatch.setattr(lead_mod, "maybe_write_postgres_outbound_audit", _audit)

    out_csv = tmp_path / "o.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--out",
            str(out_csv),
            "--write-postgres-audit",
            "--postgres-url",
            "postgresql://u:p@h/db",
        ],
    )
    rc = lead_mod.main()
    assert rc == 2  # less than default limit still returns 2 by existing behavior
    assert called["n"] == 1


def test_lead_export_default_does_not_call_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lead_mod = _load_mod(LEAD_SCRIPT, "lead_export_script_noaudit")
    called = {"n": 0}

    class _S:
        n_scanned = 1
        n_sent_folder_recipients = 0
        n_suppressed = 0
        n_outreach_state = 0
        gmail_user = "contacto@origenlab.cl"

    class _P:
        ok = True
        warnings = []

    class _Cfg:
        def resolved_sqlite_path(self):
            return tmp_path / "x.sqlite"

    class _Conn:
        def close(self):
            pass

    monkeypatch.setattr(lead_mod, "load_settings", lambda: _Cfg())
    monkeypatch.setattr(lead_mod, "connect", lambda *_: _Conn())
    monkeypatch.setattr(lead_mod, "ensure_leads_tables", lambda *_: None)
    monkeypatch.setattr(lead_mod, "resolve_outbound_gmail_user", lambda *a, **k: "contacto@origenlab.cl")
    monkeypatch.setattr(lead_mod, "sent_folder_defaults_were_used", lambda *_: True)
    monkeypatch.setattr(lead_mod, "resolve_outbound_sent_folders", lambda *_: ("[Gmail]/Enviados",))
    monkeypatch.setattr(lead_mod, "probe_sent_history", lambda *a, **k: object())
    monkeypatch.setattr(lead_mod, "evaluate_sent_history_preflight", lambda *a, **k: _P())
    monkeypatch.setattr(
        lead_mod,
        "compute_next_marketing_recipients",
        lambda *a, **k: ([], _S()),
    )
    monkeypatch.setattr(lead_mod, "maybe_write_postgres_outbound_audit", lambda **_: called.__setitem__("n", 1))
    out_csv = tmp_path / "o.csv"
    monkeypatch.setattr(sys, "argv", ["prog", "--out", str(out_csv)])
    rc = lead_mod.main()
    assert rc == 2
    assert called["n"] == 0


def test_archive_export_calls_audit_when_flag_passed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    arc_mod = _load_mod(ARCHIVE_SCRIPT, "archive_export_script")
    called = {"n": 0}

    class _Cfg:
        def resolved_sqlite_path(self):
            return tmp_path / "x.sqlite"

    class _Conn:
        def close(self):
            pass

    class _Result:
        out_dir = tmp_path
        summary = {"sent_preflight": {"ok": True}}

    send_ready = tmp_path / "archive_outreach_send_ready.csv"
    send_ready.write_text(
        "contact_email,organization_name,domain,final_decision_path,candidate_tier,contact_name\n"
        "a@x.com,Org,x.com,eligible,tier1,A\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(arc_mod, "load_settings", lambda: _Cfg())
    monkeypatch.setattr(arc_mod, "connect", lambda *_: _Conn())
    monkeypatch.setattr(arc_mod, "resolve_outbound_gmail_user", lambda *a, **k: "contacto@origenlab.cl")
    monkeypatch.setattr(arc_mod, "sent_folder_defaults_were_used", lambda *_: True)
    monkeypatch.setattr(arc_mod, "resolve_outbound_sent_folders", lambda *_: ("[Gmail]/Enviados",))
    monkeypatch.setattr(arc_mod, "build_archive_send_batch", lambda **_: _Result())

    def _audit(**kwargs):
        called["n"] += 1
        return 77

    monkeypatch.setattr(arc_mod, "maybe_write_postgres_outbound_audit", _audit)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--out-dir",
            str(tmp_path),
            "--build-batch",
            "--write-postgres-audit",
            "--postgres-url",
            "postgresql://u:p@h/db",
        ],
    )
    rc = arc_mod.main()
    assert rc == 0
    assert called["n"] == 1


def test_archive_export_default_does_not_call_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    arc_mod = _load_mod(ARCHIVE_SCRIPT, "archive_export_script_noaudit")
    called = {"n": 0}

    class _Cfg:
        def resolved_sqlite_path(self):
            return tmp_path / "x.sqlite"

    class _Conn:
        def close(self):
            pass

    class _Result:
        out_dir = tmp_path
        summary = {"sent_preflight": {"ok": True}}

    monkeypatch.setattr(arc_mod, "load_settings", lambda: _Cfg())
    monkeypatch.setattr(arc_mod, "connect", lambda *_: _Conn())
    monkeypatch.setattr(arc_mod, "resolve_outbound_gmail_user", lambda *a, **k: "contacto@origenlab.cl")
    monkeypatch.setattr(arc_mod, "sent_folder_defaults_were_used", lambda *_: True)
    monkeypatch.setattr(arc_mod, "resolve_outbound_sent_folders", lambda *_: ("[Gmail]/Enviados",))
    monkeypatch.setattr(arc_mod, "build_archive_send_batch", lambda **_: _Result())
    monkeypatch.setattr(arc_mod, "maybe_write_postgres_outbound_audit", lambda **_: called.__setitem__("n", 1))
    monkeypatch.setattr(sys, "argv", ["prog", "--out-dir", str(tmp_path)])
    rc = arc_mod.main()
    assert rc == 0
    assert called["n"] == 0


@pytest.mark.skipif(
    not os.environ.get("ORIGENLAB_POSTGRES_TEST_URL"),
    reason="Set ORIGENLAB_POSTGRES_TEST_URL for optional integration test.",
)
def test_optional_integration_url_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORIGENLAB_POSTGRES_URL", os.environ["ORIGENLAB_POSTGRES_TEST_URL"])
    url = audit.resolve_postgres_url(None, require_when_requested=True, audit_requested=True)
    assert isinstance(url, str)
    assert url.startswith("postgresql://")

