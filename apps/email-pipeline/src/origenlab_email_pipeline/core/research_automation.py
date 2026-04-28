"""Deep research automation for review-ready marketing prospect batches.

Safety: this module intentionally stops before any live send or post-send actions.
"""

from __future__ import annotations

import csv
import io
import json
import os
import random
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
SECTOR_CHOICES = (
    "broad",
    "water_env",
    "universities_regional",
    "hospitals_clinical",
    "industry_qc",
    "thin_regions",
    "custom",
)
EXPECTED_COLUMNS = [
    "institution_name",
    "region",
    "city",
    "type",
    "contact_email",
    "contact_label",
    "source_url",
    "confidence",
    "fit_signal",
]
_HEADER_ALIASES = {
    "institution": "institution_name",
    "institutionname": "institution_name",
    "institucion": "institution_name",
    "contacto_email": "contact_email",
    "email": "contact_email",
    "correo": "contact_email",
    "label": "contact_label",
    "contact": "contact_label",
    "source": "source_url",
    "url": "source_url",
    "fit": "fit_signal",
    "fit_notes": "fit_signal",
}


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
    prompt_preview_txt: Path
    api_error_json: Path
    api_error_txt: Path
    retry_attempts_json: Path
    process_workspace: Path


class DeepResearchApiError(RuntimeError):
    def __init__(self, *, message: str, code: str, status: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable


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
    compact_seed_files: dict[str, Path],
) -> str:
    lim = str(limit_hint) if limit_hint is not None else "40"
    return template_text.format(
        sector=sector,
        limit_hint=lim,
        canonical_dnr_path=str(compact_seed_files["canonical_dnr_path"]),
        seed_known_institutions_path=str(compact_seed_files["seed_known_institutions"]),
        seed_known_domains_path=str(compact_seed_files["seed_known_domains"]),
        seed_recent_contacted_emails_sample_path=str(compact_seed_files["seed_recent_contacted_emails_sample"]),
        seed_exclusion_summary_path=str(compact_seed_files["seed_exclusion_summary"]),
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


def _extract_response_error(resp: Any) -> tuple[str, str]:
    payload: dict[str, Any] = {}
    if hasattr(resp, "model_dump"):
        payload = resp.model_dump()
    elif hasattr(resp, "to_dict"):
        payload = resp.to_dict()
    err = payload.get("error") or {}
    code = str(err.get("code") or "").strip().lower()
    msg = str(err.get("message") or "").strip()
    return code, msg


def _is_retryable_error(*, code: str, status: str) -> bool:
    if status in {"cancelled"}:
        return False
    retryable_codes = {
        "rate_limit_exceeded",
        "server_error",
        "temporarily_unavailable",
        "service_unavailable",
        "timeout",
    }
    return code in retryable_codes


def run_deep_research_response(
    *,
    client: OpenAI,
    model: str,
    prompt_text: str,
    seed_input_files: dict[str, Path],
    use_background: bool,
    poll_seconds: float = 3.0,
) -> tuple[str, str, dict[str, str]]:
    missing = [str(p) for p in seed_input_files.values() if not Path(p).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing seed files for model input: {', '.join(missing)}")

    uploaded: dict[str, str] = {}
    for key, path in seed_input_files.items():
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
            code, msg = _extract_response_error(resp)
            retryable = _is_retryable_error(code=code, status=final_status)
            raise DeepResearchApiError(
                message=(
                    f"Deep research response did not complete successfully: "
                    f"status={final_status}, code={code or 'unknown'}, message={msg or 'n/a'}"
                ),
                code=code or "unknown",
                status=final_status,
                retryable=retryable,
            )

    return _response_to_json(resp), _response_output_text(resp), uploaded


def _extract_email_and_institution(path: Path) -> tuple[list[tuple[str, str]], set[str]]:
    pairs: list[tuple[str, str]] = []
    emails: set[str] = set()
    if not path.is_file():
        return pairs, emails
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            em = str(row.get("email_norm") or row.get("contact_email") or "").strip().lower()
            if not em:
                continue
            emails.add(em)
            inst = str(row.get("institution_name") or "").strip()
            if inst:
                pairs.append((em, inst))
    return pairs, emails


def _domain(email: str) -> str:
    em = str(email or "").strip().lower()
    return em.split("@", 1)[1] if "@" in em else ""


def build_compact_seed_artifacts(
    *,
    out_dir: Path,
    seed_paths: SeedPaths,
    max_seed_email_sample: int,
    max_seed_institutions: int,
    max_seed_domains: int,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    seed_known_institutions = out_dir / "seed_known_institutions.csv"
    seed_known_domains = out_dir / "seed_known_domains.csv"
    seed_recent_contacted_emails_sample = out_dir / "seed_recent_contacted_emails_sample.csv"
    seed_exclusion_summary = out_dir / "seed_exclusion_summary.json"

    dnr_pairs, dnr_emails = _extract_email_and_institution(seed_paths.do_not_repeat_master)
    contacted_pairs, contacted_emails = _extract_email_and_institution(seed_paths.outreach_contacted_all)
    known_pairs, known_emails = _extract_email_and_institution(seed_paths.all_known_marketing_contacts_dedup)
    all_emails = sorted(dnr_emails | contacted_emails | known_emails)

    inst_counts: dict[str, int] = {}
    for _, inst in [*dnr_pairs, *contacted_pairs, *known_pairs]:
        if inst:
            inst_counts[inst] = inst_counts.get(inst, 0) + 1
    top_institutions = sorted(inst_counts.items(), key=lambda kv: kv[1], reverse=True)[: max(1, max_seed_institutions)]

    dom_counts: dict[str, int] = {}
    for em in all_emails:
        dom = _domain(em)
        if dom:
            dom_counts[dom] = dom_counts.get(dom, 0) + 1
    top_domains = sorted(dom_counts.items(), key=lambda kv: kv[1], reverse=True)[: max(1, max_seed_domains)]

    sample_emails = all_emails[: max(1, max_seed_email_sample)]

    write_csv(
        seed_known_institutions,
        fieldnames=["institution_name", "frequency"],
        rows=[{"institution_name": name, "frequency": str(freq)} for name, freq in top_institutions],
    )
    write_csv(
        seed_known_domains,
        fieldnames=["domain", "frequency"],
        rows=[{"domain": dom, "frequency": str(freq)} for dom, freq in top_domains],
    )
    write_csv(
        seed_recent_contacted_emails_sample,
        fieldnames=["contact_email"],
        rows=[{"contact_email": em} for em in sample_emails],
    )
    summary_payload = {
        "canonical_dnr_path": str(seed_paths.do_not_repeat_master.resolve()),
        "total_do_not_repeat_size": len(dnr_emails),
        "total_contacted_size": len(contacted_emails),
        "total_known_marketing_size": len(known_emails),
        "sampled_contacted_emails_count": len(sample_emails),
        "top_repeated_institutions": [{"institution_name": k, "frequency": v} for k, v in top_institutions[:20]],
        "top_repeated_domains": [{"domain": k, "frequency": v} for k, v in top_domains[:20]],
        "note": "These are compact summaries/samples. Final exact exclusion runs locally after research.",
    }
    seed_exclusion_summary.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "canonical_dnr_path": seed_paths.do_not_repeat_master.resolve(),
        "seed_known_institutions": seed_known_institutions.resolve(),
        "seed_known_domains": seed_known_domains.resolve(),
        "seed_recent_contacted_emails_sample": seed_recent_contacted_emails_sample.resolve(),
        "seed_exclusion_summary": seed_exclusion_summary.resolve(),
        "counts": {
            "dnr_total": len(dnr_emails),
            "contacted_total": len(contacted_emails),
            "known_total": len(known_emails),
            "sample_email_count": len(sample_emails),
            "institution_rows": len(top_institutions),
            "domain_rows": len(top_domains),
        },
    }


def extract_csv_text_from_model_output(text: str) -> str:
    s = str(text or "").lstrip("\ufeff")
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
    clean = str(csv_text or "").lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(clean))
    fields = [str(f or "") for f in (reader.fieldnames or [])]
    if not fields:
        raise ValueError("Extracted CSV has no header row.")
    normalized = normalize_and_validate_headers(fields)
    rows = [{k: str(v or "") for k, v in row.items()} for row in reader]
    return normalized, rows


def normalize_and_validate_headers(headers: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in headers:
        key = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
        key = _HEADER_ALIASES.get(key, key)
        if key in seen:
            raise ValueError(f"Duplicate normalized header detected: {key}")
        seen.add(key)
        out.append(key)
    missing = [c for c in EXPECTED_COLUMNS if c not in out]
    extra = [c for c in out if c not in EXPECTED_COLUMNS]
    if missing:
        raise ValueError(f"Extracted CSV missing required columns: {', '.join(missing)}")
    if extra:
        raise ValueError(
            "Extracted CSV has unsupported columns after normalization: " + ", ".join(extra)
        )
    return EXPECTED_COLUMNS[:]


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


def resolve_sector_for_day_rotation(*, weekday: int) -> str:
    """Map weekday (0=Mon..6=Sun) to a recommended daily sector."""
    mapping = {
        0: "broad",
        1: "water_env",
        2: "universities_regional",
        3: "hospitals_clinical",
        4: "industry_qc",
        5: "thin_regions",
        6: "custom",
    }
    return mapping[int(weekday) % 7]


def _backoff_seconds(*, attempt: int, initial: float, cap: float) -> float:
    base = min(float(cap), float(initial) * (2 ** max(0, attempt - 1)))
    jitter = random.uniform(0.0, min(1.0, base * 0.2))
    return base + jitter


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
    prompt_file: Path,
    sector: str,
    limits: dict[str, Any],
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
    repeated_institutions: list[str] = []
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
    repeated_institutions = [k for k, v in inst_counts.items() if v > 1]

    def _top_n(d: dict[str, int], n: int = 10) -> list[str]:
        return [k for k, _ in sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:n]]

    counts = summary_json.get("counts", {})
    blocked = int(counts.get("blocked", len(blocked_rows)))
    review = int(counts.get("needs_manual_review", 0))
    send_ready = int(counts.get("send_ready_marketing", len(send_rows)))
    lines = [
        "# Deep Research automation review summary",
        "",
        f"- Prompt file: `{prompt_file.resolve()}`",
        f"- Sector: **{sector}**",
        f"- Total candidates: **{int(exclusion_summary.get('total_candidates', 0))}**",
        f"- Excluded locally: **{int(exclusion_summary.get('excluded_count', 0))}**",
        f"- Net-new candidates: **{int(exclusion_summary.get('netnew_count', len(net_rows)))}**",
        f"- Send-ready count: **{send_ready}**",
        f"- Blocked count: **{blocked}**",
        f"- Review count: **{review}**",
        f"- Limits triggered: **{bool(limits.get('limits_triggered', False))}**",
        f"- Truncation applied: **{bool(limits.get('truncation_applied', False))}**",
        f"- Candidate limit: **{int(limits.get('max_candidates', 0))}**",
        f"- Send-ready limit: **{int(limits.get('max_send_ready', 0))}**",
        f"- Send-ready over limit: **{bool(limits.get('send_ready_over_limit', False))}**",
        f"- Generic label count: **{len(generic_flags)}**",
        "",
        "## Top institutions",
    ]
    for name in _top_n(inst_counts):
        lines.append(f"- {name}")
    lines.extend(["", "## Top domains"])
    for dom in _top_n(domain_counts):
        lines.append(f"- {dom}")
    lines.extend(["", "## Repeated institutions"])
    if repeated_institutions:
        for inst in sorted(repeated_institutions)[:10]:
            lines.append(f"- {inst}")
    else:
        lines.append("- (none)")
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
    max_candidates: int,
    max_send_ready: int,
    fail_on_over_limit: bool,
    run_contacted_coverage_check: bool,
    strict_contacted_coverage: bool,
    max_seed_email_sample: int = 300,
    max_seed_institutions: int = 500,
    max_seed_domains: int = 500,
    use_file_search: bool = False,
    max_retries: int = 4,
    initial_backoff_seconds: float = 5.0,
    max_backoff_seconds: float = 120.0,
    fallback_sector: str | None = None,
    daily_mode: bool = False,
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
        prompt_preview_txt=out_dir / "prompt_preview.txt",
        api_error_json=out_dir / "api_error.json",
        api_error_txt=out_dir / "api_error.txt",
        retry_attempts_json=out_dir / "retry_attempts.json",
        process_workspace=out_dir / "process_workspace",
    )
    artifacts.process_workspace.mkdir(parents=True, exist_ok=True)
    coverage_report_json = out_dir / "contacted_coverage_report.json"

    compact = build_compact_seed_artifacts(
        out_dir=out_dir,
        seed_paths=seed_paths,
        max_seed_email_sample=max_seed_email_sample,
        max_seed_institutions=max_seed_institutions,
        max_seed_domains=max_seed_domains,
    )
    prompt_template = load_prompt_template(prompt_file)
    compact_prompt_paths = {
        "canonical_dnr_path": Path(compact["canonical_dnr_path"]),
        "seed_known_institutions": Path(compact["seed_known_institutions"]),
        "seed_known_domains": Path(compact["seed_known_domains"]),
        "seed_recent_contacted_emails_sample": Path(compact["seed_recent_contacted_emails_sample"]),
        "seed_exclusion_summary": Path(compact["seed_exclusion_summary"]),
    }

    def _render_for_sector(s: str) -> str:
        return render_prompt(
            template_text=prompt_template,
            sector=s,
            limit_hint=limit_hint,
            compact_seed_files=compact_prompt_paths,
        )

    prompt_text = _render_for_sector(sector)
    artifacts.prompt_preview_txt.write_text(prompt_text, encoding="utf-8")
    uploaded_file_ids: dict[str, str] = {}
    retry_attempts: list[dict[str, Any]] = []
    selected_sector = sector
    try:
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
            sector_plan = [sector]
            if fallback_sector and fallback_sector != sector:
                sector_plan.append(fallback_sector)
            last_err: Exception | None = None
            for idx, sector_candidate in enumerate(sector_plan):
                selected_sector = sector_candidate
                prompt_text = _render_for_sector(selected_sector)
                artifacts.prompt_preview_txt.write_text(prompt_text, encoding="utf-8")
                for attempt in range(1, max(1, int(max_retries)) + 1):
                    try:
                        raw_json, raw_text, uploaded_file_ids = run_deep_research_response(
                            client=client,
                            model=model,
                            prompt_text=prompt_text,
                            seed_input_files={
                                "seed_known_institutions": Path(compact["seed_known_institutions"]),
                                "seed_known_domains": Path(compact["seed_known_domains"]),
                                "seed_recent_contacted_emails_sample": Path(compact["seed_recent_contacted_emails_sample"]),
                                "seed_exclusion_summary": Path(compact["seed_exclusion_summary"]),
                            },
                            use_background=use_background,
                        )
                        retry_attempts.append(
                            {
                                "at": _utc_now().isoformat().replace("+00:00", "Z"),
                                "sector": selected_sector,
                                "attempt": attempt,
                                "result": "success",
                            }
                        )
                        break
                    except DeepResearchApiError as exc:
                        last_err = exc
                        retry_attempts.append(
                            {
                                "at": _utc_now().isoformat().replace("+00:00", "Z"),
                                "sector": selected_sector,
                                "attempt": attempt,
                                "result": "error",
                                "error_code": exc.code,
                                "retryable": exc.retryable,
                                "message": str(exc),
                            }
                        )
                        if not exc.retryable or attempt >= max(1, int(max_retries)):
                            break
                        delay = _backoff_seconds(
                            attempt=attempt,
                            initial=float(initial_backoff_seconds),
                            cap=float(max_backoff_seconds),
                        )
                        retry_attempts[-1]["delay_seconds"] = delay
                        time.sleep(delay)
                    except Exception as exc:
                        last_err = exc
                        retry_attempts.append(
                            {
                                "at": _utc_now().isoformat().replace("+00:00", "Z"),
                                "sector": selected_sector,
                                "attempt": attempt,
                                "result": "error",
                                "error_code": "non_retryable",
                                "retryable": False,
                                "message": str(exc),
                            }
                        )
                        break
                else:
                    pass
                if retry_attempts and retry_attempts[-1].get("result") == "success":
                    break
                # Only rotate to fallback if broad failed with retryable API errors.
                if idx == 0 and sector_candidate == sector and fallback_sector and fallback_sector != sector:
                    continue
                if last_err is not None:
                    raise last_err
            if not retry_attempts or retry_attempts[-1].get("result") != "success":
                if last_err is not None:
                    raise last_err
                raise RuntimeError("Deep research run failed without detailed retry records.")

        artifacts.retry_attempts_json.write_text(
            json.dumps({"attempts": retry_attempts}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        artifacts.raw_response_json.write_text(raw_json, encoding="utf-8")
        artifacts.raw_response_txt.write_text(raw_text, encoding="utf-8")

        csv_text = extract_csv_text_from_model_output(raw_text)
        fieldnames, rows = parse_csv_rows(csv_text)
        candidate_count = len(rows)
        truncation_applied = False
        candidate_limit_triggered = candidate_count > max_candidates
        if candidate_limit_triggered and fail_on_over_limit:
            raise RuntimeError(
                f"Extracted candidate rows ({candidate_count}) exceed --max-candidates={max_candidates}."
            )
        if candidate_limit_triggered:
            rows = rows[:max_candidates]
            truncation_applied = True
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

        coverage_payload: dict[str, Any] = {
            "enabled": bool(run_contacted_coverage_check),
            "strict": bool(strict_contacted_coverage),
            "returncode": None,
            "json_report": str(coverage_report_json),
        }
        if run_contacted_coverage_check:
            coverage_cp = _run_subprocess(
                [
                    "scripts/qa/validate_contacted_csv_coverage.py",
                    "--json-out",
                    str(coverage_report_json),
                    *(["--strict"] if strict_contacted_coverage else []),
                ],
                cwd=app_root,
            )
            coverage_payload["returncode"] = int(coverage_cp.returncode)
            coverage_payload["stdout"] = coverage_cp.stdout
            coverage_payload["stderr"] = coverage_cp.stderr
            if strict_contacted_coverage and coverage_cp.returncode != 0:
                raise RuntimeError(
                    "Contacted coverage validation failed in strict mode. "
                    f"stdout={coverage_cp.stdout}\nstderr={coverage_cp.stderr}"
                )

        send_ready = artifacts.process_workspace / "send_ready_marketing.csv"
        blocked = artifacts.process_workspace / "marketing_blocked_already_known.csv"
        summary = artifacts.process_workspace / "marketing_contacts_summary.json"
        summary_json: dict[str, Any] = {}
        if summary.is_file():
            summary_json = json.loads(summary.read_text(encoding="utf-8"))
        counts = summary_json.get("counts", {})
        send_ready_count = int(counts.get("send_ready_marketing", len(_read_csv_dicts(send_ready))))
        blocked_count = int(counts.get("blocked", len(_read_csv_dicts(blocked))))
        review_count = int(
            counts.get(
                "needs_manual_review",
                len(_read_csv_dicts(artifacts.process_workspace / "marketing_needs_manual_review.csv")),
            )
        )
        send_ready_over_limit = send_ready_count > max_send_ready
        limits = {
            "max_candidates": max_candidates,
            "max_send_ready": max_send_ready,
            "truncation_applied": truncation_applied,
            "candidate_limit_triggered": candidate_limit_triggered,
            "send_ready_over_limit": send_ready_over_limit,
            "limits_triggered": bool(truncation_applied or send_ready_over_limit),
        }
        review_md = build_review_summary_markdown(
            exclusion_summary=exclusion,
            send_ready_csv=send_ready,
            blocked_csv=blocked,
            summary_json_path=summary,
            netnew_csv=artifacts.candidates_netnew_csv,
            output_paths=artifacts,
            prompt_file=prompt_file,
            sector=sector,
            limits=limits,
        )
        artifacts.review_summary_md.write_text(review_md, encoding="utf-8")

        metadata = {
            "generated_at": _utc_now().isoformat().replace("+00:00", "Z"),
            "mode": "dry_run" if dry_run else "live_research_no_send",
            "sector": selected_sector,
            "requested_sector": sector,
            "fallback_sector": fallback_sector,
            "fallback_used": bool(selected_sector != sector),
            "daily_mode": bool(daily_mode),
            "daily_mode_broad_warning": bool(daily_mode and sector == "broad"),
            "limit_hint": limit_hint,
            "model": model,
            "prompt_file": str(prompt_file.resolve()),
            "seed_paths": {k: str(v) for k, v in asdict(seed_paths).items()},
            "compact_seed_artifacts": {
                "seed_known_institutions": str(compact["seed_known_institutions"]),
                "seed_known_domains": str(compact["seed_known_domains"]),
                "seed_recent_contacted_emails_sample": str(compact["seed_recent_contacted_emails_sample"]),
                "seed_exclusion_summary": str(compact["seed_exclusion_summary"]),
                "counts": compact["counts"],
            },
            "uploaded_file_paths": {k: str(v) for k, v in asdict(seed_paths).items()},
            "uploaded_file_ids": uploaded_file_ids,
            "output_directory": str(out_dir.resolve()),
            "artifacts": {k: str(v) for k, v in asdict(artifacts).items()},
            "exclusion_summary": exclusion,
            "candidate_count": len(rows),
            "excluded_count": int(exclusion.get("excluded_count", 0)),
            "send_ready_count": send_ready_count,
            "blocked_count": blocked_count,
            "review_count": review_count,
            "max_candidates": max_candidates,
            "max_send_ready": max_send_ready,
            "truncation_applied": truncation_applied,
            "dry_run": bool(dry_run),
            "background_mode": bool(use_background),
            "candidate_limit_triggered": candidate_limit_triggered,
            "send_ready_over_limit": send_ready_over_limit,
            "contacted_coverage_check": coverage_payload,
            "use_file_search_requested": bool(use_file_search),
            "structured_output_mode": "csv_parser_v1",
            "retry_policy": {
                "max_retries": int(max_retries),
                "initial_backoff_seconds": float(initial_backoff_seconds),
                "max_backoff_seconds": float(max_backoff_seconds),
            },
            "retry_attempt_count": len(retry_attempts),
            "status": "completed",
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
        artifacts.retry_attempts_json.write_text(
            json.dumps({"attempts": retry_attempts}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return artifacts
    except Exception as exc:
        err_payload = {
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        if isinstance(exc, DeepResearchApiError):
            err_payload["error_code"] = exc.code
            err_payload["api_status"] = exc.status
            err_payload["retryable"] = exc.retryable
        artifacts.api_error_json.write_text(json.dumps(err_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        artifacts.api_error_txt.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        fail_meta = {
            "generated_at": _utc_now().isoformat().replace("+00:00", "Z"),
            "status": "failed",
            "mode": "dry_run" if dry_run else "live_research_no_send",
            "model": model,
            "sector": selected_sector,
            "requested_sector": sector,
            "fallback_sector": fallback_sector,
            "fallback_used": bool(selected_sector != sector),
            "daily_mode": bool(daily_mode),
            "prompt_file": str(prompt_file.resolve()),
            "output_directory": str(out_dir.resolve()),
            "seed_paths": {k: str(v) for k, v in asdict(seed_paths).items()},
            "compact_seed_artifacts": {
                "seed_known_institutions": str(compact["seed_known_institutions"]),
                "seed_known_domains": str(compact["seed_known_domains"]),
                "seed_recent_contacted_emails_sample": str(compact["seed_recent_contacted_emails_sample"]),
                "seed_exclusion_summary": str(compact["seed_exclusion_summary"]),
                "counts": compact["counts"],
            },
            "uploaded_file_ids": uploaded_file_ids,
            "retry_policy": {
                "max_retries": int(max_retries),
                "initial_backoff_seconds": float(initial_backoff_seconds),
                "max_backoff_seconds": float(max_backoff_seconds),
            },
            "retry_attempt_count": len(retry_attempts),
            "error": err_payload,
            "safety": {
                "gmail_send_called": False,
                "mark_contacted_called": False,
                "sent_ingest_called": False,
                "dnr_refresh_after_send_called": False,
                "sqlite_mutation_intended": False,
            },
            "stop_message": "Ready for review; no live send performed.",
        }
        artifacts.retry_attempts_json.write_text(
            json.dumps({"attempts": retry_attempts}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        artifacts.run_metadata_json.write_text(json.dumps(fail_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise


__all__ = [
    "DEFAULT_PROMPT_PATH",
    "RunArtifacts",
    "SeedPaths",
    "build_review_summary_markdown",
    "default_seed_paths",
    "extract_csv_text_from_model_output",
    "load_prompt_template",
    "normalize_and_validate_headers",
    "parse_csv_rows",
    "build_compact_seed_artifacts",
    "render_prompt",
    "resolve_out_dir",
    "resolve_sector_for_day_rotation",
    "run_local_exclusion",
    "run_research_automation",
    "SECTOR_CHOICES",
    "write_csv",
]
