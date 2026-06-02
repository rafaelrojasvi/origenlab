#!/usr/bin/env python3
"""Read-only `scripts/` sprawl and consolidation plan (no file edits, DB, or network)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
_MAX_READ = 60_000

_READ_ONLY_QA: frozenset[str] = frozenset(
    {
        "check_reproducibility.py",
        "plan_reports_out_cleanup.py",
        "plan_script_consolidation.py",
    }
)

# Root-level ``scripts/<name>.py`` shims removed in Phase 5B; canonical paths are under scripts/leads/advanced/
_ROOT_COMPATIBILITY_WRAPPERS: frozenset[str] = frozenset()

_TTABLE = re.compile(
    r"^\s*\|\s*`?(scripts/[\w./-]+\.py)`?\s*\|\s*([A-Z0-9_]+)\s*\|",
    re.IGNORECASE,
)
_P_SCR = re.compile(r"scripts/[\w./-]+\.py", re.IGNORECASE)
_SAFETY = re.compile(
    r"(?i)(BREAK-?GLASS|DANGEROUS|#+\s*SAFETY|SAFETY\s*[\(—:])",
)
_MUT = re.compile(
    r"""(?ix)
    \b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|UPSERT)\b
    |\.execute\s*\(
    |executemany\s*\(
    |\.commit\s*\(
    """,
)
_SEND = re.compile(
    r"(?ix)\bsendmail\b|\bsmtplib\b|googleapiclient|MimeText|send_message|send_inline|Gmail API",
)
_CLI = re.compile(
    r"(?m)(^\s*import\s+(argparse|click|typer)\b|^\s*from\s+(argparse|click|typer)\s+import)",
)
_APPLY = re.compile(r"--apply")


@dataclass(frozen=True, slots=True)
class Row:
    path: str
    rel_from_scripts: str
    size_bytes: int
    primary_bucket: str
    has_cli: bool
    has_apply: bool
    mutation_like: bool
    send_like: bool
    safety_header: bool
    in_docs: bool
    in_tests: bool
    is_wrapper_signal: bool
    proposed_action: str


def to_rel(s: str) -> str:
    t = s.strip().strip("`")
    return t[8:] if t.startswith("scripts/") else t


def parse_map_tags(path: Path) -> dict[str, set[str]]:
    m: dict[str, set[str]] = {}
    if not path.is_file():
        return m
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        g = _TTABLE.match(line)
        if g:
            m.setdefault(g.group(2).upper(), set()).add(g.group(1))
    return m


def break_glass_section_paths(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    t = path.read_text(encoding="utf-8", errors="replace")
    b = re.search(r"(?ms)^##\s+Break-glass scripts\b.*?(?=^##\s+|\Z)", t)
    if not b:
        return set()
    return set(_P_SCR.findall(b.group(0)))


def in_break_table(rel: str, break_table: set[str]) -> bool:
    fscripts = f"scripts/{rel}"
    if fscripts in break_table:
        return True
    for b in break_table:
        if to_rel(b) == rel:
            return True
    return False


def _h(text: str) -> str:
    return "\n".join(text.splitlines()[:160])


def is_break_glass(
    rel: str, base: str, p0: str, text: str, break_table: set[str],
) -> bool:
    if in_break_table(rel, break_table) and base not in _READ_ONLY_QA:
        return True
    if base in _READ_ONLY_QA:
        return False
    h = _h(text)
    if _SAFETY.search(h):
        return True
    bl = base.lower()
    if p0 == "tools" and "purge" in bl:
        return True
    if p0 == "validation" and "extract_attachment_text" in bl:
        return True
    if p0 == "mart" and "build_business_mart" in bl:
        return True
    if p0 == "commercial" and "build_commercial_intel" in bl:
        return True
    if p0 == "qa" and bl == "sync_outreach_batch_from_ingested_bounces.py":
        return True
    if p0 == "tools" and ("flag_ndr" in bl or "non_delivery" in bl) and "flag" in bl:
        return True
    if "send_inline" in bl:
        return True
    return False


def is_wrapper(n_lines: int, text: str) -> bool:
    if n_lines < 3 or n_lines > 50:
        return False
    low = text.lower()
    if n_lines < 35 and re.search(
        r"subprocess\.(run|call|check_output)|importlib|runpy\.",
        text,
    ) and "leads" in low:
        return True
    if n_lines < 34 and re.search(
        r"Path\(__file__\).*(/|\\\\)leads/(\./)?advanced", text, re.IGNORECASE,
    ):
        return True
    return bool(
        n_lines < 24
        and re.search(r"(?i)if\s+__name__\s*==\s*['\"]__main__['\"]", text)
        and re.search(r"(?m)exec\(|import_module\(", text)
        and "leads" in low
    )


def classify(
    rel: str, base: str, p0: str, text: str, n_lines: int,
    tset: dict[str, set[str]], break_table: set[str],
) -> str:
    daily = {to_rel(x) for x in tset.get("OPS_DAILY", set())}
    core = {to_rel(x) for x in tset.get("OPS_CORE", set())}
    audit = {to_rel(x) for x in tset.get("OPS_AUDIT", set())}
    maint = (
        {to_rel(x) for x in tset.get("OPS_MAINT", set())}
        | {to_rel(x) for x in tset.get("ARCHIVE_LANE", set())}
        | {to_rel(x) for x in tset.get("CONSOLIDATE", set())}
    )
    mig = {to_rel(x) for x in tset.get("OPS_MIGRATE", set())}
    in_break = is_break_glass(rel, base, p0, text, break_table)
    wsig = is_wrapper(n_lines, text) and rel not in daily and rel not in core
    wsig = wsig and base not in _READ_ONLY_QA and base not in ("_bootstrap.py",) and p0 != "migrate"

    if p0 == "migrate":
        return "migration"
    if in_break:
        return "break_glass"
    if p0 in ("tatiana", "dataset", "ml") or rel.startswith("leads/campaigns/"):
        return "lab_archive"
    if rel == "_bootstrap.py":
        return "infrastructure_core"
    if rel == "validate_supplier_workbook.py":
        return "maintenance"
    if rel == "qa/extract_chilecompra_lab_buyers_from_xlsx.py":
        return "maintenance"
    if "/" not in rel and rel in _ROOT_COMPATIBILITY_WRAPPERS:
        return "compatibility_wrapper"
    if wsig:
        return "wrapper_or_duplicate_candidate"
    if rel in daily:
        return "daily"
    if rel in core:
        return "core_operator"
    if rel in audit or (rel in mig and "validate" in rel):
        return "audit_readonly"
    if rel in maint:
        return "maintenance"
    if p0 == "qa" and (
        base in _READ_ONLY_QA
        or base.startswith(("export_", "check_", "plan_"))
        or base
        in (
            "print_outbound_run_summary.py",
            "publish_gate.py",
            "verify_client_pack_consistency.py",
        )
        or "audit" in base
        or "approve" in base
    ):
        return "audit_readonly"
    if p0 == "tools" and base == "inspect_sqlite.py":
        return "audit_readonly"
    if p0 in (
        "mart", "commercial", "reports", "validation", "ingest", "pipeline", "leads", "tools",
    ) or p0.startswith("import_supplier") or (base and base.startswith("import_supplier")):
        return "maintenance"
    return "unknown"


def action_for(
    bucket: str, in_docs: bool, relp: str,
) -> str:
    if relp in (
        "validate_supplier_workbook.py",
        "qa/extract_chilecompra_lab_buyers_from_xlsx.py",
    ) and bucket == "maintenance":
        return "keep_maintenance"
    if relp == "_bootstrap.py" or bucket == "infrastructure_core":
        return "keep"
    if bucket == "compatibility_wrapper":
        return "keep"
    if bucket == "unknown" and not in_docs:
        return "deprecate_in_docs_later"
    return {
        "daily": "keep_daily",
        "core_operator": "keep",
        "audit_readonly": "keep_audit",
        "infrastructure_core": "keep",
        "maintenance": "keep",
        "migration": "keep",
        "lab_archive": "archive_later",
        "break_glass": "keep_break_glass",
        "compatibility_wrapper": "keep",
        "wrapper_or_duplicate_candidate": "wrap_later",
        "unknown": "review_unknown",
    }.get(bucket, "review_unknown")


def load_corpus(roots: list[Path], ext: frozenset[str]) -> str:
    ch: list[str] = []
    for base in roots:
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.suffix.lower() not in ext:
                continue
            if ".venv" in p.parts or "node_modules" in p.parts:
                continue
            if "generated" in p.parts and p.suffix == ".md" and "docs" in p.parts:
                continue
            try:
                ch.append(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return "\n\n".join(ch)


def ref_in_corpus(rel: str, corpus: str) -> bool:
    if f"scripts/{rel}" in corpus or f"scripts\\{rel}" in corpus:
        return True
    bn = rel.split("/")[-1]
    if bn in corpus and "scripts" in corpus:
        return len(bn) > 6
    return False


def scan(scripts_dir: Path, map_path: Path, app_root: Path | None = None) -> list[Row]:
    root = app_root or APP_ROOT
    tset = parse_map_tags(map_path)
    break_table = break_glass_section_paths(map_path)
    docs = load_corpus(
        [root / "docs", root / "scripts", root],
        frozenset({".md", ".mako"}),
    )
    tests = load_corpus(
        [root / "tests"],
        frozenset({".py"}),
    )
    out: list[Row] = []
    sdir = scripts_dir.resolve()
    for f in sorted(sdir.rglob("*.py")):
        if "__pycache__" in f.parts:  # noqa: SIM201
            continue
        if f.suffix != ".py":
            continue
        relp = f.relative_to(sdir).as_posix()
        p0 = relp.split("/")[0] if "/" in relp else relp
        try:
            body = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        btrim = body[:_MAX_READ]
        n_lines = body.count("\n") + 1
        st = f.stat()
        size = st.st_size
        bucket = classify(
            relp, f.name, p0, btrim, n_lines, tset, break_table,
        )
        in_doc = ref_in_corpus(relp, docs)
        in_tst = ref_in_corpus(relp, tests)
        wflag = (bucket == "compatibility_wrapper") or (
            bucket == "wrapper_or_duplicate_candidate" and is_wrapper(n_lines, btrim)
        )
        row = Row(
            path="scripts/" + relp,
            rel_from_scripts=relp,
            size_bytes=size,
            primary_bucket=bucket,
            has_cli=bool(_CLI.search(btrim)),
            has_apply=bool(_APPLY.search(btrim)),
            mutation_like=bool(_MUT.search(btrim)),
            send_like=bool(_SEND.search(btrim)),
            safety_header=bool(_SAFETY.search(_h(btrim))),
            in_docs=bool(in_doc),
            in_tests=bool(in_tst),
            is_wrapper_signal=bool(wflag),
            proposed_action=action_for(bucket, in_doc, relp),
        )
        out.append(row)
    return out


def print_report(rows: list[Row]) -> None:
    by: dict[str, int] = {}
    for r in rows:
        by[r.primary_bucket] = by.get(r.primary_bucket, 0) + 1
    n_apply = sum(1 for r in rows if r.has_apply)
    n_safety = sum(1 for r in rows if r.safety_header)
    n_docs = sum(1 for r in rows if r.in_docs)
    n_tests = sum(1 for r in rows if r.in_tests)
    comp = [r for r in rows if r.primary_bucket == "compatibility_wrapper"]
    wrap = [r for r in rows if r.primary_bucket == "wrapper_or_duplicate_candidate"]
    unk = [r for r in rows if r.primary_bucket == "unknown"]
    bg = [r for r in rows if r.primary_bucket == "break_glass"]
    print("total .py under scripts/:", len(rows), file=sys.stdout)
    print(
        f"contract-style counts: compatibility_wrapper={len(comp)} | unknown={len(unk)} | break_glass={len(bg)}",
        file=sys.stdout,
    )
    print("--- by bucket ---", file=sys.stdout)
    for k, v in sorted(by.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {k}: {v}", file=sys.stdout)
    print(
        f"with --apply in file: {n_apply}\n"
        f"with safety-style header/keyword: {n_safety}\n"
        f"referenced in docs: {n_docs}\n"
        f"referenced in tests: {n_tests}\n"
    )
    print("--- compatibility root wrappers (scripts/ → leads/advanced) ---", file=sys.stdout)
    for r in comp[:200]:
        print(f"  {r.path}", file=sys.stdout)
    print("--- other wrapper/duplicate candidates ---", file=sys.stdout)
    for r in wrap[:200]:
        print(f"  {r.path}", file=sys.stdout)
    print("--- unknown scripts ---", file=sys.stdout)
    for r in sorted(unk, key=lambda x: x.path)[:200]:
        print(f"  {r.path}", file=sys.stdout)
    print("--- break_glass scripts ---", file=sys.stdout)
    for r in sorted(bg, key=lambda x: x.path)[:200]:
        print(f"  {r.path}", file=sys.stdout)
    print("--- suggested next actions (planning) ---", file=sys.stdout)
    print(
        "  - Triage 'unknown' with owners; add SCRIPT_MAP or RUNBOOK pointers before any move.\n"
        "  - 'compatibility_wrapper' entries are documented root shims; do not remove until\n"
        "    docs/tests/operator paths no longer reference the root path (see wrapper docstrings).\n"
        "  - Confirm 'wrapper_or_duplicate_candidate' with tests (test_critical_script_paths); "
        "wrap later, do not delete yet.\n"
        "  - break_glass: keep; never merge without --help parity + new tests + SCRIPT_MAP table.\n"
        "  - Re-run this planner after doc/script renames; do not change behavior from this report alone.",
        file=sys.stdout,
    )


def _rows_to_json(rows: list[Row], scripts_dir: str, map_path: str) -> dict:
    by: dict[str, int] = {}
    for r in rows:
        by[r.primary_bucket] = by.get(r.primary_bucket, 0) + 1
    return {
        "scripts_dir": scripts_dir,
        "script_map_path": map_path,
        "count_by_bucket": by,
        "total_py": len(rows),
        "with_apply": sum(1 for r in rows if r.has_apply),
        "with_safety_header": sum(1 for r in rows if r.safety_header),
        "in_docs": sum(1 for r in rows if r.in_docs),
        "in_tests": sum(1 for r in rows if r.in_tests),
        "rows": [asdict(r) for r in rows],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--scripts-dir",
        type=Path,
        default=None,
        help="Default: apps/email-pipeline/scripts",
    )
    p.add_argument(
        "--map",
        type=Path,
        default=None,
        help="Path to SCRIPT_MAP.md (default: apps/email-pipeline/docs/SCRIPT_MAP.md)",
    )
    p.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Write JSON report to this new file only.",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    sdir = args.scripts_dir or (APP_ROOT / "scripts")
    mpath = args.map or (APP_ROOT / "docs" / "SCRIPT_MAP.md")
    sdir = sdir.resolve()
    mpath = mpath.resolve()
    if not sdir.is_dir():
        print(f"error: not a directory: {sdir}", file=sys.stderr)
        return 1
    rows = scan(sdir, mpath, app_root=APP_ROOT)
    print_report(rows)
    if args.json_out is not None:
        jp = args.json_out.resolve()
        jp.parent.mkdir(parents=True, exist_ok=True)
        data = _rows_to_json(
            rows, str(sdir), str(mpath)
        )
        jp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"wrote json report: {jp}", file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
