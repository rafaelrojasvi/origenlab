#!/usr/bin/env python3
"""Run canonical DeepSearch/outbound workflow on reports/out/active/current."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

BLOCKED_MATCH_TYPES = {
    "exact_lead_email_sent",
    "exact_researched_email_sent",
    "exact_pending_email_sent",
    "exact_lead_email_state",
    "exact_researched_email_state",
    "exact_pending_email_state",
    "suppression_email",
    "suppression_domain",
}
MANUAL_REVIEW_MATCH_TYPES = {
    "same_domain_contacted",
    "possible_org_name_match",
}


def _run_py(
    script_rel: str,
    args: list[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(cwd / script_rel), *args]
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False, timeout=600)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def _parse_json_stdout(stdout: str) -> dict[str, object]:
    s = (stdout or "").strip()
    if not s:
        return {}
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Try first JSON object lines only.
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start : end + 1])
    return {}


def _stage_prepare(args, *, repo_root: Path) -> int:
    current_dir = Path(args.reports_out_dir) / "active" / "current"
    prepare_args = ["--campaign-slug", args.campaign_slug]
    if args.operator:
        prepare_args += ["--operator", args.operator]
    if args.archive_existing:
        prepare_args.append("--archive-existing")
    prepare_args += ["--reports-out-dir", str(Path(args.reports_out_dir))]
    run = _run_py("scripts/qa/prepare_outbound_campaign_workspace.py", prepare_args, cwd=repo_root)
    if run.returncode != 0:
        sys.stderr.write(run.stderr or run.stdout)
        return run.returncode

    queue_path = current_dir / "research_queue.csv"
    export_args = ["--out", str(queue_path), "--limit", str(int(args.queue_limit))]
    if args.db:
        export_args += ["--db", str(Path(args.db))]
    run2 = _run_py("scripts/leads/export_lead_contact_research_queue.py", export_args, cwd=repo_root)
    if run2.returncode != 0:
        sys.stderr.write(run2.stderr or run2.stdout)
        return run2.returncode
    print(run.stdout.strip())
    if run2.stdout.strip():
        print(run2.stdout.strip())
    print("Upload research_queue.csv to DeepSearch, then save output as reviewed_deepsearch.csv")
    print(f"research_queue: {queue_path}")
    print(f"reviewed_deepsearch target: {current_dir / 'reviewed_deepsearch.csv'}")
    return 0


def _split_reviewed_by_overlap(
    reviewed_rows: list[dict[str, str]],
    overlap_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    overlap_by_id = {
        str(r.get("lead_id") or "").strip(): str(r.get("match_type") or "").strip()
        for r in overlap_rows
        if str(r.get("lead_id") or "").strip()
    }
    safe: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []
    manual: list[dict[str, str]] = []
    for row in reviewed_rows:
        lid = str(row.get("lead_id") or "").strip()
        mt = overlap_by_id.get(lid, "")
        if mt in BLOCKED_MATCH_TYPES:
            blocked.append(row)
        elif mt in MANUAL_REVIEW_MATCH_TYPES:
            manual.append(row)
        else:
            safe.append(row)
    return safe, blocked, manual


def _stage_process_reviewed(args, *, repo_root: Path) -> int:
    current_dir = Path(args.reports_out_dir) / "active" / "current"
    reviewed = current_dir / "reviewed_deepsearch.csv"
    if not reviewed.is_file():
        print(f"Missing required file: {reviewed}", file=sys.stderr)
        print("Save reviewed DeepSearch output to reviewed_deepsearch.csv, then rerun.", file=sys.stderr)
        return 2
    validate_args = [
        "--file",
        str(reviewed),
        "--kind",
        "reviewed_deepsearch",
        "--strict",
    ]
    val = _run_py("scripts/qa/validate_campaign_csvs.py", validate_args, cwd=repo_root)
    if val.returncode != 0:
        sys.stderr.write(val.stderr or val.stdout)
        return val.returncode
    if val.stdout.strip():
        print(val.stdout.strip())

    overlap_out = current_dir / "overlap_audit.csv"
    overlap_args = ["--out", str(overlap_out), "--input-research-csv", str(reviewed)]
    if args.db:
        overlap_args += ["--db", str(Path(args.db))]
    run_overlap = _run_py("scripts/qa/export_contacted_lead_overlap_audit.py", overlap_args, cwd=repo_root)
    if run_overlap.returncode != 0:
        sys.stderr.write(run_overlap.stderr or run_overlap.stdout)
        return run_overlap.returncode

    reviewed_rows = _read_csv_rows(reviewed)
    overlap_rows = _read_csv_rows(overlap_out)
    safe_rows, blocked_rows, manual_rows = _split_reviewed_by_overlap(reviewed_rows, overlap_rows)
    if reviewed_rows:
        fieldnames = list(reviewed_rows[0].keys())
    else:
        fieldnames = [
            "lead_id",
            "org_name",
            "resolved_domain",
            "resolved_contact_email",
            "resolved_contact_name",
            "contact_source_url",
            "source_type",
            "confidence",
            "notes",
        ]
    safe_path = current_dir / "reviewed_safe_to_import.csv"
    blocked_path = current_dir / "reviewed_blocked_already_contacted.csv"
    manual_path = current_dir / "reviewed_needs_manual_review.csv"
    _write_csv(safe_path, safe_rows, fieldnames)
    _write_csv(blocked_path, blocked_rows, fieldnames)
    _write_csv(manual_path, manual_rows, fieldnames)

    import_base = ["--input", str(safe_path)]
    if args.db:
        import_base += ["--db", str(Path(args.db))]
    dry = _run_py("scripts/leads/import_lead_contact_research_csv.py", import_base, cwd=repo_root)
    if dry.returncode != 0:
        sys.stderr.write(dry.stderr or dry.stdout)
        return dry.returncode
    dry_payload = _parse_json_stdout(dry.stdout)
    imported_rows = 0
    if args.apply:
        apply_args = [*import_base, "--apply"]
        if args.operator:
            apply_args += ["--updated-by", args.operator]
        app = _run_py("scripts/leads/import_lead_contact_research_csv.py", apply_args, cwd=repo_root)
        if app.returncode != 0:
            sys.stderr.write(app.stderr or app.stdout)
            return app.returncode
        app_payload = _parse_json_stdout(app.stdout)
        imported_rows = int(((app_payload.get("summary") or {}).get("applied")) or 0)

    gate_out = current_dir / "gate_audit.csv"
    gate_args = ["--out", str(gate_out), "--lane", "lead", "--limit", str(int(args.gate_limit))]
    if args.db:
        gate_args += ["--db", str(Path(args.db))]
    gate = _run_py("scripts/qa/export_gate_audit_csv.py", gate_args, cwd=repo_root)
    if gate.returncode != 0:
        sys.stderr.write(gate.stderr or gate.stdout)
        return gate.returncode

    send_ready = current_dir / "send_ready.csv"
    send_args = [
        "--out",
        str(send_ready),
        "--limit",
        str(int(args.send_limit)),
        "--fetch-cap",
        str(int(args.fetch_cap)),
        "--write-outbound-summary",
    ]
    if args.db:
        send_args += ["--db", str(Path(args.db))]
    send = _run_py("scripts/leads/export_next_marketing_recipients.py", send_args, cwd=repo_root)
    if send.returncode not in (0, 2):
        sys.stderr.write(send.stderr or send.stdout)
        return send.returncode

    gate_rows = _read_csv_rows(gate_out)
    eligible_gate_rows = sum(1 for r in gate_rows if str(r.get("final_eligible") or "") == "1")
    send_rows = _read_csv_rows(send_ready)
    uniq_recipients = len(
        {
            str(r.get("contact_email") or "").strip().lower()
            for r in send_rows
            if str(r.get("contact_email") or "").strip()
        }
    )
    pending_count = len(reviewed_rows)
    skipped_blocked = len(blocked_rows)
    manual_count = len(manual_rows)
    if not args.apply:
        imported_rows = int(((dry_payload.get("summary") or {}).get("upsert_candidates")) or 0)

    print("Process-reviewed summary")
    print(f"pending rows scanned: {pending_count}")
    print(f"already contacted skipped: {skipped_blocked}")
    print(f"manual review count: {manual_count}")
    print(f"imported rows: {imported_rows}")
    print(f"eligible gate rows: {eligible_gate_rows}")
    print(f"send_ready unique recipients: {uniq_recipients}")
    print(f"send_ready path: {send_ready}")
    print(f"overlap_audit path: {overlap_out}")
    print(f"gate_audit path: {gate_out}")
    return 0


def _stage_post_send(args, *, repo_root: Path) -> int:
    current_dir = Path(args.reports_out_dir) / "active" / "current"
    send_ready = current_dir / "send_ready.csv"
    if not send_ready.is_file():
        print(f"Missing required file: {send_ready}", file=sys.stderr)
        return 2
    send_rows = _read_csv_rows(send_ready)
    if not send_rows:
        print("send_ready.csv has 0 rows; refusing to mark contacted.", file=sys.stderr)
        return 2
    validate_args = [
        "--file",
        str(send_ready),
        "--kind",
        "send_ready",
        "--strict",
    ]
    val = _run_py("scripts/qa/validate_campaign_csvs.py", validate_args, cwd=repo_root)
    if val.returncode != 0:
        sys.stderr.write(val.stderr or val.stdout)
        return val.returncode

    out_json = current_dir / "mark_contacted_result.json"
    mark_args = [
        "--batch-file",
        str(send_ready),
        "--source",
        str(args.source or "").strip(),
        "--updated-by",
        str(args.operator or "run_current_campaign_pipeline.py"),
        "--json-out",
        str(out_json),
    ]
    if args.db:
        mark_args += ["--db", str(Path(args.db))]
    mark = _run_py("scripts/leads/mark_sent_batch_contacted.py", mark_args, cwd=repo_root)
    if mark.returncode != 0:
        sys.stderr.write(mark.stderr or mark.stdout)
        return mark.returncode

    if args.ingest_sent:
        folder_values = args.sent_folder or ["[Gmail]/Enviados"]
        for folder in folder_values:
            ingest_args = ["--folder", folder]
            if args.db:
                ingest_args += ["--db", str(Path(args.db))]
            ingest = _run_py("scripts/ingest/05_workspace_gmail_imap_to_sqlite.py", ingest_args, cwd=repo_root)
            if ingest.returncode != 0:
                sys.stderr.write(ingest.stderr or ingest.stdout)
                return ingest.returncode
            if ingest.stdout.strip():
                print(ingest.stdout.strip())

    print(f"mark_contacted_result: {out_json}")
    print(f"send_ready: {send_ready}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", required=True, choices=("prepare", "process-reviewed", "post-send"))
    ap.add_argument("--campaign-slug", default="", help="Required for --stage prepare.")
    ap.add_argument("--operator", default="", help="Operator string for manifests/imports.")
    ap.add_argument("--archive-existing", action="store_true", help="Archive existing active/current on prepare.")
    ap.add_argument("--queue-limit", type=int, default=50)
    ap.add_argument("--gate-limit", type=int, default=5000)
    ap.add_argument("--send-limit", type=int, default=200)
    ap.add_argument("--fetch-cap", type=int, default=4000)
    ap.add_argument("--apply", action="store_true", help="Apply reviewed import (otherwise dry-run only).")
    ap.add_argument("--source", default="", help="Required for --stage post-send.")
    ap.add_argument("--ingest-sent", action="store_true", help="Run Gmail Sent ingest after post-send mark.")
    ap.add_argument("--sent-folder", action="append", default=[], help="Folder(s) for optional --ingest-sent.")
    ap.add_argument("--db", type=Path, default=None, help="Optional SQLite path forwarded to subcommands.")
    ap.add_argument(
        "--reports-out-dir",
        type=Path,
        default=_ROOT / "reports" / "out",
        help="Reports out root (default: <repo>/reports/out).",
    )
    args = ap.parse_args(argv)

    repo_root = _ROOT
    if args.stage == "prepare":
        if not str(args.campaign_slug).strip():
            print("--campaign-slug is required for --stage prepare", file=sys.stderr)
            return 2
        return _stage_prepare(args, repo_root=repo_root)
    if args.stage == "process-reviewed":
        return _stage_process_reviewed(args, repo_root=repo_root)
    if args.stage == "post-send":
        if not str(args.source).strip():
            print("--source is required for --stage post-send", file=sys.stderr)
            return 2
        return _stage_post_send(args, repo_root=repo_root)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

