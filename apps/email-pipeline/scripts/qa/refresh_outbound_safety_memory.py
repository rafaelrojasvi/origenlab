#!/usr/bin/env python3
"""Run canonical outbound anti-repeat memory refresh + validation steps.

Default behavior treats readiness ``ready_with_warnings`` as success.
Use ``--fail-on-ready-with-warnings`` to enforce stricter gating.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


class StepResult:
    def __init__(
        self,
        *,
        name: str,
        command: list[str],
        returncode: int,
        elapsed_s: float,
        stdout: str,
        stderr: str,
        hard_failed: bool,
        note: str = "",
    ) -> None:
        self.name = name
        self.command = command
        self.returncode = returncode
        self.elapsed_s = elapsed_s
        self.stdout = stdout
        self.stderr = stderr
        self.hard_failed = hard_failed
        self.note = note


def _extract_readiness_verdict(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.startswith("Verdict:"):
            return line.split(":", 1)[1].strip()
    return None


def _run_step(name: str, command: list[str]) -> StepResult:
    start = time.perf_counter()
    cp = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.perf_counter() - start
    return StepResult(
        name=name,
        command=command,
        returncode=cp.returncode,
        elapsed_s=elapsed,
        stdout=cp.stdout,
        stderr=cp.stderr,
        hard_failed=cp.returncode != 0,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--fail-on-ready-with-warnings",
        action="store_true",
        help="Treat readiness verdict ready_with_warnings as failure.",
    )
    args = ap.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]
    py = sys.executable

    steps: list[tuple[str, list[str]]] = [
        ("export_outreach_contacted_all", [py, str(repo_root / "scripts/qa/export_outreach_contacted_all.py")]),
        ("export_all_known_marketing_contacts", [py, str(repo_root / "scripts/qa/export_all_known_marketing_contacts.py")]),
        ("export_do_not_repeat_master", [py, str(repo_root / "scripts/qa/export_do_not_repeat_master.py")]),
        ("validate_contacted_csv_coverage_strict", [py, str(repo_root / "scripts/qa/validate_contacted_csv_coverage.py"), "--strict"]),
        ("check_reports_out_active_hygiene", [py, str(repo_root / "scripts/qa/check_reports_out_active_hygiene.py")]),
        ("check_outbound_readiness", [py, str(repo_root / "scripts/qa/check_outbound_readiness.py")]),
    ]

    print("=== refresh_outbound_safety_memory ===")
    print(f"Working directory: {repo_root}")

    results: list[StepResult] = []
    for idx, (name, cmd) in enumerate(steps, start=1):
        print(f"[{idx}/{len(steps)}] {name}")
        res = _run_step(name, cmd)
        if name == "check_outbound_readiness" and res.returncode == 0:
            verdict = _extract_readiness_verdict(res.stdout)
            if verdict == "ready_with_warnings":
                if args.fail_on_ready_with_warnings:
                    res.hard_failed = True
                    res.note = "fail_on_ready_with_warnings enabled"
                else:
                    res.note = "warnings accepted by default"
        results.append(res)
        status = "OK" if not res.hard_failed else "FAIL"
        print(f"  -> {status} (rc={res.returncode}, {res.elapsed_s:.2f}s)")
        if res.note:
            print(f"  -> note: {res.note}")
        if res.hard_failed:
            print("\n--- step stdout ---")
            if res.stdout.strip():
                print(res.stdout.rstrip())
            print("--- step stderr ---")
            if res.stderr.strip():
                print(res.stderr.rstrip())
            print("\nStopped on first hard failure.")
            break

    print("\n=== Summary ===")
    for r in results:
        status = "OK" if not r.hard_failed else "FAIL"
        print(f"- {r.name}: {status} (rc={r.returncode}, {r.elapsed_s:.2f}s)")
    failed = any(r.hard_failed for r in results)
    if failed:
        return 1
    print("All outbound safety-memory refresh checks completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
