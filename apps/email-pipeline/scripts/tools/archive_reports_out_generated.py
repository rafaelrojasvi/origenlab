#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# SAFETY (break-glass): MOVES files under ``reports/out`` when ``--apply`` is used.
# Default is DRY-RUN. Never use ``--allow-active-current`` or ``--allow-reference`` during
# an active campaign unless the selection is verified. Run ``plan_reports_out_cleanup.py``
# (read-only) first. This tool does not DELETE files; it only moves into
# ``archive/manual_cleanup/YYYY-MM-DD_<slug>/``. See docs/SCRIPT_MAP.md and CRUD_SAFETY.md.
# -----------------------------------------------------------------------------
"""Controlled archive (move) of generated ``reports/out`` content — **dry-run by default**.

Moves selected files into ``reports/out/archive/manual_cleanup/YYYY-MM-DD_<slug>/`` preserving
relative paths. **Never** deletes. Does not mutate paths outside the ``--reports-out-dir`` root.

Bucket labels match ``scripts/qa/plan_reports_out_cleanup.py`` (imported).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
_SCRIPTS = _TOOLS.parent
_QA_PLAN = _SCRIPTS / "qa" / "plan_reports_out_cleanup.py"
_plan_mod_name = "origenlab_embedded_plan_reports_out_cleanup"
_spec = importlib.util.spec_from_file_location(_plan_mod_name, _QA_PLAN)
if _spec is None or _spec.loader is None:
    raise RuntimeError("cannot load plan_reports_out_cleanup")
_planner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _planner
_spec.loader.exec_module(_planner)  # type: ignore[union-attr]
classify_path = _planner.classify_path
has_active_current = _planner.has_active_current
is_reference = _planner.is_reference
APP_ROOT = _SCRIPTS.parent
_DEFAULT_ROOT = APP_ROOT / "reports" / "out"


def _is_protected_name(name: str) -> bool:
    n = name.casefold()
    return n in (".gitkeep", "readme.md", ".gitignore")


def _under_manual_cleanup(rel: Path) -> bool:
    parts = [p.casefold() for p in rel.parts]
    if len(parts) < 2:
        return False
    return parts[0] == "archive" and parts[1] == "manual_cleanup"


def iter_report_files(root: Path) -> list[Path]:
    out: list[Path] = []
    root = root.resolve()
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            if p.is_symlink():
                continue
        except OSError:
            continue
        rel = p.relative_to(root)
        if _under_manual_cleanup(rel):
            continue
        out.append(p)
    return sorted(out)


def eligible_bucket(bucket: str, args: argparse.Namespace) -> bool:
    if bucket in ("active_current", "reference"):
        if bucket == "active_current" and args.allow_active_current:
            return True
        if bucket == "reference" and args.allow_reference:
            return True
        return False
    m = {
        "tmp_or_scratch": args.include_tmp,
        "lab_or_tatiana": args.include_lab,
        "loose_root_files": args.include_loose_root,
        "unknown": args.include_unknown,
    }
    if bucket not in m:
        return False
    return bool(m[bucket])


def _is_under_active_tree(rel: Path) -> bool:
    """True if path is under top-level ``active/`` (campaign workspace root)."""
    return len(rel.parts) >= 1 and rel.parts[0].casefold() == "active"


def should_skip_protection(rel: Path) -> str | None:
    """Path/name guard (README, .gitkeep) — independent of --allow flags."""
    if any(_is_protected_name(n) for n in rel.parts):
        return "protected (README / .gitkeep / .gitignore in path)"
    return None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument("--reports-out-dir", type=Path, default=None, help="Default: .../reports/out")
    p.add_argument(
        "--archive-slug",
        type=str,
        default="",
        help="Required with --apply. Folder name: YYYY-MM-DD_<slug>.",
    )
    p.add_argument("--apply", action="store_true", help="Perform moves (default: dry-run).")
    p.add_argument("--json-out", type=Path, default=None, help="Write JSON report.")
    p.add_argument("--include-tmp", action="store_true", help="Select tmp_or_scratch bucket.")
    p.add_argument("--include-lab", action="store_true", help="Select lab_or_tatiana bucket.")
    p.add_argument(
        "--include-loose-root",
        action="store_true",
        help="Select loose_root_files (files directly under root).",
    )
    p.add_argument("--include-unknown", action="store_true", help="Select unknown bucket.")
    p.add_argument(
        "--max-files",
        type=int,
        default=50_000,
        help="Refuse --apply if more than N files would move.",
    )
    p.add_argument(
        "--allow-active-current",
        action="store_true",
        help="Include paths under top-level active/ (incl. active/current); not during a live campaign.",
    )
    p.add_argument(
        "--allow-reference",
        action="store_true",
        help="Include reference/ bucket; only when you intend to relocate those files.",
    )
    return p


def collect_selection(
    root: Path, args: argparse.Namespace,
) -> list[tuple[Path, str, str]]:
    selected: list[tuple[Path, str, str]] = []
    for p in iter_report_files(root):
        rel = p.relative_to(root)
        rsn = should_skip_protection(rel)
        if rsn is not None:
            continue
        # ``classify_path`` can label e.g. ``active/my_batch/...`` as tmp (``my_`` rule) without
        # ``active_current``; still treat all of ``active/`` as campaign workspace unless allow.
        if _is_under_active_tree(rel) and not args.allow_active_current:
            continue
        b = classify_path(rel)
        if b in ("archive", "repo_bootstrap"):
            continue
        if not eligible_bucket(b, args):
            continue
        if (has_active_current(rel) and not args.allow_active_current) or (
            is_reference(rel) and not args.allow_reference
        ):
            continue
        selected.append((p, rel.as_posix(), b))
    return selected


def _unique_path(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suf = dest.stem, dest.suffix
    for i in range(1, 10_000):
        c = dest.parent / f"{stem}__conflict_{i}{suf}"
        if not c.exists():
            return c
    raise FileExistsError(dest)


def _main_inner(args: argparse.Namespace) -> int:
    root = (args.reports_out_dir or _DEFAULT_ROOT).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1
    if args.apply:
        slug = (args.archive_slug or "").strip()
        if not slug or slug.startswith("-"):
            print("error: --apply requires a non-empty --archive-slug", file=sys.stderr)
            return 2
    if args.apply and (args.allow_active_current or args.allow_reference):
        print(
            "WARNING: --allow-active-current / --allow-reference: verify selection and campaign state.",
            file=sys.stderr,
        )
    day = date.today().strftime("%Y-%m-%d")
    raw_slug = (args.archive_slug or "preview").strip()
    clean_slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw_slug) or "run"
    dest_dir = root / "archive" / "manual_cleanup" / f"{day}_{clean_slug}"
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"mode: {mode}", file=sys.stdout)
    print(f"reports-out root: {root}", file=sys.stdout)
    print(f"destination: {dest_dir} (relative tree preserved under this folder)", file=sys.stdout)
    selected = collect_selection(root, args)
    n = len(selected)
    if args.apply and n > args.max_files:
        print(
            f"error: {n} files to move exceeds --max-files {args.max_files}.",
            file=sys.stderr,
        )
        return 3
    total = sum(s[0].stat().st_size for s in selected) if selected else 0
    print(f"files to move: {n}", file=sys.stdout)
    print(f"total bytes: {total}", file=sys.stdout)

    moves: list[dict[str, str | int]] = []
    for p, rel, bucket in selected:
        dest = dest_dir / rel
        udest = _unique_path(dest)
        moves.append(
            {
                "source": p.as_posix(),
                "relative": rel,
                "dest_planned": udest.as_posix(),
                "bucket": bucket,
                "size_bytes": p.stat().st_size,
            }
        )
    for i, m in enumerate(moves):
        print(f"  {i + 1}. {m['relative']}  ->  {m['dest_planned']}", file=sys.stdout)
    if args.apply and moves:
        dest_dir.mkdir(parents=True, exist_ok=True)
        for m in moves:
            src = Path(m["source"])
            dst = Path(m["dest_planned"])
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst), copy_function=shutil.copy2)

    if args.json_out is not None:
        payload = {
            "mode": mode,
            "root": root.as_posix(),
            "dest_dir": dest_dir.as_posix(),
            "moves": moves,
            "file_count": n,
            "total_bytes": total,
        }
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"JSON: {args.json_out}", file=sys.stdout)
    print("done.", file=sys.stdout)
    return 0


def run() -> int:
    return _main_inner(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(run())
