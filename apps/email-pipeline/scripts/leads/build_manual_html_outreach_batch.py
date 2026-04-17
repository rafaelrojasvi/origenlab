#!/usr/bin/env python3
"""Package a manually reviewed recipient CSV + one shared HTML body for operator sending.

Does not send mail, touch the DB, or personalize HTML. See RUNBOOK § Manual HTML outreach batch.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.manual_html_outreach_batch import (
    DEFAULT_SUBJECT,
    MANIFEST_JSON_NAME,
    run_manual_html_outreach_batch,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True, help="Recipient CSV (e.g. archive manual shortlist).")
    ap.add_argument("--html", type=Path, required=True, help="Shared HTML email body file path.")
    ap.add_argument("--subject", type=str, default=DEFAULT_SUBJECT, help=f"Email subject (default: {DEFAULT_SUBJECT!r}).")
    ap.add_argument("--out-dir", type=Path, required=True, help="Output directory for batch artifacts.")
    ap.add_argument("--limit", type=int, default=None, help="Max recipients after dedupe (optional).")
    ap.add_argument(
        "--batch-name",
        type=str,
        default=None,
        help="Logical batch name (default: input stem + UTC timestamp).",
    )
    ap.add_argument(
        "--no-copy-html",
        action="store_true",
        help="Do not copy HTML into out-dir as shared_email.html.",
    )
    ap.add_argument(
        "--no-preview-md",
        action="store_true",
        help="Do not write manual_html_outreach_preview.md.",
    )
    args = ap.parse_args()

    try:
        manifest = run_manual_html_outreach_batch(
            input_csv=args.input,
            html_path=args.html,
            subject=str(args.subject),
            out_dir=args.out_dir,
            limit=args.limit,
            batch_name=args.batch_name,
            copy_shared_html=not args.no_copy_html,
            write_preview_md=not args.no_preview_md,
        )
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2

    out = Path(args.out_dir).resolve()
    print(f"Wrote manual HTML outreach batch to {out}")
    print(f"Manifest: {out / MANIFEST_JSON_NAME}")
    print(f"Recipients: {manifest['counts']['recipients_written']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
