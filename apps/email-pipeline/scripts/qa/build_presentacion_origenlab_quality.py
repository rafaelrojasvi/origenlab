#!/usr/bin/env python3
"""Quality pass for Presentación OrigenLab review lists (read-only, no sends).

Requires prior build:
  uv run python scripts/qa/build_presentacion_origenlab_review.py

Outputs:
  presentacion_batch1_send_now_25.csv
  presentacion_batch2_followup_old_25.csv
  presentacion_hold_active_personalized.csv
  presentacion_same_domain_review_curated.csv
  presentacion_do_not_send_reasons.csv
  presentacion_batch1_messages.md
  presentacion_followup_messages.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.campaigns.presentacion_origenlab_quality import (
    run_presentacion_quality_pass,
    write_presentacion_quality_outputs,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=_ROOT / "reports" / "out" / "active" / "current",
        help="Directory with presentacion_origenlab_* inputs",
    )
    args = ap.parse_args(argv)

    out_dir = args.out_dir.resolve()
    if not (out_dir / "presentacion_origenlab_send_now_review.csv").is_file():
        print(
            f"Missing input: {out_dir / 'presentacion_origenlab_send_now_review.csv'}",
            file=sys.stderr,
        )
        print("Run build_presentacion_origenlab_review.py first.", file=sys.stderr)
        return 1

    result = run_presentacion_quality_pass(out_dir)
    paths = write_presentacion_quality_outputs(result, out_dir)
    s = result.summary

    print("Presentación OrigenLab quality pass (read-only) — no sends")
    print(f"  In:  {s.get('input_send_now_count')} send-now raw")
    print(f"  Batch 1 (presentación): {s.get('batch1_count')}")
    print(f"  Batch 2 (follow-up):    {s.get('batch2_count')}")
    print(f"  Hold personalizado:     {s.get('hold_personalized_count')}")
    print(f"  Same-domain curated:    {s.get('same_domain_curated_count')}")
    print(f"  Do-not-send reasons:    {s.get('do_not_send_count')}")
    print(f"  Dominios dedupe (sec.): {s.get('domains_duplicate_secondaries_removed')}")
    print(f"  Out: {paths['batch1']}")
    print("  Top batch 1:")
    for i, item in enumerate(s.get("top_batch1") or [], start=1):
        print(f"    {i}. {item['email']} — {item['org']} ({item['score']:.1f})")
    print("  Top batch 2:")
    for i, item in enumerate(s.get("top_batch2") or [], start=1):
        print(f"    {i}. {item['email']} — {item['org']} ({item['score']:.1f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
