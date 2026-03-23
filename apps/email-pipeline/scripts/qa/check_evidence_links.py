#!/usr/bin/env python3
"""Validate http(s) URLs in hunt + top20 CSVs: scheme/host, then live HTTP with thresholds."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from origenlab_email_pipeline.operational_trust import (
    any_critical_failed,
    check_evidence_url_formats,
    check_urls_batch,
    collect_urls_from_csvs,
    dedupe_urls,
    is_valid_http_url,
    leads_active_paths,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=REPO)
    p.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Per-URL HTTP timeout in seconds (default: 20)",
    )
    p.add_argument(
        "--max-failures",
        type=int,
        default=5,
        help="Fail if more than this many URLs return error status (default: 5)",
    )
    p.add_argument(
        "--max-fail-ratio",
        type=float,
        default=0.15,
        help="Also fail if failure count / checked exceeds this ratio (default: 0.15)",
    )
    return p


def run(args: argparse.Namespace) -> int:
    repo = args.repo_root.resolve()
    paths = leads_active_paths(repo)
    spec: list[tuple[Path, list[str]]] = [
        (paths.top20.resolve(), ["source_url"]),
        (
            paths.hunt.resolve(),
            [
                "url_fuente",
                "url_contacto_compras",
                "url_transparencia_oirs",
                "url_pagina_laboratorio",
                "url_perfil_comprador",
                "url_evidencia_compras",
                "url_evidencia_tecnico",
                "url_evidencia_general",
            ],
        ),
    ]
    raw = collect_urls_from_csvs(spec)
    http_candidates = [u for u in dedupe_urls(raw) if is_valid_http_url(u)]

    checks = [
        check_evidence_url_formats(raw),
        check_urls_batch(
            http_candidates,
            timeout=args.timeout,
            max_failures=args.max_failures,
            max_fail_ratio=args.max_fail_ratio,
        ),
    ]
    for c in checks:
        mark = "OK  " if c.ok else "FAIL"
        crit = " [critical]" if c.critical else ""
        print(f"{mark}{crit} {c.check_id}: {c.message}")
        if c.details:
            d = c.details
            if "invalid_count" in d:
                print(f"       invalid format count: {d.get('invalid_count')}")
            if "checked" in d:
                print(
                    f"       http checked={d.get('checked')} failures={d.get('failure_count')} "
                    f"ratio={d.get('failure_ratio', 0):.3f}"
                )

    return 1 if any_critical_failed(checks) else 0


def main() -> None:
    raise SystemExit(run(build_parser().parse_args()))


if __name__ == "__main__":
    main()
