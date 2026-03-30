"""Shared helpers for Streamlit OrigenLab-mode drafting (review-only; no send)."""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from origenlab_email_pipeline.config import Settings
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source

if TYPE_CHECKING:
    import pandas as pd

from .draft_package import build_draft_package
from .generator import DraftGenerator, MockDraftGenerator
from .generator_factory import TatianaLLMConfigurationError, resolve_draft_generator
from .index import TatianaExampleIndex
from .normalize import build_example_sets
from .origenlab_context import DRAFTING_PROFILE_ORIGENLAB
from .origenlab_facts_loader import load_origenlab_drafting_context
from .pilot_schemas import PILOT_REVIEW_ALL_FIELDS, extract_asunto_from_draft, text_preview
from .schemas import DraftCase, DraftPackage


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_tatiana_seed_paths(settings: Settings) -> tuple[Path, Path, Path]:
    """Same defaults as ``run_pilot_batch`` for cohort CSVs."""
    root = _repo_root()
    reports = settings.resolved_reports_dir()
    lf = root / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_labeled_final.csv"
    sf = root / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_seed_style_guide.csv"
    rf = root / "reports" / "out" / "tatiana_candidate_cohort_marketing_top200_seed_retrieval.csv"
    return lf, sf, rf


def seed_paths_mtime(paths: tuple[Path, Path, Path]) -> tuple[float, float, float]:
    def mt(p: Path) -> float:
        return p.stat().st_mtime if p.is_file() else 0.0

    return (mt(paths[0]), mt(paths[1]), mt(paths[2]))


def get_cached_tatiana_index(settings: Settings, session_state: dict[str, Any]) -> TatianaExampleIndex:
    """Reuse Tatiana TF-IDF index in Streamlit session while cohort CSV mtimes are unchanged."""
    paths = default_tatiana_seed_paths(settings)
    mts = seed_paths_mtime(paths)
    cache = session_state.get("tatiana_index_cache")
    if cache and tuple(cache.get("mts") or ()) == mts:
        return cache["index"]
    index = load_tatiana_index(settings)
    session_state["tatiana_index_cache"] = {"mts": mts, "index": index}
    return index


def load_tatiana_index(
    settings: Settings,
    *,
    labeled_final: Path | None = None,
    style_seed: Path | None = None,
    retrieval_seed: Path | None = None,
) -> TatianaExampleIndex:
    lf, sf, rf = default_tatiana_seed_paths(settings)
    lf = labeled_final or lf
    sf = style_seed or sf
    rf = retrieval_seed or rf
    missing = [str(p) for p in (lf, sf, rf) if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "Faltan CSV de índice Tatiana: " + "; ".join(missing) + ". "
            "Ejecute build del índice/cohort o ajuste rutas (ver TATIANA_DRAFTING_COPILOT.md)."
        )
    style_ex, retr_ex = build_example_sets(labeled_final_csv=lf, style_seed_csv=sf, retrieval_seed_csv=rf)
    return TatianaExampleIndex.build(style_examples=style_ex, retrieval_examples=retr_ex, method="tfidf")


def resolve_streamlit_generator(
    *,
    generator_name: str,
    use_mock_explicit: bool,
    settings: Settings,
) -> tuple[DraftGenerator, str]:
    """Like pilot ``resolve_pilot_generator`` but raises ``RuntimeError``/``ValueError`` for UI (no ``SystemExit``)."""
    if use_mock_explicit:
        return MockDraftGenerator(), "mock"
    name = (generator_name or "openai_chat").strip().lower()
    if name in ("mock", "none", "offline"):
        raise ValueError(
            "Elija en la interfaz la opción «Simulación sin API» para generar sin conexión, "
            "o use OpenAI con la clave de API configurada."
        )
    try:
        return resolve_draft_generator(name, settings=settings), name
    except TatianaLLMConfigurationError as e:
        raise RuntimeError(
            "No está configurada la clave de API de OpenAI. "
            "Defina las variables ORIGENLAB_TATIANA_OPENAI_API_KEY u OPENAI_API_KEY "
            "(vea el archivo .env.example), o elija «Simulación sin API» en el motor de generación."
        ) from e


def run_origenlab_draft_package(
    *,
    case: DraftCase,
    settings: Settings,
    index: TatianaExampleIndex,
    generator_name: str,
    use_mock_explicit: bool,
    style_top_k: int = 3,
    retrieval_top_k: int = 5,
) -> DraftPackage:
    gen, _ = resolve_streamlit_generator(
        generator_name=generator_name,
        use_mock_explicit=use_mock_explicit,
        settings=settings,
    )
    ol = load_origenlab_drafting_context()
    return build_draft_package(
        case=case,
        index=index,
        generator=gen,
        style_top_k=style_top_k,
        retrieval_top_k=retrieval_top_k,
        drafting_profile=DRAFTING_PROFILE_ORIGENLAB,
        origenlab_context=ol,
    )


def load_contacto_gmail_email_choices_df(
    conn: sqlite3.Connection,
    *,
    limit: int = 40,
    ensure_email_ids: Sequence[int] | None = None,
) -> "pd.DataFrame":
    """Recent Gmail contacto rows for picker (read-only).

    ``ensure_email_ids`` adds specific ``emails.id`` rows if missing (e.g. handoff from Casos para revisar).
    """
    import pandas as pd

    lim = max(1, min(int(limit), 500))
    _gmail_c = sql_predicate_contacto_gmail_source()
    df = pd.read_sql_query(
        f"""
        SELECT
          id,
          date_iso,
          substr(COALESCE(subject, ''), 1, 100) AS subject_preview,
          substr(COALESCE(sender, ''), 1, 100) AS sender_preview,
          source_file
        FROM emails
        WHERE {_gmail_c}
        ORDER BY
          CASE WHEN date_iso IS NULL OR trim(date_iso) = '' THEN 1 ELSE 0 END,
          date_iso DESC
        LIMIT ?
        """,
        conn,
        params=(lim,),
    )
    if not ensure_email_ids:
        return df
    have = set(int(x) for x in df["id"].tolist()) if not df.empty else set()
    missing = [int(i) for i in ensure_email_ids if int(i) not in have]
    if not missing:
        return df
    placeholders = ",".join("?" * len(missing))
    extra = pd.read_sql_query(
        f"""
        SELECT
          id,
          date_iso,
          substr(COALESCE(subject, ''), 1, 100) AS subject_preview,
          substr(COALESCE(sender, ''), 1, 100) AS sender_preview,
          source_file
        FROM emails
        WHERE {_gmail_c}
          AND id IN ({placeholders})
        """,
        conn,
        params=tuple(missing),
    )
    if extra.empty:
        return df
    out = pd.concat([df, extra], ignore_index=True)
    out = out.drop_duplicates(subset=["id"], keep="first")
    return out


def draft_case_from_email_row(
    conn: sqlite3.Connection,
    *,
    email_id: int,
) -> DraftCase | None:
    row = conn.execute(
        """
        SELECT id, subject, sender, source_file, date_iso,
               COALESCE(NULLIF(trim(top_reply_clean), ''), NULLIF(trim(full_body_clean), ''),
                        NULLIF(trim(body_text_clean), ''), NULLIF(trim(body), '')) AS body_use
        FROM emails
        WHERE id = ?
        """,
        (int(email_id),),
    ).fetchone()
    if row is None:
        return None
    eid, subject, sender, source_file, date_iso, body_use = row
    body = (body_use or "").strip()
    if not body:
        body = "(sin cuerpo extraíble en archivo; amplíe en editor manual)"
    meta = {
        "intake": "gmail_contacto_email",
        "email_id": int(eid),
        "sender": sender,
        "source_file": source_file,
        "date_iso": date_iso,
    }
    return DraftCase(
        case_id=f"gmail_contacto_{eid}",
        subject=(subject or "").strip(),
        body_text=body,
        expected_label=None,
        context_metadata=meta,
    )


def export_streamlit_review_artifact(
    *,
    out_dir: Path,
    pkg: DraftPackage,
    reviewer_decision: str,
    reviewer_notes: str,
    reviewer_final_subject: str,
    reviewer_final_body: str,
) -> dict[str, str]:
    """Write draft JSON + single-row pilot-style CSV under ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pkg_path = out_dir / "draft_package.json"
    pkg_path.write_text(json.dumps(pkg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    gen_subj = extract_asunto_from_draft(pkg.generated_draft or "")
    case = pkg.case
    cid = str(case.get("case_id") or "")
    sub_in = str(case.get("subject") or "")
    body_prev = text_preview(str(case.get("body_text") or ""), max_chars=600)
    style_ids = ";".join(x.get("example_id", "") for x in pkg.retrieved_style_examples)
    retr_ids = ";".join(x.get("example_id", "") for x in pkg.retrieved_examples)

    row: dict[str, str] = {k: "" for k in PILOT_REVIEW_ALL_FIELDS}
    row.update(
        {
            "case_id": cid,
            "subject_input": sub_in,
            "body_preview": body_prev,
            "generated_subject": gen_subj,
            "generated_body": pkg.generated_draft or "",
            "abstained": "y" if pkg.abstained else "n",
            "provider_name": pkg.provider_name,
            "retrieved_style_ids": style_ids,
            "retrieved_example_ids": retr_ids,
            "system_notes": pkg.notes or "",
            "reviewer_decision": reviewer_decision.strip(),
            "reviewer_edit_level": "",
            "reviewer_sentiment": "",
            "reviewer_notes": reviewer_notes.strip(),
            "reviewer_final_subject": reviewer_final_subject.strip(),
            "reviewer_final_body": reviewer_final_body.strip(),
            "approved_for_send": "n",
        }
    )
    csv_path = out_dir / "pilot_review_row.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(PILOT_REVIEW_ALL_FIELDS))
        w.writeheader()
        w.writerow(row)

    snap = load_origenlab_drafting_context().to_serializable_summary()
    (out_dir / "origenlab_context_snapshot.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = {
        "kind": "streamlit_borrador_comercial",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "draft_package_json": str(pkg_path.resolve()),
        "pilot_review_csv": str(csv_path.resolve()),
        "origenlab_context_snapshot": str((out_dir / "origenlab_context_snapshot.json").resolve()),
    }
    (out_dir / "export_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return {"out_dir": str(out_dir.resolve()), "draft_package_json": str(pkg_path), "csv": str(csv_path)}


def new_streamlit_export_dir(settings: Settings) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return settings.resolved_reports_dir() / f"{ts}_streamlit_borrador_comercial"


def draft_case_from_manual(
    *,
    case_id: str,
    subject: str,
    body_text: str,
    requester_name: str | None = None,
    requester_email: str | None = None,
    requested_product_or_category: str | None = None,
    explicit_known_facts: str | None = None,
    missing_information: str | None = None,
    notes_for_reviewer: str | None = None,
) -> DraftCase:
    """Build a ``DraftCase`` aligned with pilot ``context_metadata`` (OrigenLab mode)."""
    meta: dict[str, Any] = {
        "pilot": True,
        "intake": "streamlit_manual",
        "requester_name": requester_name,
        "requester_email": requester_email,
        "requested_product_or_category": requested_product_or_category,
        "explicit_known_facts": explicit_known_facts,
        "missing_information": missing_information,
        "notes_for_reviewer": notes_for_reviewer,
    }
    meta = {k: v for k, v in meta.items() if v not in (None, "", [])}
    cid = (case_id or "").strip() or "streamlit_manual_case"
    subj = (subject or "").strip()
    body = (body_text or "").strip()
    return DraftCase(
        case_id=cid,
        subject=subj,
        body_text=body,
        expected_label=None,
        context_metadata=meta,
    )
