from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


def _load_mod():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "leads" / "run_current_campaign_pipeline.py"
    spec = importlib.util.spec_from_file_location("run_current_campaign_pipeline", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _RunResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_prepare_stage_creates_expected_paths(tmp_path: Path) -> None:
    mod = _load_mod()
    reports_out = tmp_path / "reports" / "out"
    current = reports_out / "active" / "current"
    calls: list[tuple[str, list[str]]] = []

    def fake_run(script_rel: str, args: list[str], *, cwd: Path):
        calls.append((script_rel, args))
        if script_rel.endswith("prepare_outbound_campaign_workspace.py"):
            current.mkdir(parents=True, exist_ok=True)
            (current / "campaign_manifest.json").write_text("{}", encoding="utf-8")
            return _RunResult(0, "ok")
        if script_rel.endswith("export_lead_contact_research_queue.py"):
            out = Path(args[args.index("--out") + 1])
            _write_csv(out, [], ["lead_id"])
            return _RunResult(0, "queue")
        return _RunResult(0, "")

    mod._run_py = fake_run
    rc = mod.main(
        [
            "--stage",
            "prepare",
            "--campaign-slug",
            "q2_hospitales_labs_02",
            "--operator",
            "rafael",
            "--queue-limit",
            "50",
            "--archive-existing",
            "--reports-out-dir",
            str(reports_out),
        ]
    )
    assert rc == 0
    assert (current / "research_queue.csv").exists()
    assert any("prepare_outbound_campaign_workspace.py" in c[0] for c in calls)
    assert any("export_lead_contact_research_queue.py" in c[0] for c in calls)


def test_process_reviewed_fails_when_missing_reviewed_csv(tmp_path: Path) -> None:
    mod = _load_mod()
    reports_out = tmp_path / "reports" / "out"
    rc = mod.main(
        [
            "--stage",
            "process-reviewed",
            "--reports-out-dir",
            str(reports_out),
        ]
    )
    assert rc == 2


def test_process_reviewed_dry_run_does_not_apply_import(tmp_path: Path) -> None:
    mod = _load_mod()
    reports_out = tmp_path / "reports" / "out"
    current = reports_out / "active" / "current"
    current.mkdir(parents=True, exist_ok=True)
    reviewed = current / "reviewed_deepsearch.csv"
    _write_csv(
        reviewed,
        [
            {
                "lead_id": "1",
                "org_name": "Org",
                "resolved_domain": "org.cl",
                "resolved_contact_email": "a@org.cl",
                "resolved_contact_name": "A",
                "contact_source_url": "https://org.cl",
                "source_type": "website",
                "confidence": "high",
                "notes": "",
            }
        ],
        [
            "lead_id",
            "org_name",
            "resolved_domain",
            "resolved_contact_email",
            "resolved_contact_name",
            "contact_source_url",
            "source_type",
            "confidence",
            "notes",
        ],
    )
    calls: list[tuple[str, list[str]]] = []

    def fake_run(script_rel: str, args: list[str], *, cwd: Path):
        calls.append((script_rel, args))
        if script_rel.endswith("export_contacted_lead_overlap_audit.py"):
            out = Path(args[args.index("--out") + 1])
            _write_csv(
                out,
                [{"lead_id": "1", "match_type": "same_domain_contacted"}],
                ["lead_id", "match_type"],
            )
            return _RunResult(0, "overlap")
        if script_rel.endswith("import_lead_contact_research_csv.py"):
            payload = {"summary": {"upsert_candidates": 0, "applied": 0}}
            return _RunResult(0, json.dumps(payload))
        if script_rel.endswith("export_gate_audit_csv.py"):
            out = Path(args[args.index("--out") + 1])
            _write_csv(out, [{"final_eligible": "0"}], ["final_eligible"])
            return _RunResult(0, "gate")
        if script_rel.endswith("export_next_marketing_recipients.py"):
            out = Path(args[args.index("--out") + 1])
            _write_csv(out, [], ["contact_email"])
            return _RunResult(2, "warn")
        return _RunResult(0, "")

    mod._run_py = fake_run
    rc = mod.main(
        [
            "--stage",
            "process-reviewed",
            "--operator",
            "rafael",
            "--reports-out-dir",
            str(reports_out),
        ]
    )
    assert rc == 0
    import_calls = [c for c in calls if c[0].endswith("import_lead_contact_research_csv.py")]
    assert len(import_calls) == 1
    assert "--apply" not in import_calls[0][1]


def test_post_send_fails_if_send_ready_missing_or_empty(tmp_path: Path) -> None:
    mod = _load_mod()
    reports_out = tmp_path / "reports" / "out"
    rc_missing = mod.main(
        [
            "--stage",
            "post-send",
            "--source",
            "camp_01",
            "--reports-out-dir",
            str(reports_out),
        ]
    )
    assert rc_missing == 2
    current = reports_out / "active" / "current"
    current.mkdir(parents=True, exist_ok=True)
    _write_csv(current / "send_ready.csv", [], ["contact_email"])
    rc_empty = mod.main(
        [
            "--stage",
            "post-send",
            "--source",
            "camp_01",
            "--reports-out-dir",
            str(reports_out),
        ]
    )
    assert rc_empty == 2


def test_paths_are_under_active_current(tmp_path: Path) -> None:
    mod = _load_mod()
    reports_out = tmp_path / "reports" / "out"
    current = reports_out / "active" / "current"
    current.mkdir(parents=True, exist_ok=True)
    _write_csv(
        current / "reviewed_deepsearch.csv",
        [],
        [
            "lead_id",
            "org_name",
            "resolved_domain",
            "resolved_contact_email",
            "resolved_contact_name",
            "contact_source_url",
            "source_type",
            "confidence",
            "notes",
        ],
    )
    captured_paths: list[Path] = []

    def fake_run(script_rel: str, args: list[str], *, cwd: Path):
        if "--out" in args:
            captured_paths.append(Path(args[args.index("--out") + 1]))
            out = Path(args[args.index("--out") + 1])
            if script_rel.endswith("export_contacted_lead_overlap_audit.py"):
                _write_csv(out, [], ["lead_id", "match_type"])
            elif script_rel.endswith("export_gate_audit_csv.py"):
                _write_csv(out, [], ["final_eligible"])
            elif script_rel.endswith("export_next_marketing_recipients.py"):
                _write_csv(out, [], ["contact_email"])
        if script_rel.endswith("import_lead_contact_research_csv.py"):
            return _RunResult(0, json.dumps({"summary": {"upsert_candidates": 0, "applied": 0}}))
        return _RunResult(0, "")

    mod._run_py = fake_run
    rc = mod.main(["--stage", "process-reviewed", "--reports-out-dir", str(reports_out)])
    assert rc == 0
    assert captured_paths
    assert all(str(p).startswith(str(current)) for p in captured_paths)


def test_wrapper_process_reviewed_fails_before_import_on_invalid_reviewed(tmp_path: Path) -> None:
    mod = _load_mod()
    reports_out = tmp_path / "reports" / "out"
    current = reports_out / "active" / "current"
    current.mkdir(parents=True, exist_ok=True)
    _write_csv(
        current / "reviewed_deepsearch.csv",
        [{"lead_id": "x"}],
        ["lead_id"],
    )
    calls: list[str] = []

    def fake_run(script_rel: str, args: list[str], *, cwd: Path):
        calls.append(script_rel)
        if script_rel.endswith("validate_campaign_csvs.py"):
            return _RunResult(1, "", "invalid")
        return _RunResult(0, "")

    mod._run_py = fake_run
    rc = mod.main(["--stage", "process-reviewed", "--reports-out-dir", str(reports_out)])
    assert rc == 1
    # must fail before overlap/import/export
    assert not any(s.endswith("import_lead_contact_research_csv.py") for s in calls)


def test_wrapper_post_send_fails_on_invalid_send_ready_via_validator(tmp_path: Path) -> None:
    mod = _load_mod()
    reports_out = tmp_path / "reports" / "out"
    current = reports_out / "active" / "current"
    current.mkdir(parents=True, exist_ok=True)
    _write_csv(
        current / "send_ready.csv",
        [{"contact_email": "bad@@x", "id_lead": "1", "institution_name": "Org", "email_source": "lead_master"}],
        ["contact_email", "id_lead", "institution_name", "email_source"],
    )

    def fake_run(script_rel: str, args: list[str], *, cwd: Path):
        if script_rel.endswith("validate_campaign_csvs.py"):
            return _RunResult(1, "", "invalid send_ready")
        return _RunResult(0, "")

    mod._run_py = fake_run
    rc = mod.main(
        [
            "--stage",
            "post-send",
            "--source",
            "camp_1",
            "--reports-out-dir",
            str(reports_out),
        ]
    )
    assert rc == 1

