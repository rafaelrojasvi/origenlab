from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.config import Settings

from .draft_package import build_draft_package
from .generator import DraftGenerator, MockDraftGenerator
from .index import TatianaExampleIndex
from .normalize import build_example_sets
from .origenlab_context import DRAFTING_PROFILE_ORIGENLAB, DRAFTING_PROFILE_TATIANA_HISTORICAL
from .origenlab_facts_loader import load_origenlab_drafting_context
from .pilot_loader import load_pilot_input
from .pilot_schemas import (
    PILOT_REVIEW_ALL_FIELDS,
    extract_asunto_from_draft,
    safe_case_filename,
    text_preview,
)
from .schemas import DraftCase

_LATEST_PILOT_SYMLINK_NAME = "latest_tatiana_pilot_batch"


def _link_latest_pilot_batch(batch_dir: Path) -> None:
    """
    Point latest_tatiana_pilot_batch -> this folder (same directory as summarize default).

    Skips if the name exists and is not a symlink (avoids clobbering user data).
    Ignores OSError (symlinks unavailable on some environments).
    """
    resolved = batch_dir.resolve()
    parent = resolved.parent
    link = parent / _LATEST_PILOT_SYMLINK_NAME
    try:
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            return
        link.symlink_to(resolved.relative_to(parent), target_is_directory=True)
    except OSError:
        return


@dataclass
class PilotBatchResult:
    out_dir: Path
    cases_processed: int
    abstained_count: int
    generator_name: str
    case_json_paths: list[str] = field(default_factory=list)
    provider_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "out_dir": str(self.out_dir),
            "cases_processed": self.cases_processed,
            "abstained_count": self.abstained_count,
            "generator_name": self.generator_name,
            "case_json_paths": list(self.case_json_paths),
            "provider_counts": dict(self.provider_counts),
        }


def resolve_pilot_generator(
    *,
    generator_name: str,
    allow_mock: bool,
    settings: Settings,
) -> tuple[DraftGenerator, str]:
    """
    - With `--allow-mock`, always uses MockDraftGenerator (for CI / dry runs).
    - Otherwise defaults to provider-backed `openai_chat` and fails clearly if the API is not configured.
    - `--generator mock` without `--allow-mock` is rejected (no silent offline pilot).
    """
    from .generator_factory import TatianaLLMConfigurationError, resolve_draft_generator

    name = (generator_name or "openai_chat").strip().lower()
    if allow_mock:
        return MockDraftGenerator(), "mock"
    if name in ("mock", "none", "offline"):
        raise SystemExit(
            "Pilot batch refuses --generator mock without --allow-mock "
            "(avoids accidental offline pilot runs). Add --allow-mock for intentional mock batches."
        )
    try:
        return resolve_draft_generator(name, settings=settings), name
    except TatianaLLMConfigurationError as e:
        raise SystemExit(
            f"{e}\n\n"
            "Pilot batch expects a configured OpenAI provider by default "
            "(ORIGENLAB_TATIANA_OPENAI_API_KEY or OPENAI_API_KEY; see apps/email-pipeline/.env.example). "
            "Use --allow-mock to generate a mock pilot batch without API access."
        ) from e


def run_pilot_batch(
    *,
    input_path: Path,
    settings: Settings,
    generator_name: str = "openai_chat",
    allow_mock: bool = False,
    out_dir: Path | None = None,
    max_cases: int | None = None,
    style_top_k: int = 3,
    retrieval_top_k: int = 5,
    labeled_final_csv: Path | None = None,
    style_seed_csv: Path | None = None,
    retrieval_seed_csv: Path | None = None,
    origenlab_mode: bool = False,
) -> PilotBatchResult:
    repo_root = Path(__file__).resolve().parents[3]
    reports = settings.resolved_reports_dir()
    default_labeled = repo_root / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_labeled_final.csv"
    default_style = repo_root / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_seed_style_guide.csv"
    default_retr = repo_root / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_seed_retrieval.csv"

    lf = labeled_final_csv or default_labeled
    sf = style_seed_csv or default_style
    rf = retrieval_seed_csv or default_retr

    gen, resolved_name = resolve_pilot_generator(
        generator_name=generator_name, allow_mock=allow_mock, settings=settings
    )

    drafting_profile = DRAFTING_PROFILE_ORIGENLAB if origenlab_mode else DRAFTING_PROFILE_TATIANA_HISTORICAL
    ol_context = load_origenlab_drafting_context() if origenlab_mode else None

    cases_in = load_pilot_input(input_path)
    if max_cases is not None:
        cases_in = cases_in[: max(0, max_cases)]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    batch_dir = out_dir or (reports / f"{ts}_tatiana_pilot_batch")
    batch_dir.mkdir(parents=True, exist_ok=True)

    pilot_cases_rows: list[dict[str, str]] = []
    pilot_review_rows: list[dict[str, str]] = []
    case_json_rel: list[str] = []
    provider_counts: dict[str, int] = {}
    abstained_n = 0

    if not cases_in:
        _write_csv(
            batch_dir / "pilot_cases.csv",
            [],
            fieldnames=[
                "case_id",
                "subject_input",
                "body_preview",
                "from_email",
                "from_name",
                "thread_hint",
                "received_at",
                "case_type",
                "notes",
                "case_json",
                "generated_subject",
                "abstained",
                "provider_name",
                "system_notes",
                "retrieved_style_ids",
                "retrieved_example_ids",
            ],
        )
        _write_csv(batch_dir / "pilot_review.csv", [], fieldnames=list(PILOT_REVIEW_ALL_FIELDS))
        batch_summary = {
            "batch_kind": "tatiana_pilot_batch",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_path": str(input_path.resolve()),
            "out_dir": str(batch_dir.resolve()),
            "generator_resolved": resolved_name,
            "allow_mock": allow_mock,
            "origenlab_mode": origenlab_mode,
            "drafting_profile": drafting_profile,
            "origenlab_fact_sources": list(ol_context.fact_sources) if ol_context else [],
            "total_cases": 0,
            "abstained_count": 0,
            "warning": "No cases loaded from input; check file path and required columns.",
        }
        (batch_dir / "pilot_summary.json").write_text(
            json.dumps(batch_summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (batch_dir / "pilot_summary.md").write_text(_render_batch_md(batch_summary), encoding="utf-8")
        _link_latest_pilot_batch(batch_dir)
        return PilotBatchResult(
            out_dir=batch_dir,
            cases_processed=0,
            abstained_count=0,
            generator_name=resolved_name,
            case_json_paths=[],
            provider_counts={},
        )

    style_ex, retr_ex = build_example_sets(labeled_final_csv=Path(lf), style_seed_csv=Path(sf), retrieval_seed_csv=Path(rf))
    index = TatianaExampleIndex.build(
        style_examples=style_ex,
        retrieval_examples=retr_ex,
        method="tfidf",
    )

    if ol_context:
        snap = ol_context.to_serializable_summary()
        (batch_dir / "origenlab_context_snapshot.json").write_text(
            json.dumps(snap, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    for pilot in cases_in:
        dc = DraftCase(
            case_id=pilot.case_id,
            subject=pilot.subject,
            body_text=pilot.body_text,
            expected_label=pilot.case_type,
            context_metadata=pilot.context_metadata(),
        )
        pkg = build_draft_package(
            case=dc,
            index=index,
            generator=gen,
            style_top_k=style_top_k,
            retrieval_top_k=retrieval_top_k,
            exclude_example_ids=None,
            drafting_profile=drafting_profile,
            origenlab_context=ol_context,
        )
        if pkg.abstained:
            abstained_n += 1
        provider_counts[pkg.provider_name] = provider_counts.get(pkg.provider_name, 0) + 1

        safe = safe_case_filename(pilot.case_id)
        case_rel = f"case_{safe}.json"
        case_path = batch_dir / case_rel
        case_path.write_text(json.dumps(pkg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        case_json_rel.append(case_rel)

        gen_subj = extract_asunto_from_draft(pkg.generated_draft)
        style_ids = ";".join(x.get("example_id", "") for x in pkg.retrieved_style_examples)
        retr_ids = ";".join(x.get("example_id", "") for x in pkg.retrieved_examples)

        pilot_cases_rows.append(
            {
                "case_id": pilot.case_id,
                "subject_input": pilot.subject,
                "body_preview": text_preview(pilot.body_text, max_chars=500),
                "from_email": pilot.from_email or "",
                "from_name": pilot.from_name or "",
                "thread_hint": pilot.thread_hint or "",
                "received_at": pilot.received_at or "",
                "case_type": pilot.case_type or "",
                "notes": pilot.notes or "",
                "case_json": case_rel,
                "generated_subject": gen_subj,
                "abstained": "y" if pkg.abstained else "n",
                "provider_name": pkg.provider_name,
                "system_notes": pkg.notes or "",
                "retrieved_style_ids": style_ids,
                "retrieved_example_ids": retr_ids,
            }
        )

        review_row: dict[str, str] = {
            "case_id": pilot.case_id,
            "subject_input": pilot.subject,
            "body_preview": text_preview(pilot.body_text, max_chars=600),
            "generated_subject": gen_subj,
            "generated_body": pkg.generated_draft or "",
            "abstained": "y" if pkg.abstained else "n",
            "provider_name": pkg.provider_name,
            "retrieved_style_ids": style_ids,
            "retrieved_example_ids": retr_ids,
            "system_notes": pkg.notes or "",
            "reviewer_decision": "",
            "reviewer_edit_level": "",
            "reviewer_sentiment": "",
            "reviewer_notes": "",
            "reviewer_final_subject": "",
            "reviewer_final_body": "",
            "approved_for_send": "",
        }
        pilot_review_rows.append(review_row)

    _write_csv(batch_dir / "pilot_cases.csv", pilot_cases_rows)
    _write_csv(batch_dir / "pilot_review.csv", pilot_review_rows, fieldnames=list(PILOT_REVIEW_ALL_FIELDS))

    batch_summary = {
        "batch_kind": "tatiana_pilot_batch",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_path": str(input_path.resolve()),
        "out_dir": str(batch_dir.resolve()),
        "generator_resolved": resolved_name,
        "allow_mock": allow_mock,
        "origenlab_mode": origenlab_mode,
        "drafting_profile": drafting_profile,
        "origenlab_fact_sources": list(ol_context.fact_sources) if ol_context else [],
        "style_top_k": style_top_k,
        "retrieval_top_k": retrieval_top_k,
        "total_cases": len(cases_in),
        "abstained_count": abstained_n,
        "provider_counts": provider_counts,
        "case_artifacts": case_json_rel,
        "human_review_csv": "pilot_review.csv",
        "machine_audit_csv": "pilot_cases.csv",
    }
    (batch_dir / "pilot_summary.json").write_text(json.dumps(batch_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (batch_dir / "pilot_summary.md").write_text(_render_batch_md(batch_summary), encoding="utf-8")
    _link_latest_pilot_batch(batch_dir)

    return PilotBatchResult(
        out_dir=batch_dir,
        cases_processed=len(cases_in),
        abstained_count=abstained_n,
        generator_name=resolved_name,
        case_json_paths=case_json_rel,
        provider_counts=provider_counts,
    )


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> None:
    if not rows:
        fn = fieldnames or []
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fn, extrasaction="ignore")
            w.writeheader()
        return
    fn = fieldnames or list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fn, extrasaction="ignore", quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fn})


def _render_batch_md(s: dict[str, Any]) -> str:
    lines = [
        "# Tatiana pilot batch (generation pass)",
        "",
        f"- **input**: `{s.get('input_path')}`",
        f"- **out_dir**: `{s.get('out_dir')}`",
        f"- **drafting_profile**: `{s.get('drafting_profile', 'tatiana_historical')}` "
        f"(origenlab_mode={s.get('origenlab_mode', False)})",
        f"- **generator**: `{s.get('generator_resolved')}` (allow_mock={s.get('allow_mock')})",
        f"- **cases**: {s.get('total_cases')}",
        f"- **abstained**: {s.get('abstained_count')}",
        f"- **provider_counts**: {s.get('provider_counts', {})}",
        "",
    ]
    if s.get("warning"):
        lines.append(f"- **warning**: {s.get('warning')}")
        lines.append("")
    lines.extend(
        [
            "## Next steps",
            "",
            "1. Open **`pilot_review.csv`** and fill reviewer columns (do not automate sending).",
            "2. Run `summarize_tatiana_pilot_review.py --pilot-dir` on this folder.",
            "",
            "Human approval remains mandatory before any outbound send.",
        ]
    )
    return "\n".join(lines) + "\n"
