"""Deep research automation for review-ready marketing prospect batches.

Safety: this module intentionally stops before any live send or post-send actions.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openai import OpenAI

from origenlab_email_pipeline.config import load_settings

DEFAULT_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "deep_research_netnew_chile_marketing.txt"
)
DEFAULT_REPORTS_ACTIVE = Path(__file__).resolve().parents[3] / "reports" / "out" / "active"


@dataclass(frozen=True)
class SeedPaths:
    do_not_repeat_master: Path
    outreach_contacted_all: Path
    all_known_marketing_contacts_dedup: Path


@dataclass(frozen=True)
class RunArtifacts:
    out_dir: Path
    raw_response_json: Path
    raw_response_txt: Path
    candidates_raw_csv: Path
    candidates_netnew_csv: Path
    candidates_excluded_csv: Path
    validation_json: Path
    review_summary_md: Path
    run_metadata_json: Path
    process_workspace: Path


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_seed_paths(reports_active: Path | None = None) -> SeedPaths:
    root = (reports_active or DEFAULT_REPORTS_ACTIVE).resolve()
    return SeedPaths(
        do_not_repeat_master=root / "current" / "do_not_repeat_master.csv",
        outreach_contacted_all=root / "outreach_contacted_all.csv",
        all_known_marketing_contacts_dedup=root / "all_known_marketing_contacts_dedup.csv",
    )


def resolve_out_dir(*, out_dir: Path | None, reports_active: Path | None = None) -> Path:
    if out_dir is not None:
        return out_dir.resolve()
    root = (reports_active or DEFAULT_REPORTS_ACTIVE).resolve()
    stamp = _utc_now().strftime("%Y%m%d_%H%M%S")
    return (root / "current" / "research_automation" / stamp).resolve()


def load_prompt_template(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Prompt template is empty: {path}")
    return text


def render_prompt(
    *,
    template_text: str,
    sector: str,
    limit_hint: int | None,
    seed_paths: SeedPaths,
) -> str:
    lim = str(limit_hint) if limit_hint is not None else "40"
    return template_text.format(
        sector=sector,
        limit_hint=lim,
        dnr_path=str(seed_paths.do_not_repeat_master),
        contacted_path=str(seed_paths.outreach_contacted_all),
        known_marketing_path=str(seed_paths.all_known_marketing_contacts_dedup),
    )


def _response_output_text(resp: Any) -> str:
    out_text = str(getattr(resp, "output_text", "") or "").strip()
    if out_text:
        return out_text
    output = getattr(resp, "output", None) or []
    chunks: list[str] = []
    for item in output:
        if getattr(item, "type", "") != "message":
            continue
        for c in getattr(item, "content", []) or []:
            txt = getattr(c, "text", "")
            if txt:
                chunks.append(str(txt))
    return "\n\n".join(chunks).strip()


def _response_to_json(resp: Any) -> str:
    if hasattr(resp, "model_dump_json"):
        return str(resp.model_dump_json(indent=2))
    if hasattr(resp, "to_dict"):
        return json.dumps(resp.to_dict(), ensure_ascii=False, indent=2)
    return json.dumps({"repr": repr(resp)}, ensure_ascii=False, indent=2)


def run_deep_research_response(
    *,
    client: OpenAI,
    model: str,
    prompt_text: str,
    seed_paths: SeedPaths,
    use_background: bool,
    poll_seconds: float = 3.0,
) -> tuple[str, str, dict[str, str]]:
    missing = [str(p) for p in seed_paths.__dict__.values() if not Path(p).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing seed files for model input: {', '.join(missing)}")

    uploaded: dict[str, str] = {}
    for key, path in seed_paths.__dict__.items():
        with Path(path).open("rb") as f:
            up = client.files.create(file=f, purpose="user_data")
        uploaded[key] = str(up.id)

    content = [{"type": "input_text", "text": prompt_text}]
    for fid in uploaded.values():
        content.append({"type": "input_file", "file_id": fid})

    resp = client.responses.create(
        model=model,
        input=[{"role": "user", "content": content}],
        tools=[{"type": "web_search"}],
        background=bool(use_background),
    )

    if use_background:
        rid = str(getattr(resp, "id", "") or "")
        if not rid:
            raise RuntimeError("Background response missing response id")
        while True:
            status = str(getattr(resp, "status", "") or "")
            if status in {"completed", "failed", "cancelled", "incomplete"}:
                break
            time.sleep(max(0.5, poll_seconds))
            resp = client.responses.retrieve(rid)
        final_status = str(getattr(resp, "status", "") or "")
        if final_status != "completed":
            raise RuntimeError(f"Deep research response did not complete successfully: status={final_status}")

    return _response_to_json(resp), _response_output_text(resp), uploaded


def extract_csv_text_from_model_output(text: str) -> str:
    s = str(text or "")
    fenced = re.search(r"```csv\s*(.*?)```", s, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        body = fenced.group(1).strip()
        if body:
            return body + "\n"

    lines = [ln.rstrip("\n") for ln in s.splitlines()]
    header_idx = -1
    for i, ln in enumerate(lines):
        lower = ln.strip().lower()
        if "institution_name" in lower and "contact_email" in lower and "," in ln:
            header_idx = i
            break
    if header_idx < 0:
        raise ValueError("Could not find candidate CSV header in model output.")

    block: list[str] = []
    for ln in lines[header_idx:]:
        t = ln.strip()
        if not t:
            if block:
                break
            continue
        if "," not in ln:
            if block:
                break
            continue
        block.append(ln)
    if len(block) < 2:
        raise ValueError("Candidate CSV extraction found header but no data rows.")
    return "\n".join(block).strip() + "\n"


def parse_csv_rows(csv_text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    fields = [str(f) for f in (reader.fieldnames or [])]
    if not fields:
        raise ValueError("Extracted CSV has no header row.")
    rows = [{k: str(v or "") for k, v in row.items()} for row in reader]
    return fields, rows


def write_csv(path: Path, *, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def _load_email_set(path: Path, key: str) -> set[str]:
    if not path.is_file():
        return set()
    out: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            v = str(row.get(key, "")).strip().lower()
            if v:
                out.add(v)
    return out


def run_local_exclusion(
    *,
    candidates_csv: Path,
    seed_paths: SeedPaths,
    out_netnew_csv: Path,
    out_excluded_csv: Path,
) -> dict[str, Any]:
    with candidates_csv.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        fields = [str(c) for c in (r.fieldnames or [])]
        rows = [{k: str(v or "") for k, v in row.items()} for row in r]

    dnr = _load_email_set(seed_paths.do_not_repeat_master, "email_norm")
    contacted = _load_email_set(seed_paths.outreach_contacted_all, "contact_email")
    known = _load_email_set(seed_paths.all_known_marketing_contacts_dedup, "contact_email")

    netnew: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    excluded_info: list[dict[str, str]] = []
    for row in rows:
        email = str(row.get("contact_email", "")).strip().lower()
        reasons: list[str] = []
        if email in dnr:
            reasons.append("dnr_match")
        if email in contacted:
            reasons.append("contacted_match")
        if email in known:
            reasons.append("known_marketing_match")
        if reasons:
            reason = "multiple" if len(reasons) > 1 else reasons[0]
            ex = dict(row)
            ex["exclusion_reason"] = reason
            excluded.append(ex)
            excluded_info.append({"contact_email": email, "exclusion_reason": reason})
        else:
            netnew.append(dict(row))

    write_csv(out_netnew_csv, fieldnames=fields, rows=netnew)
    write_csv(out_excluded_csv, fieldnames=[*fields, "exclusion_reason"], rows=excluded)

    return {
        "total_candidates": len(rows),
        "excluded_count": len(excluded),
        "netnew_count": len(netnew),
        "excluded": excluded_info,
    }


def _run_subprocess(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(cwd / "src")}
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def _read_csv_dicts(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k: str(v or "") for k, v in row.items()} for row in csv.DictReader(f)]


def build_review_summary_markdown(
    *,
    exclusion_summary: dict[str, Any],
    send_ready_csv: Path,
    blocked_csv: Path,
    summary_json_path: Path,
    netnew_csv: Path,
    output_paths: RunArtifacts,
) -> str:
    send_rows = _read_csv_dicts(send_ready_csv)
    blocked_rows = _read_csv_dicts(blocked_csv)
    net_rows = _read_csv_dicts(netnew_csv)
    summary_json: dict[str, Any] = {}
    if summary_json_path.is_file():
        summary_json = json.loads(summary_json_path.read_text(encoding="utf-8"))

    domain_counts: dict[str, int] = {}
    inst_counts: dict[str, int] = {}
    generic_flags: list[str] = []
    for row in send_rows:
        email = str(row.get("contact_email", "")).strip().lower()
        dom = email.split("@", 1)[1] if "@" in email else ""
        if dom:
            domain_counts[dom] = domain_counts.get(dom, 0) + 1
        inst = str(row.get("institution_name", "")).strip()
        if inst:
            inst_counts[inst] = inst_counts.get(inst, 0) + 1
        label = str(row.get("contact_label", "")).strip().lower()
        typ = str(row.get("type", "")).strip().lower()
        if any(k in label for k in ("general", "admis", "direccion", "secretaria", "oficina_partes")) or typ in {
            "instituto",
            "gobierno",
        }:
            generic_flags.append(email)

    def _top_n(d: dict[str, int], n: int = 8) -> list[str]:
        return [k for k, _ in sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:n]]

    counts = summary_json.get("counts", {})
    blocked = int(counts.get("blocked", len(blocked_rows)))
    review = int(counts.get("needs_manual_review", 0))
    send_ready = int(counts.get("send_ready_marketing", len(send_rows)))
    lines = [
        "# Deep Research automation review summary",
        "",
        f"- Total candidates: **{int(exclusion_summary.get('total_candidates', 0))}**",
        f"- Excluded locally: **{int(exclusion_summary.get('excluded_count', 0))}**",
        f"- Net-new candidates: **{int(exclusion_summary.get('netnew_count', len(net_rows)))}**",
        f"- Send-ready count: **{send_ready}**",
        f"- Blocked count: **{blocked}**",
        f"- Review count: **{review}**",
        "",
        "## Top institutions",
    ]
    for name in _top_n(inst_counts):
        lines.append(f"- {name}")
    lines.extend(["", "## Top domains"])
    for dom in _top_n(domain_counts):
        lines.append(f"- {dom}")
    lines.extend(
        [
            "",
            "## Flagged generic/public-sector contacts",
            *(f"- {em}" for em in sorted(set(generic_flags))[:30]),
            "",
            "## Next files to review",
            f"- `{output_paths.candidates_raw_csv}`",
            f"- `{output_paths.candidates_netnew_csv}`",
            f"- `{output_paths.candidates_excluded_csv}`",
            f"- `{send_ready_csv}`",
            f"- `{blocked_csv}`",
            f"- `{summary_json_path}`",
            "",
            "Ready for review; no live send performed.",
            "",
        ]
    )
    return "\n".join(lines)


def run_research_automation(
    *,
    model: str,
    prompt_file: Path,
    out_dir: Path,
    sector: str,
    limit_hint: int | None,
    dry_run: bool,
    sample_response: Path | None,
    seed_paths: SeedPaths,
    use_background: bool,
    app_root: Path,
) -> RunArtifacts:
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = RunArtifacts(
        out_dir=out_dir,
        raw_response_json=out_dir / "raw_response.json",
        raw_response_txt=out_dir / "raw_response.txt",
        candidates_raw_csv=out_dir / "candidates_raw.csv",
        candidates_netnew_csv=out_dir / "candidates_netnew.csv",
        candidates_excluded_csv=out_dir / "candidates_excluded.csv",
        validation_json=out_dir / "validation_result.json",
        review_summary_md=out_dir / "review_summary.md",
        run_metadata_json=out_dir / "run_metadata.json",
        process_workspace=out_dir / "process_workspace",
    )
    artifacts.process_workspace.mkdir(parents=True, exist_ok=True)

    prompt_text = render_prompt(
        template_text=load_prompt_template(prompt_file),
        sector=sector,
        limit_hint=limit_hint,
        seed_paths=seed_paths,
    )
    uploaded_file_ids: dict[str, str] = {}
    if dry_run:
        if sample_response is None or not sample_response.is_file():
            raise ValueError("--dry-run requires --sample-response PATH to an existing file.")
        raw_text = sample_response.read_text(encoding="utf-8")
        raw_json = json.dumps({"mode": "dry_run_sample", "sample_response_path": str(sample_response)}, indent=2)
    else:
        settings = load_settings()
        api_key = (
            (settings.resolved_tatiana_openai_api_key() or "").strip()
            or (os.environ.get("OPENAI_API_KEY") or "").strip()
        )
        if not api_key:
            raise RuntimeError("Missing OPENAI_API_KEY (or ORIGENLAB_TATIANA_OPENAI_API_KEY) for live research.")
        client = OpenAI(api_key=api_key)
        raw_json, raw_text, uploaded_file_ids = run_deep_research_response(
            client=client,
            model=model,
            prompt_text=prompt_text,
            seed_paths=seed_paths,
            use_background=use_background,
        )

    artifacts.raw_response_json.write_text(raw_json, encoding="utf-8")
    artifacts.raw_response_txt.write_text(raw_text, encoding="utf-8")

    csv_text = extract_csv_text_from_model_output(raw_text)
    fieldnames, rows = parse_csv_rows(csv_text)
    write_csv(artifacts.candidates_raw_csv, fieldnames=fieldnames, rows=rows)

    exclusion = run_local_exclusion(
        candidates_csv=artifacts.candidates_raw_csv,
        seed_paths=seed_paths,
        out_netnew_csv=artifacts.candidates_netnew_csv,
        out_excluded_csv=artifacts.candidates_excluded_csv,
    )

    validate_cp = _run_subprocess(
        [
            "scripts/qa/validate_campaign_csvs.py",
            "--file",
            str(artifacts.candidates_netnew_csv),
            "--kind",
            "marketing_contacts",
            "--strict",
        ],
        cwd=app_root,
    )
    validation_payload = {
        "returncode": validate_cp.returncode,
        "stdout": validate_cp.stdout,
        "stderr": validate_cp.stderr,
    }
    artifacts.validation_json.write_text(
        json.dumps(validation_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if validate_cp.returncode != 0:
        raise RuntimeError(
            "Validation failed for candidates_netnew.csv. See validation_result.json for exact errors."
        )

    process_cp = _run_subprocess(
        [
            "scripts/leads/process_broad_marketing_contacts.py",
            "--workspace",
            str(artifacts.process_workspace),
            "--master",
            str(seed_paths.do_not_repeat_master),
            "--input",
            str(artifacts.candidates_netnew_csv),
        ],
        cwd=app_root,
    )
    if process_cp.returncode != 0:
        raise RuntimeError(
            "Processing failed for net-new candidates. "
            f"stdout={process_cp.stdout}\nstderr={process_cp.stderr}"
        )

    send_ready = artifacts.process_workspace / "send_ready_marketing.csv"
    blocked = artifacts.process_workspace / "marketing_blocked_already_known.csv"
    summary = artifacts.process_workspace / "marketing_contacts_summary.json"
    review_md = build_review_summary_markdown(
        exclusion_summary=exclusion,
        send_ready_csv=send_ready,
        blocked_csv=blocked,
        summary_json_path=summary,
        netnew_csv=artifacts.candidates_netnew_csv,
        output_paths=artifacts,
    )
    artifacts.review_summary_md.write_text(review_md, encoding="utf-8")

    metadata = {
        "generated_at": _utc_now().isoformat().replace("+00:00", "Z"),
        "mode": "dry_run" if dry_run else "live_research_no_send",
        "sector": sector,
        "limit_hint": limit_hint,
        "model": model,
        "prompt_file": str(prompt_file.resolve()),
        "seed_paths": {k: str(v) for k, v in asdict(seed_paths).items()},
        "uploaded_file_ids": uploaded_file_ids,
        "artifacts": {k: str(v) for k, v in asdict(artifacts).items()},
        "exclusion_summary": exclusion,
        "stop_message": "Ready for review; no live send performed.",
        "safety": {
            "gmail_send_called": False,
            "mark_contacted_called": False,
            "sent_ingest_called": False,
            "dnr_refresh_after_send_called": False,
            "sqlite_mutation_intended": False,
        },
    }
    artifacts.run_metadata_json.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifacts


__all__ = [
    "DEFAULT_PROMPT_PATH",
    "RunArtifacts",
    "SeedPaths",
    "build_review_summary_markdown",
    "default_seed_paths",
    "extract_csv_text_from_model_output",
    "load_prompt_template",
    "parse_csv_rows",
    "render_prompt",
    "resolve_out_dir",
    "run_local_exclusion",
    "run_research_automation",
    "write_csv",
]
