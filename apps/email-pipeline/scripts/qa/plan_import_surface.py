#!/usr/bin/env python3
"""Read-only import / reference surface planner (stdlib + AST only).

Scans Python imports, docs/tests path references, and ``uv run origenlab`` command mentions.
**Does not** import pipeline modules, execute scripts, or mutate SQLite/Postgres/Gmail.

Output defaults to ``reports/local/import-surface-audit/<timestamp>/``.

**Planning guidance only** — zero import/reference counts do **not** prove deletion safety.
Use together with ``plan_function_surface.py`` before file moves or deletions.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SRC = APP_ROOT / "src" / "origenlab_email_pipeline"
_DEFAULT_SCRIPTS = APP_ROOT / "scripts"
_DEFAULT_TESTS = APP_ROOT / "tests"
_DEFAULT_DOCS = APP_ROOT / "docs"
_DEFAULT_OUT_PARENT = APP_ROOT / "reports" / "local" / "import-surface-audit"

PACKAGE = "origenlab_email_pipeline"

RE_SCRIPT_PATH = re.compile(
    r"(?i)(?<![\w./])(?:\.\./)*scripts/[\w./-]+\.py",
)
RE_SRC_MODULE_PATH = re.compile(
    r"(?i)(?<![\w./])(?:\.\./)*src/origenlab_email_pipeline/[\w./-]+\.py",
)
RE_PYTHON_SCRIPTS = re.compile(
    r"(?i)(?:uv run )?python\s+(?:-m\s+)?(?:\.\./)*scripts/[\w./-]+\.py",
)
RE_ORIGENLAB_CMD = re.compile(
    r"(?i)uv run origenlab\s+([\w-]+)",
)
RE_FACADE_MARKER = re.compile(
    r"(?i)Implementation currently lives in|re-export only|from\s+[\.\w]+\s+import\s+\*",
)

DANGEROUS_SCRIPT_FRAGMENTS = (
    "scripts/tools/purge",
    "gmail_send.py",
    "send_inline",
    "postgres_mirror",
    "sync_dashboard_postgres",
    "alembic",
    "mark_sent_batch",
    "build_business_mart.py",
)


@dataclass(frozen=True, slots=True)
class ImportEdge:
    importer_path: str
    importer_area: str
    import_kind: str
    target_module: str
    target_symbol: str
    lineno: int


@dataclass
class ScanResult:
    import_edges: list[ImportEdge] = field(default_factory=list)
    doc_script_refs: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    test_script_refs: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    doc_module_refs: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    test_module_refs: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    command_refs: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    all_py_modules: set[str] = field(default_factory=set)
    all_scripts: set[str] = field(default_factory=set)
    facade_module_paths: set[str] = field(default_factory=set)


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _normalize_script_ref(raw: str) -> str:
    ref = raw.strip().strip("`").replace("\\", "/")
    while ref.startswith("../"):
        ref = ref[3:]
    if not ref.startswith("scripts/"):
        idx = ref.find("scripts/")
        if idx >= 0:
            ref = ref[idx:]
    return ref


def _normalize_module_ref(raw: str) -> str:
    ref = raw.strip().strip("`").replace("\\", "/")
    while ref.startswith("../"):
        ref = ref[3:]
    if not ref.startswith("src/origenlab_email_pipeline/"):
        idx = ref.find("src/origenlab_email_pipeline/")
        if idx >= 0:
            ref = ref[idx:]
    return ref


def _module_path_from_src_rel(rel: str) -> str:
    """``src/origenlab_email_pipeline/foo/bar.py`` -> ``origenlab_email_pipeline.foo.bar``."""
    if rel.startswith("src/origenlab_email_pipeline/"):
        rel = rel[len("src/origenlab_email_pipeline/") :]
    if rel.endswith(".py"):
        rel = rel[:-3]
    if rel.endswith("/__init__"):
        rel = rel[: -len("/__init__")]
    return f"{PACKAGE}.{rel.replace('/', '.')}"


def _src_rel_from_module(module: str) -> str | None:
    if not module.startswith(PACKAGE):
        return None
    suffix = module[len(PACKAGE) :].lstrip(".")
    if not suffix:
        return f"src/{PACKAGE}/__init__.py"
    return f"src/{PACKAGE}/{suffix.replace('.', '/')}.py"


def iter_py_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out: list[Path] = []
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        out.append(p)
    return sorted(out)


def iter_md_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.md") if "__pycache__" not in p.parts)


def _parse_ast(text: str) -> ast.AST | None:
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def _resolve_relative(module: str | None, level: int, current_rel: str) -> str:
    if level == 0:
        return module or ""
    parts = current_rel.replace("\\", "/").split("/")
    if parts[-1].endswith(".py"):
        parts = parts[:-1]
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[0] == PACKAGE:
        parts = parts[1:]
    if level > len(parts):
        base_parts: list[str] = []
    else:
        base_parts = parts[: len(parts) - level]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(base_parts)


def extract_imports(text: str, rel_path: str, area: str) -> list[ImportEdge]:
    tree = _parse_ast(text)
    if tree is None:
        return []
    edges: list[ImportEdge] = []
    pkg_rel = rel_path
    if rel_path.startswith("src/origenlab_email_pipeline/"):
        pkg_rel = rel_path[len("src/origenlab_email_pipeline/") :]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                sym = alias.asname or alias.name.split(".")[-1]
                kind = "import"
                if mod.startswith(PACKAGE):
                    edges.append(
                        ImportEdge(rel_path, area, kind, mod, sym, node.lineno)
                    )
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            mod = node.module or ""
            resolved = _resolve_relative(mod, level, pkg_rel)
            if level > 0:
                full = f"{PACKAGE}.{resolved}" if resolved else PACKAGE
                kind = "relative_from"
            else:
                full = mod
                kind = "from_import"
            if full.startswith(PACKAGE) or mod.startswith(PACKAGE):
                target = full if full.startswith(PACKAGE) else mod
                for alias in node.names:
                    sym = alias.name
                    edges.append(
                        ImportEdge(rel_path, area, kind, target, sym, node.lineno)
                    )
    return edges


def _scan_text_references(text: str, source_label: str, result: ScanResult) -> None:
    for match in RE_SCRIPT_PATH.finditer(text):
        ref = _normalize_script_ref(match.group(0))
        if ref.endswith(".py"):
            if source_label.startswith("doc:"):
                result.doc_script_refs[ref].add(source_label)
            elif source_label.startswith("test:"):
                result.test_script_refs[ref].add(source_label)
    for match in RE_SRC_MODULE_PATH.finditer(text):
        ref = _normalize_module_ref(match.group(0))
        if source_label.startswith("doc:"):
            result.doc_module_refs[ref].add(source_label)
        elif source_label.startswith("test:"):
            result.test_module_refs[ref].add(source_label)
    for match in RE_PYTHON_SCRIPTS.finditer(text):
        chunk = match.group(0)
        sm = RE_SCRIPT_PATH.search(chunk)
        if sm:
            ref = _normalize_script_ref(sm.group(0))
            if source_label.startswith("doc:"):
                result.doc_script_refs[ref].add(source_label)
            elif source_label.startswith("test:"):
                result.test_script_refs[ref].add(source_label)
    for match in RE_ORIGENLAB_CMD.finditer(text):
        cmd = match.group(1).strip()
        if cmd:
            result.command_refs[cmd].add(source_label)


def detect_facade_pairs(src_root: Path) -> set[str]:
    """Root vs ``core/`` basename pairs — do not treat low-ref side as delete candidate."""
    by_basename: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    src_root = src_root.resolve()
    for p in iter_py_files(src_root):
        rel = f"src/origenlab_email_pipeline/{p.relative_to(src_root).as_posix()}"
        by_basename[p.name].append((rel, p))

    facades: set[str] = set()
    for entries in by_basename.values():
        if len(entries) < 2:
            continue
        rels = [r for r, _ in entries]
        core = [r for r in rels if "/core/" in r]
        non_core = [r for r in rels if "/core/" not in r]
        if core and non_core:
            facades.update(rels)
            continue
        for rel, abs_path in entries:
            try:
                text = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if RE_FACADE_MARKER.search(text) and len(text.splitlines()) < 25:
                facades.add(rel)
    return facades


def is_dangerous_script(path: str) -> bool:
    low = path.lower().replace("\\", "/")
    return any(frag.lower() in low for frag in DANGEROUS_SCRIPT_FRAGMENTS)


def is_dangerous_module(path: str) -> bool:
    low = path.lower()
    return any(
        x in low
        for x in (
            "gmail_send",
            "postgres_mirror",
            "purge_",
            "sync_dashboard_postgres",
            "mart_core_postgres",
        )
    )


def scan_python_tree(root: Path, area: str, prefix: str, result: ScanResult) -> None:
    root = root.resolve()
    for p in iter_py_files(root):
        rel = f"{prefix}/{p.relative_to(root).as_posix()}"
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if area == "src":
            result.all_py_modules.add(rel)
        elif area == "script":
            result.all_scripts.add(rel)
        elif area == "test":
            pass
        result.import_edges.extend(extract_imports(text, rel, area))


def scan_markdown_files(paths: list[Path], label_prefix: str, result: ScanResult) -> None:
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        label = f"{label_prefix}:{p.as_posix()}"
        _scan_text_references(text, label, result)


def scan_roots(
    src_root: Path,
    scripts_root: Path,
    tests_root: Path,
    docs_root: Path,
) -> ScanResult:
    result = ScanResult()
    scan_python_tree(src_root, "src", "src/origenlab_email_pipeline", result)
    scan_python_tree(scripts_root, "script", "scripts", result)
    scan_python_tree(tests_root, "test", "tests", result)

    extra_docs = [
        p
        for p in (APP_ROOT / "README.md", APP_ROOT / "AGENTS.md")
        if p.is_file()
    ]
    scan_markdown_files(iter_md_files(docs_root) + extra_docs, "doc", result)
    for p in iter_py_files(tests_root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _scan_text_references(text, f"test:{p.as_posix()}", result)

    result.facade_module_paths = detect_facade_pairs(src_root)
    return result


def _module_import_count(module_path: str, module_name: str, result: ScanResult) -> int:
    count = 0
    for edge in result.import_edges:
        if edge.target_module == module_name or edge.target_module.startswith(f"{module_name}."):
            count += 1
        src_rel = _src_rel_from_module(edge.target_module)
        if src_rel == module_path:
            count += 1
    return count


IMPORT_EDGE_FIELDS = [
    "importer_path",
    "importer_area",
    "import_kind",
    "target_module",
    "target_symbol",
    "lineno",
]


def write_reports(result: ScanResult, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    edge_rows = [
        {
            "importer_path": e.importer_path,
            "importer_area": e.importer_area,
            "import_kind": e.import_kind,
            "target_module": e.target_module,
            "target_symbol": e.target_symbol,
            "lineno": e.lineno,
        }
        for e in sorted(
            result.import_edges,
            key=lambda x: (x.target_module, x.importer_path, x.lineno),
        )
    ]
    _write_csv(out_dir / "import_edges.csv", edge_rows, IMPORT_EDGE_FIELDS)

    module_rows: list[dict[str, Any]] = []
    for mod_path in sorted(result.all_py_modules):
        mod_name = _module_path_from_src_rel(mod_path)
        py_count = _module_import_count(mod_path, mod_name, result)
        doc_count = len(result.doc_module_refs.get(mod_path, set()))
        test_count = len(result.test_module_refs.get(mod_path, set()))
        is_facade = mod_path in result.facade_module_paths
        dangerous = is_dangerous_module(mod_path)
        module_rows.append(
            {
                "module_path": mod_path,
                "module_name": mod_name,
                "python_import_count": py_count,
                "doc_reference_count": doc_count,
                "test_reference_count": test_count,
                "total_references": py_count + doc_count + test_count,
                "is_facade_pair": is_facade,
                "dangerous_path": dangerous,
                "zero_import_not_delete_proof": py_count == 0,
            }
        )
    _write_csv(
        out_dir / "module_reference_summary.csv",
        module_rows,
        list(module_rows[0].keys()) if module_rows else ["module_path"],
    )

    script_rows: list[dict[str, Any]] = []
    for script_path in sorted(result.all_scripts):
        doc_count = len(result.doc_script_refs.get(script_path, set()))
        test_count = len(result.test_script_refs.get(script_path, set()))
        py_count = sum(
            1
            for e in result.import_edges
            if script_path in e.importer_path or script_path in e.target_module
        )
        cmd_count = 0
        dangerous = is_dangerous_script(script_path)
        total = doc_count + test_count + py_count
        zero_ref = doc_count == 0 and test_count == 0
        not_delete = zero_ref and not dangerous
        script_rows.append(
            {
                "script_path": script_path,
                "python_import_count": py_count,
                "doc_reference_count": doc_count,
                "test_reference_count": test_count,
                "command_reference_count": cmd_count,
                "total_references": total,
                "dangerous_path": dangerous,
                "zero_reference_not_delete_candidate": not_delete,
            }
        )
    _write_csv(
        out_dir / "script_reference_summary.csv",
        script_rows,
        list(script_rows[0].keys()) if script_rows else ["script_path"],
    )

    zero_mod_rows = [
        r
        for r in module_rows
        if r["python_import_count"] == 0
        and not r["module_path"].endswith("__init__.py")
        and not r["is_facade_pair"]
    ]
    _write_csv(
        out_dir / "zero_python_import_modules.csv",
        zero_mod_rows,
        list(zero_mod_rows[0].keys()) if zero_mod_rows else ["module_path"],
    )

    zero_script_rows = [
        r
        for r in script_rows
        if r["doc_reference_count"] == 0
        and r["test_reference_count"] == 0
        and not r["dangerous_path"]
    ]
    _write_csv(
        out_dir / "zero_doc_reference_scripts.csv",
        zero_script_rows,
        list(zero_script_rows[0].keys()) if zero_script_rows else ["script_path"],
    )

    cmd_rows: list[dict[str, Any]] = []
    for cmd, sources in sorted(result.command_refs.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        cmd_rows.append(
            {
                "command": cmd,
                "reference_count": len(sources),
                "reference_sources": "; ".join(sorted(sources)[:10]),
            }
        )
    _write_csv(
        out_dir / "command_reference_summary.csv",
        cmd_rows,
        ["command", "reference_count", "reference_sources"],
    )

    summary = build_summary(result, out_dir, module_rows, script_rows, cmd_rows)
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    return build_json_summary(result, out_dir, module_rows, script_rows, cmd_rows)


def build_json_summary(
    result: ScanResult,
    out_dir: Path,
    module_rows: list[dict[str, Any]],
    script_rows: list[dict[str, Any]],
    cmd_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "out_dir": str(out_dir),
        "import_edge_count": len(result.import_edges),
        "module_count": len(result.all_py_modules),
        "script_count": len(result.all_scripts),
        "facade_pair_module_count": len(result.facade_module_paths),
        "zero_python_import_module_count": sum(
            1 for r in module_rows if r["python_import_count"] == 0 and not r["is_facade_pair"]
        ),
        "zero_doc_reference_script_count": sum(
            1
            for r in script_rows
            if r["doc_reference_count"] == 0 and r["test_reference_count"] == 0
        ),
        "dangerous_script_count": sum(1 for r in script_rows if r["dangerous_path"]),
        "top_imported_modules": sorted(
            [
                {"module_name": r["module_name"], "python_import_count": r["python_import_count"]}
                for r in module_rows
            ],
            key=lambda x: (-x["python_import_count"], x["module_name"]),
        )[:15],
        "top_referenced_scripts": sorted(
            script_rows,
            key=lambda r: (-r["total_references"], r["script_path"]),
        )[:15],
        "top_commands": cmd_rows[:15],
    }


def build_summary(
    result: ScanResult,
    out_dir: Path,
    module_rows: list[dict[str, Any]],
    script_rows: list[dict[str, Any]],
    cmd_rows: list[dict[str, Any]],
) -> str:
    data = build_json_summary(result, out_dir, module_rows, script_rows, cmd_rows)
    lines = [
        "# Import / reference surface audit (read-only planner)",
        "",
        f"- Generated: `{data['generated_at']}`",
        f"- Output dir: `{out_dir}`",
        "",
        "## Counts",
        "",
        f"- Import edges: **{data['import_edge_count']}**",
        f"- Src modules scanned: **{data['module_count']}**",
        f"- Scripts scanned: **{data['script_count']}**",
        f"- Facade-pair modules: **{data['facade_pair_module_count']}**",
        f"- Zero Python-import modules (non-facade): **{data['zero_python_import_module_count']}**",
        f"- Zero doc/test reference scripts: **{data['zero_doc_reference_script_count']}**",
        f"- Dangerous scripts flagged: **{data['dangerous_script_count']}**",
        "",
        "## Top imported modules",
        "",
    ]
    for row in data["top_imported_modules"][:10]:
        lines.append(f"- `{row['module_name']}` — {row['python_import_count']} import edges")
    lines.extend(["", "## Top referenced scripts", ""])
    for row in data["top_referenced_scripts"][:10]:
        lines.append(
            f"- `{row['script_path']}` — total refs {row['total_references']} "
            f"(doc {row['doc_reference_count']}, test {row['test_reference_count']})"
        )
    lines.extend(["", "## Top `uv run origenlab` command references", ""])
    for row in data["top_commands"][:10]:
        lines.append(f"- `{row['command']}` — {row['reference_count']} doc/test mentions")
    lines.extend(
        [
            "",
            "## Outputs",
            "",
            "- `import_edges.csv`",
            "- `module_reference_summary.csv`",
            "- `script_reference_summary.csv`",
            "- `zero_python_import_modules.csv`",
            "- `zero_doc_reference_scripts.csv`",
            "- `command_reference_summary.csv`",
            "",
            "## Safety",
            "",
            "Zero import/reference counts **do not** prove deletion safety.",
            "Dangerous paths (purge, Gmail send, Postgres mirror, outbound apply) stay flagged even when unreferenced.",
            "Root/core facade pairs are **not** delete candidates based on low references alone.",
            "Use with `plan_function_surface.py` before any file moves or deletions.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--src-dir", type=Path, default=None)
    parser.add_argument("--scripts-dir", type=Path, default=None)
    parser.add_argument("--tests-dir", type=Path, default=None)
    parser.add_argument("--docs-dir", type=Path, default=None)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Report directory (default: reports/local/import-surface-audit/<timestamp>/)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout.")
    parser.add_argument(
        "--stdout-only",
        action="store_true",
        help="With --json, skip writing CSV/summary files.",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    src_root = (args.src_dir or _DEFAULT_SRC).resolve()
    scripts_root = (args.scripts_dir or _DEFAULT_SCRIPTS).resolve()
    tests_root = (args.tests_dir or _DEFAULT_TESTS).resolve()
    docs_root = (args.docs_dir or _DEFAULT_DOCS).resolve()

    if args.out_dir is not None:
        out_dir = args.out_dir.resolve()
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = (_DEFAULT_OUT_PARENT / stamp).resolve()

    result = scan_roots(src_root, scripts_root, tests_root, docs_root)

    if args.json and args.stdout_only:
        summary = build_json_summary(result, out_dir, [], [], [])
    else:
        summary = write_reports(result, out_dir)

    print("plan_import_surface (read-only planner — not deletion authority)", file=sys.stdout)
    print(f"src-dir: {src_root}", file=sys.stdout)
    print(f"import-edges: {summary.get('import_edge_count', len(result.import_edges))}", file=sys.stdout)
    if not (args.json and args.stdout_only):
        print(f"wrote reports: {out_dir}", file=sys.stdout)
    if args.json:
        print(json.dumps(summary, indent=2), file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
