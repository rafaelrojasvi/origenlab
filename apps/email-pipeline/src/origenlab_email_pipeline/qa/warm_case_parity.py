"""Read-only warm-case parity audit (SQLite vs Postgres mirror API exports)."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WarmCaseParityResult:
    sqlite_meta: dict[str, Any] = field(default_factory=dict)
    postgres_meta: dict[str, Any] = field(default_factory=dict)
    sqlite_row_count: int = 0
    postgres_row_count: int = 0
    sqlite_category_counts: dict[str, int] = field(default_factory=dict)
    postgres_category_counts: dict[str, int] = field(default_factory=dict)
    category_count_deltas: dict[str, int] = field(default_factory=dict)
    category_mismatches: list[dict[str, Any]] = field(default_factory=list)
    sqlite_only: list[dict[str, Any]] = field(default_factory=list)
    postgres_only: list[dict[str, Any]] = field(default_factory=list)
    matched_count: int = 0


def normalize_subject(subject: str) -> str:
    return " ".join(str(subject or "").strip().lower().split())


def pair_key(item: dict[str, Any]) -> str:
    email = str(item.get("contact_email") or "").strip().lower()
    subject = normalize_subject(str(item.get("subject") or ""))
    return f"{email}|{subject}"


def case_id_key(item: dict[str, Any]) -> str | None:
    case_id = str(item.get("case_id") or "").strip()
    return case_id or None


def load_warm_cases_json(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected JSON object with meta/items")
    meta = payload.get("meta")
    items = payload.get("items")
    if meta is not None and not isinstance(meta, dict):
        raise ValueError(f"{path}: meta must be an object")
    if items is None:
        items = []
    if not isinstance(items, list):
        raise ValueError(f"{path}: items must be a list")
    normalized_items = [item for item in items if isinstance(item, dict)]
    return dict(meta or {}), normalized_items


def category_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        category = str(item.get("category") or "").strip() or "(missing)"
        counts[category] += 1
    return dict(sorted(counts.items()))


def _index_by_pair(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        indexed[pair_key(item)] = item
    return indexed


def _index_by_case_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        key = case_id_key(item)
        if key:
            indexed[key] = item
    return indexed


def _category(item: dict[str, Any]) -> str:
    return str(item.get("category") or "").strip() or "(missing)"


def _audit_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "contact_email": str(item.get("contact_email") or "").strip(),
        "subject": str(item.get("subject") or "").strip(),
        "category": _category(item),
        "case_id": str(item.get("case_id") or "").strip(),
        "last_seen_at": str(item.get("last_seen_at") or "").strip(),
        "status": str(item.get("status") or "").strip(),
    }


def _mismatch_row(
    sqlite_item: dict[str, Any],
    postgres_item: dict[str, Any],
    *,
    match_by: str,
) -> dict[str, Any]:
    return {
        "match_by": match_by,
        "contact_email": str(sqlite_item.get("contact_email") or postgres_item.get("contact_email") or "").strip(),
        "subject": str(sqlite_item.get("subject") or postgres_item.get("subject") or "").strip(),
        "sqlite_category": _category(sqlite_item),
        "postgres_category": _category(postgres_item),
        "sqlite_case_id": str(sqlite_item.get("case_id") or "").strip(),
        "postgres_case_id": str(postgres_item.get("case_id") or "").strip(),
        "sqlite_last_seen_at": str(sqlite_item.get("last_seen_at") or "").strip(),
        "postgres_last_seen_at": str(postgres_item.get("last_seen_at") or "").strip(),
    }


def compare_warm_case_exports(
    sqlite_items: list[dict[str, Any]],
    postgres_items: list[dict[str, Any]],
    *,
    sqlite_meta: dict[str, Any] | None = None,
    postgres_meta: dict[str, Any] | None = None,
) -> WarmCaseParityResult:
    sqlite_by_pair = _index_by_pair(sqlite_items)
    postgres_by_pair = _index_by_pair(postgres_items)
    sqlite_by_case_id = _index_by_case_id(sqlite_items)
    postgres_by_case_id = _index_by_case_id(postgres_items)

    matched_sqlite_pairs: set[str] = set()
    matched_postgres_pairs: set[str] = set()
    category_mismatches: list[dict[str, Any]] = []
    matched_count = 0

    for case_id, sqlite_item in sqlite_by_case_id.items():
        postgres_item = postgres_by_case_id.get(case_id)
        if postgres_item is None:
            continue
        sqlite_pk = pair_key(sqlite_item)
        postgres_pk = pair_key(postgres_item)
        matched_sqlite_pairs.add(sqlite_pk)
        matched_postgres_pairs.add(postgres_pk)
        matched_count += 1
        if _category(sqlite_item) != _category(postgres_item):
            category_mismatches.append(
                _mismatch_row(sqlite_item, postgres_item, match_by="case_id")
            )

    for sqlite_pk, sqlite_item in sqlite_by_pair.items():
        if sqlite_pk in matched_sqlite_pairs:
            continue
        postgres_item = postgres_by_pair.get(sqlite_pk)
        if postgres_item is None:
            continue
        postgres_pk = pair_key(postgres_item)
        matched_sqlite_pairs.add(sqlite_pk)
        matched_postgres_pairs.add(postgres_pk)
        matched_count += 1
        if _category(sqlite_item) != _category(postgres_item):
            category_mismatches.append(
                _mismatch_row(sqlite_item, postgres_item, match_by="contact_email+subject")
            )

    sqlite_only = [
        _audit_row(item)
        for pk, item in sqlite_by_pair.items()
        if pk not in matched_sqlite_pairs
    ]
    postgres_only = [
        _audit_row(item)
        for pk, item in postgres_by_pair.items()
        if pk not in matched_postgres_pairs
    ]

    sqlite_counts = category_counts(sqlite_items)
    postgres_counts = category_counts(postgres_items)
    all_categories = sorted(set(sqlite_counts) | set(postgres_counts))
    category_count_deltas = {
        category: postgres_counts.get(category, 0) - sqlite_counts.get(category, 0)
        for category in all_categories
    }

    return WarmCaseParityResult(
        sqlite_meta=dict(sqlite_meta or {}),
        postgres_meta=dict(postgres_meta or {}),
        sqlite_row_count=len(sqlite_items),
        postgres_row_count=len(postgres_items),
        sqlite_category_counts=sqlite_counts,
        postgres_category_counts=postgres_counts,
        category_count_deltas=category_count_deltas,
        category_mismatches=category_mismatches,
        sqlite_only=sqlite_only,
        postgres_only=postgres_only,
        matched_count=matched_count,
    )


def format_parity_summary(result: WarmCaseParityResult) -> str:
    lines = [
        "warm-case parity audit (read-only; not send approval)",
        f"  sqlite rows: {result.sqlite_row_count}",
        f"  postgres rows: {result.postgres_row_count}",
        f"  matched rows: {result.matched_count}",
        f"  category mismatches: {len(result.category_mismatches)}",
        f"  sqlite-only rows: {len(result.sqlite_only)}",
        f"  postgres-only rows: {len(result.postgres_only)}",
        "  sqlite categories:",
    ]
    for category, count in result.sqlite_category_counts.items():
        lines.append(f"    {category}: {count}")
    lines.append("  postgres categories:")
    for category, count in result.postgres_category_counts.items():
        lines.append(f"    {category}: {count}")
    deltas = [
        (category, delta)
        for category, delta in result.category_count_deltas.items()
        if delta != 0
    ]
    if deltas:
        lines.append("  category deltas (postgres - sqlite):")
        for category, delta in deltas:
            sign = "+" if delta > 0 else ""
            lines.append(f"    {category}: {sign}{delta}")
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_parity_outputs(result: WarmCaseParityResult, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "warm_case_parity_summary.json"
    summary_path.write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    category_rows = [
        {
            "category": category,
            "sqlite_count": result.sqlite_category_counts.get(category, 0),
            "postgres_count": result.postgres_category_counts.get(category, 0),
            "delta_postgres_minus_sqlite": result.category_count_deltas.get(category, 0),
        }
        for category in sorted(
            set(result.sqlite_category_counts) | set(result.postgres_category_counts)
        )
    ]
    category_counts_path = out_dir / "warm_case_category_counts.csv"
    _write_csv(
        category_counts_path,
        category_rows,
        [
            "category",
            "sqlite_count",
            "postgres_count",
            "delta_postgres_minus_sqlite",
        ],
    )

    mismatch_path = out_dir / "warm_case_category_mismatches.csv"
    _write_csv(
        mismatch_path,
        result.category_mismatches,
        [
            "match_by",
            "contact_email",
            "subject",
            "sqlite_category",
            "postgres_category",
            "sqlite_case_id",
            "postgres_case_id",
            "sqlite_last_seen_at",
            "postgres_last_seen_at",
        ],
    )

    sqlite_only_path = out_dir / "warm_case_sqlite_only.csv"
    _write_csv(
        sqlite_only_path,
        result.sqlite_only,
        ["contact_email", "subject", "category", "case_id", "last_seen_at", "status"],
    )

    postgres_only_path = out_dir / "warm_case_postgres_only.csv"
    _write_csv(
        postgres_only_path,
        result.postgres_only,
        ["contact_email", "subject", "category", "case_id", "last_seen_at", "status"],
    )

    return {
        "summary_json": summary_path,
        "category_counts_csv": category_counts_path,
        "category_mismatches_csv": mismatch_path,
        "sqlite_only_csv": sqlite_only_path,
        "postgres_only_csv": postgres_only_path,
    }


def run_warm_case_parity_audit(
    *,
    sqlite_json: Path,
    postgres_json: Path,
    out_dir: Path | None = None,
) -> WarmCaseParityResult:
    sqlite_meta, sqlite_items = load_warm_cases_json(sqlite_json)
    postgres_meta, postgres_items = load_warm_cases_json(postgres_json)
    result = compare_warm_case_exports(
        sqlite_items,
        postgres_items,
        sqlite_meta=sqlite_meta,
        postgres_meta=postgres_meta,
    )
    if out_dir is not None:
        write_parity_outputs(result, out_dir)
    return result
