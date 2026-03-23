#!/usr/bin/env python3
"""Validate relative targets in markdown links for maintained documentation.

Run from monorepo root:
  python3 docs/check_doc_links.py

Checks:
  - Relative file paths resolve to an existing path under the repo.
  - Optional fragments prefixed with ``m-`` exist as ``<a id="m-...">`` in the target .md.

Skips: http(s), mailto, pure ``#fragment``, and links inside fenced code blocks.
Skips scanning under ``docs/**/ARCHIVE/`` and ``docs/**/generated/``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MARKDOWN_DIRS = [
    REPO_ROOT / "docs",
    REPO_ROOT / "apps" / "web" / "docs",
    REPO_ROOT / "apps" / "email-pipeline" / "docs",
]

EXTRA_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "apps" / "web" / "README.md",
    REPO_ROOT / "apps" / "web" / "AGENTS.md",
    REPO_ROOT / "apps" / "email-pipeline" / "README.md",
    REPO_ROOT / "apps" / "email-pipeline" / "scripts" / "README.md",
    REPO_ROOT / "apps" / "email-pipeline" / "scripts" / "leads" / "README.md",
    REPO_ROOT / "apps" / "email-pipeline" / "reports" / "README.md",
    REPO_ROOT / "apps" / "email-pipeline" / "reports" / "out" / "README.md",
]

SKIP_SUBSTR = ("/ARCHIVE/", "/generated/", "/node_modules/")

LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")


def strip_code_fences(text: str) -> str:
    out: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "".join(out)


def parse_target(raw: str) -> tuple[str, str | None]:
    t = raw.strip()
    if t.startswith("<") and t.endswith(">"):
        t = t[1:-1].strip()
    if ' "' in t:
        t = t.split(' "', 1)[0].strip()
    if " '" in t:
        t = t.split(" '", 1)[0].strip()
    if "#" in t:
        path_part, frag = t.split("#", 1)
        return path_part.strip() or "", frag.strip() or None
    return t, None


def iter_md_files() -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for d in MARKDOWN_DIRS:
        if not d.is_dir():
            continue
        for p in d.rglob("*.md"):
            s = str(p)
            if any(skip in s for skip in SKIP_SUBSTR):
                continue
            if p not in seen:
                seen.add(p)
                files.append(p)
    for f in EXTRA_FILES:
        if f.is_file() and f not in seen:
            seen.add(f)
            files.append(f)
    return sorted(files, key=lambda x: str(x))


def fragment_ok(target_md: Path, frag: str) -> bool:
    content = target_md.read_text(encoding="utf-8")
    return f'id="{frag}"' in content or f"id='{frag}'" in content


def check_file(path: Path) -> list[str]:
    errs: list[str] = []
    text = path.read_text(encoding="utf-8")
    body = strip_code_fences(text)
    for m in LINK_RE.finditer(body):
        raw = m.group(2).strip()
        if not raw or raw.startswith("#") or "://" in raw or raw.startswith("mailto:"):
            continue
        path_part, frag = parse_target(raw)
        if not path_part:
            continue
        resolved = (path.parent / path_part).resolve()
        try:
            resolved.relative_to(REPO_ROOT)
        except ValueError:
            errs.append(f"broken link [{raw}] (escapes repo)")
            continue
        if not resolved.exists():
            errs.append(f"broken link [{raw}] (missing path)")
            continue
        if frag and frag.startswith("m-") and resolved.suffix.lower() == ".md":
            if not fragment_ok(resolved, frag):
                errs.append(f"broken link [{raw}] (missing anchor id={frag!r})")
    return errs


def main() -> int:
    files = iter_md_files()
    failures: list[tuple[str, list[str]]] = []
    for md in files:
        row = check_file(md)
        if row:
            failures.append((str(md.relative_to(REPO_ROOT)), row))
    if failures:
        for src, rows in failures:
            for r in rows:
                print(f"{src}: {r}")
        return 1
    print(f"OK: checked links in {len(files)} markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
