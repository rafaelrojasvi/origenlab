from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from origenlab_email_pipeline.core import research_automation as ra


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def test_prompt_rendering() -> None:
    seeds = ra.SeedPaths(
        do_not_repeat_master=Path("/tmp/dnr.csv"),
        outreach_contacted_all=Path("/tmp/contacted.csv"),
        all_known_marketing_contacts_dedup=Path("/tmp/known.csv"),
    )
    text = ra.render_prompt(
        template_text="sector={sector} limit={limit_hint} dnr={dnr_path}",
        sector="broad",
        limit_hint=25,
        seed_paths=seeds,
    )
    assert "sector=broad" in text
    assert "limit=25" in text
    assert "dnr=/tmp/dnr.csv" in text


def test_extract_csv_parsing_from_model_output() -> None:
    txt = (
        "foo\n```csv\ninstitution_name,region,city,type,contact_email,contact_label,source_url,confidence,fit_signal\n"
        "A,RM,Santiago,universidad,a@x.cl,lab,https://x.cl,high,fit\n```\nbar"
    )
    csv_text = ra.extract_csv_text_from_model_output(txt)
    fields, rows = ra.parse_csv_rows(csv_text)
    assert fields == ra.EXPECTED_COLUMNS
    assert rows[0]["contact_email"] == "a@x.cl"


def test_extract_csv_with_prose_and_bom() -> None:
    txt = (
        "\ufeffResult follows.\n"
        "institution_name,region,city,type,contact_email,contact_label,source_url,confidence,fit_signal\n"
        "A,RM,Santiago,universidad,a@x.cl,lab,https://x.cl,high,fit\n"
        "Thanks."
    )
    csv_text = ra.extract_csv_text_from_model_output(txt)
    fields, rows = ra.parse_csv_rows(csv_text)
    assert fields == ra.EXPECTED_COLUMNS
    assert len(rows) == 1


def test_malformed_schema_failure() -> None:
    bad = (
        "institution_name,region,city,type,contact_email,contact_label,source_url,confidence\n"
        "A,RM,Santiago,universidad,a@x.cl,lab,https://x.cl,high\n"
    )
    try:
        ra.parse_csv_rows(bad)
        assert False, "Expected ValueError for missing fit_signal"
    except ValueError as exc:
        assert "missing required columns" in str(exc).lower()


def test_path_resolution(tmp_path: Path) -> None:
    out = ra.resolve_out_dir(out_dir=tmp_path / "abc")
    assert out == (tmp_path / "abc").resolve()


def test_local_exclusion_behavior(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.csv"
    _write_csv(
        candidates,
        ["institution_name", "contact_email"],
        [["A", "a@x.cl"], ["B", "b@x.cl"], ["C", "c@x.cl"]],
    )
    dnr = tmp_path / "do_not_repeat_master.csv"
    _write_csv(dnr, ["email_norm"], [["a@x.cl"]])
    contacted = tmp_path / "outreach_contacted_all.csv"
    _write_csv(contacted, ["contact_email"], [["b@x.cl"]])
    known = tmp_path / "all_known_marketing_contacts_dedup.csv"
    _write_csv(known, ["contact_email"], [["c@x.cl"]])
    seeds = ra.SeedPaths(dnr, contacted, known)
    netnew = tmp_path / "netnew.csv"
    excluded = tmp_path / "excluded.csv"
    summary = ra.run_local_exclusion(
        candidates_csv=candidates,
        seed_paths=seeds,
        out_netnew_csv=netnew,
        out_excluded_csv=excluded,
    )
    assert summary["total_candidates"] == 3
    assert summary["excluded_count"] == 3
    assert summary["netnew_count"] == 0
    ex_rows = list(csv.DictReader(excluded.open(encoding="utf-8", newline="")))
    reasons = {r["contact_email"]: r["exclusion_reason"] for r in ex_rows}
    assert reasons["a@x.cl"] == "dnr_match"
    assert reasons["b@x.cl"] == "contacted_match"
    assert reasons["c@x.cl"] == "known_marketing_match"


def test_review_summary_generation(tmp_path: Path) -> None:
    send_ready = tmp_path / "send_ready_marketing.csv"
    _write_csv(
        send_ready,
        ["institution_name", "contact_email", "contact_label", "type"],
        [["Inst A", "lab@a.cl", "lab", "universidad"], ["Inst B", "oficina@b.cl", "oficina_partes", "instituto"]],
    )
    blocked = tmp_path / "blocked.csv"
    _write_csv(blocked, ["contact_email"], [["x@y.cl"]])
    summary_json = tmp_path / "summary.json"
    summary_json.write_text(
        json.dumps({"counts": {"blocked": 1, "needs_manual_review": 0, "send_ready_marketing": 2}}),
        encoding="utf-8",
    )
    artifacts = ra.RunArtifacts(
        out_dir=tmp_path,
        raw_response_json=tmp_path / "raw_response.json",
        raw_response_txt=tmp_path / "raw_response.txt",
        candidates_raw_csv=tmp_path / "raw.csv",
        candidates_netnew_csv=tmp_path / "netnew.csv",
        candidates_excluded_csv=tmp_path / "excluded.csv",
        validation_json=tmp_path / "validation_result.json",
        review_summary_md=tmp_path / "review_summary.md",
        run_metadata_json=tmp_path / "run_metadata.json",
        process_workspace=tmp_path / "ws",
    )
    text = ra.build_review_summary_markdown(
        exclusion_summary={"total_candidates": 5, "excluded_count": 1, "netnew_count": 4, "excluded": []},
        send_ready_csv=send_ready,
        blocked_csv=blocked,
        summary_json_path=summary_json,
        netnew_csv=tmp_path / "netnew.csv",
        output_paths=artifacts,
        prompt_file=tmp_path / "prompt.txt",
        sector="broad",
        limits={
            "limits_triggered": True,
            "truncation_applied": True,
            "max_candidates": 200,
            "max_send_ready": 50,
            "send_ready_over_limit": False,
        },
    )
    assert "Ready for review; no live send performed." in text
    assert "Top institutions" in text
    assert "Prompt file" in text
    assert "Truncation applied" in text


def test_dry_run_no_send_safety(tmp_path: Path, monkeypatch) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("sector={sector} limit={limit_hint}", encoding="utf-8")
    sample = tmp_path / "sample.txt"
    sample.write_text(
        "```csv\ninstitution_name,region,city,type,contact_email,contact_label,source_url,confidence,fit_signal\n"
        "A,RM,Santiago,universidad,a@x.cl,lab,https://x.cl,high,fit\n```",
        encoding="utf-8",
    )
    dnr = tmp_path / "do_not_repeat_master.csv"
    _write_csv(dnr, ["email_norm"], [])
    contacted = tmp_path / "outreach_contacted_all.csv"
    _write_csv(contacted, ["contact_email"], [])
    known = tmp_path / "all_known_marketing_contacts_dedup.csv"
    _write_csv(known, ["contact_email"], [])
    seeds = ra.SeedPaths(dnr, contacted, known)

    def _fake_run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        if "process_broad_marketing_contacts.py" in " ".join(args):
            ws = Path(args[args.index("--workspace") + 1])
            _write_csv(
                ws / "send_ready_marketing.csv",
                [
                    "case_id",
                    "contact_email",
                    "email_source",
                    "institution_name",
                    "region",
                    "city",
                    "type",
                    "contact_label",
                    "source_url",
                    "confidence",
                    "fit_signal",
                    "variant_type",
                ],
                [["MKT-00001", "a@x.cl", "marketing_contacts", "A", "RM", "Santiago", "universidad", "lab", "https://x.cl", "high", "fit", "broad_marketing"]],
            )
            _write_csv(
                ws / "marketing_blocked_already_known.csv",
                ["institution_name", "contact_email", "block_reason"],
                [],
            )
            _write_csv(
                ws / "marketing_needs_manual_review.csv",
                ["institution_name", "contact_email", "review_reason"],
                [],
            )
            _write_csv(
                ws / "marketing_safe_to_send.csv",
                ["institution_name", "contact_email"],
                [["A", "a@x.cl"]],
            )
            (ws / "marketing_contacts_summary.json").write_text(
                json.dumps(
                    {
                        "counts": {
                            "input_rows": 1,
                            "safe_to_send": 1,
                            "blocked": 0,
                            "needs_manual_review": 0,
                            "send_ready_marketing": 1,
                        }
                    }
                ),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(ra, "_run_subprocess", _fake_run)
    artifacts = ra.run_research_automation(
        model="o4-mini-deep-research",
        prompt_file=prompt,
        out_dir=tmp_path / "out",
        sector="broad",
        limit_hint=5,
        dry_run=True,
        sample_response=sample,
        seed_paths=seeds,
        use_background=False,
        app_root=Path(__file__).resolve().parents[1],
        max_candidates=200,
        max_send_ready=50,
        fail_on_over_limit=False,
        run_contacted_coverage_check=False,
        strict_contacted_coverage=False,
    )
    meta = json.loads(artifacts.run_metadata_json.read_text(encoding="utf-8"))
    assert meta["safety"]["gmail_send_called"] is False
    assert meta["safety"]["sqlite_mutation_intended"] is False
    assert meta["dry_run"] is True
    assert meta["max_candidates"] == 200
    assert meta["max_send_ready"] == 50
    assert "output_directory" in meta
    assert "Ready for review; no live send performed." in artifacts.review_summary_md.read_text(encoding="utf-8")


def test_candidate_limit_truncation(tmp_path: Path, monkeypatch) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("sector={sector} limit={limit_hint}", encoding="utf-8")
    sample = tmp_path / "sample.txt"
    sample.write_text(
        "```csv\ninstitution_name,region,city,type,contact_email,contact_label,source_url,confidence,fit_signal\n"
        "A,RM,Santiago,universidad,a1@x.cl,lab,https://x.cl,high,fit\n"
        "B,RM,Santiago,universidad,a2@x.cl,lab,https://x.cl,high,fit\n"
        "C,RM,Santiago,universidad,a3@x.cl,lab,https://x.cl,high,fit\n```",
        encoding="utf-8",
    )
    dnr = tmp_path / "do_not_repeat_master.csv"
    _write_csv(dnr, ["email_norm"], [])
    contacted = tmp_path / "outreach_contacted_all.csv"
    _write_csv(contacted, ["contact_email"], [])
    known = tmp_path / "all_known_marketing_contacts_dedup.csv"
    _write_csv(known, ["contact_email"], [])
    seeds = ra.SeedPaths(dnr, contacted, known)

    def _fake_run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        if "process_broad_marketing_contacts.py" in " ".join(args):
            ws = Path(args[args.index("--workspace") + 1])
            _write_csv(
                ws / "send_ready_marketing.csv",
                [
                    "case_id",
                    "contact_email",
                    "email_source",
                    "institution_name",
                    "region",
                    "city",
                    "type",
                    "contact_label",
                    "source_url",
                    "confidence",
                    "fit_signal",
                    "variant_type",
                ],
                [["MKT-00001", "a1@x.cl", "marketing_contacts", "A", "RM", "Santiago", "universidad", "lab", "https://x.cl", "high", "fit", "broad_marketing"]],
            )
            _write_csv(ws / "marketing_blocked_already_known.csv", ["contact_email"], [])
            _write_csv(ws / "marketing_needs_manual_review.csv", ["contact_email"], [])
            _write_csv(ws / "marketing_safe_to_send.csv", ["contact_email"], [["a1@x.cl"]])
            (ws / "marketing_contacts_summary.json").write_text(
                json.dumps({"counts": {"send_ready_marketing": 1, "blocked": 0, "needs_manual_review": 0}}),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(ra, "_run_subprocess", _fake_run)
    artifacts = ra.run_research_automation(
        model="o4-mini-deep-research",
        prompt_file=prompt,
        out_dir=tmp_path / "out",
        sector="broad",
        limit_hint=10,
        dry_run=True,
        sample_response=sample,
        seed_paths=seeds,
        use_background=False,
        app_root=Path(__file__).resolve().parents[1],
        max_candidates=2,
        max_send_ready=50,
        fail_on_over_limit=False,
        run_contacted_coverage_check=False,
        strict_contacted_coverage=False,
    )
    meta = json.loads(artifacts.run_metadata_json.read_text(encoding="utf-8"))
    assert meta["truncation_applied"] is True
    assert meta["candidate_count"] == 2


def test_fail_on_over_limit_behavior(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("sector={sector} limit={limit_hint}", encoding="utf-8")
    sample = tmp_path / "sample.txt"
    sample.write_text(
        "```csv\ninstitution_name,region,city,type,contact_email,contact_label,source_url,confidence,fit_signal\n"
        "A,RM,Santiago,universidad,a1@x.cl,lab,https://x.cl,high,fit\n"
        "B,RM,Santiago,universidad,a2@x.cl,lab,https://x.cl,high,fit\n```",
        encoding="utf-8",
    )
    dnr = tmp_path / "do_not_repeat_master.csv"
    _write_csv(dnr, ["email_norm"], [])
    contacted = tmp_path / "outreach_contacted_all.csv"
    _write_csv(contacted, ["contact_email"], [])
    known = tmp_path / "all_known_marketing_contacts_dedup.csv"
    _write_csv(known, ["contact_email"], [])
    seeds = ra.SeedPaths(dnr, contacted, known)
    try:
        ra.run_research_automation(
            model="o4-mini-deep-research",
            prompt_file=prompt,
            out_dir=tmp_path / "out",
            sector="broad",
            limit_hint=10,
            dry_run=True,
            sample_response=sample,
            seed_paths=seeds,
            use_background=False,
            app_root=Path(__file__).resolve().parents[1],
            max_candidates=1,
            max_send_ready=50,
            fail_on_over_limit=True,
            run_contacted_coverage_check=False,
            strict_contacted_coverage=False,
        )
        assert False, "Expected over-limit failure"
    except RuntimeError as exc:
        assert "max-candidates" in str(exc)


def test_cli_help() -> None:
    repo = Path(__file__).resolve().parents[1]
    script = repo / "scripts" / "research" / "run_deep_research_prospecting.py"
    cp = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 0
    assert "dry-run" in cp.stdout
    assert "--max-candidates" in cp.stdout
    assert "--day-rotation" in cp.stdout
    assert "--run-contacted-coverage-check" in cp.stdout


def test_day_rotation_mapping() -> None:
    assert ra.resolve_sector_for_day_rotation(weekday=0) == "broad"
    assert ra.resolve_sector_for_day_rotation(weekday=1) == "water_env"
    assert ra.resolve_sector_for_day_rotation(weekday=2) == "universities_regional"
    assert ra.resolve_sector_for_day_rotation(weekday=3) == "hospitals_clinical"
    assert ra.resolve_sector_for_day_rotation(weekday=4) == "industry_qc"
    assert ra.resolve_sector_for_day_rotation(weekday=5) == "thin_regions"


def test_contacted_coverage_hook_non_strict(tmp_path: Path, monkeypatch) -> None:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("sector={sector} limit={limit_hint}", encoding="utf-8")
    sample = tmp_path / "sample.txt"
    sample.write_text(
        "```csv\ninstitution_name,region,city,type,contact_email,contact_label,source_url,confidence,fit_signal\n"
        "A,RM,Santiago,universidad,a@x.cl,lab,https://x.cl,high,fit\n```",
        encoding="utf-8",
    )
    dnr = tmp_path / "do_not_repeat_master.csv"
    _write_csv(dnr, ["email_norm"], [])
    contacted = tmp_path / "outreach_contacted_all.csv"
    _write_csv(contacted, ["contact_email"], [])
    known = tmp_path / "all_known_marketing_contacts_dedup.csv"
    _write_csv(known, ["contact_email"], [])
    seeds = ra.SeedPaths(dnr, contacted, known)

    def _fake_run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        cmd = " ".join(args)
        if "validate_contacted_csv_coverage.py" in cmd:
            out = Path(args[args.index("--json-out") + 1])
            out.write_text('{"ok": true}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=args, returncode=3, stdout="coverage warning", stderr="")
        if "process_broad_marketing_contacts.py" in cmd:
            ws = Path(args[args.index("--workspace") + 1])
            _write_csv(
                ws / "send_ready_marketing.csv",
                [
                    "case_id",
                    "contact_email",
                    "email_source",
                    "institution_name",
                    "region",
                    "city",
                    "type",
                    "contact_label",
                    "source_url",
                    "confidence",
                    "fit_signal",
                    "variant_type",
                ],
                [["MKT-00001", "a@x.cl", "marketing_contacts", "A", "RM", "Santiago", "universidad", "lab", "https://x.cl", "high", "fit", "broad_marketing"]],
            )
            _write_csv(ws / "marketing_blocked_already_known.csv", ["contact_email"], [])
            _write_csv(ws / "marketing_needs_manual_review.csv", ["contact_email"], [])
            _write_csv(ws / "marketing_safe_to_send.csv", ["contact_email"], [["a@x.cl"]])
            (ws / "marketing_contacts_summary.json").write_text(
                json.dumps({"counts": {"send_ready_marketing": 1, "blocked": 0, "needs_manual_review": 0}}),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(ra, "_run_subprocess", _fake_run)
    artifacts = ra.run_research_automation(
        model="o4-mini-deep-research",
        prompt_file=prompt,
        out_dir=tmp_path / "out",
        sector="broad",
        limit_hint=5,
        dry_run=True,
        sample_response=sample,
        seed_paths=seeds,
        use_background=False,
        app_root=Path(__file__).resolve().parents[1],
        max_candidates=200,
        max_send_ready=50,
        fail_on_over_limit=False,
        run_contacted_coverage_check=True,
        strict_contacted_coverage=False,
    )
    meta = json.loads(artifacts.run_metadata_json.read_text(encoding="utf-8"))
    assert meta["contacted_coverage_check"]["enabled"] is True
    assert meta["contacted_coverage_check"]["returncode"] == 3

