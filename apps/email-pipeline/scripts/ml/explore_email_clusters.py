#!/usr/bin/env python3
"""
Explore archived email text with embeddings + hierarchical (agglomerative) clusters.

Useful to see:
  - Whether clusters separate cotizaciones / proveedores / logistics / noise
  - How dense or mixed the business signal is in a sample

Requires ML env: uv sync --group ml
  uv run python scripts/ml/explore_email_clusters.py --limit 500 --n-clusters 10

Stratified samples (--sample-mode): cotiz, no_bounce, universidad, business, random.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings

# Spanish + English tokens aligned with AI_ML_IMPLEMENTED_SUMMARY.md (business-signal prompt appendix)
DEFAULT_TRACK = [
    ("cotiz", "cotización / quote"),
    ("proveedor", "proveedor"),
    ("pedido", "pedido / order"),
    ("oc ", "OC / purchase order"),
    ("factura", "factura / invoice"),
    ("envío", "envío / shipping"),
    ("entrega", "entrega / delivery"),
    ("stock", "stock"),
    ("adjunto", "adjunto / attachment"),
    ("invoice", "invoice (EN)"),
    ("quote", "quote (EN)"),
    ("delivery", "delivery (EN)"),
]

NOISE_HINTS = [
    "mailer-daemon",
    "postmaster",
    "undeliverable",
    "out of office",
    "fuera de la oficina",
    "automatic reply",
    "respuesta automática",
    "newsletter",
    "unsubscribe",
    "no-reply",
    "noreply",
]


def norm(s: str) -> str:
    return (s or "").lower()


def row_text(subject: str, sender: str, body: str, max_body: int) -> str:
    b = (body or "").strip()
    if len(b) > max_body:
        b = b[: max_body - 3] + "..."
    return f"Subject: {subject or '(no subject)'}\nFrom: {sender or ''}\n{b}"


def trunc_one_line(s: str, n: int = 100) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s if len(s) <= n else s[: n - 3] + "..."


def main() -> None:
    ap = argparse.ArgumentParser(description="Email embeddings + agglomerative clusters + keyword stats")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: ORIGENLAB_SQLITE_PATH)")
    ap.add_argument("--limit", type=int, default=800, help="Max emails to load (random sample after filter)")
    ap.add_argument("--min-body-len", type=int, default=40, help="Skip very short bodies")
    ap.add_argument("--max-body-chars", type=int, default=800, help="Body chars combined into embedding text")
    ap.add_argument("--n-clusters", type=int, default=12, help="Agglomerative cluster count")
    ap.add_argument(
        "--filter-any",
        action="store_true",
        help="Same as --sample-mode business",
    )
    ap.add_argument(
        "--sample-mode",
        choices=("random", "business", "cotiz", "no_bounce", "universidad"),
        default=None,
        help="Stratify sample: cotiz=mention cotiz; no_bounce=exclude Mailer-Daemon/postmaster; "
        "universidad=edu-ish OR; business=any business keyword; random=unfiltered random",
    )
    ap.add_argument("--year", type=str, default=None, help="Only substr(date_iso,1,4)=YEAR")
    ap.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="SentenceTransformer model id",
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Also write clusters.json + report snippet into this folder (e.g. client report run)",
    )
    args = ap.parse_args()

    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
        from sklearn.cluster import AgglomerativeClustering
    except ImportError as e:
        print("Missing deps. Run: uv sync --group ml", file=sys.stderr)
        raise SystemExit(1) from e

    db_path = args.db or load_settings().resolved_sqlite_path()
    if not db_path.is_file():
        print("DB not found:", db_path, file=sys.stderr)
        print("Build: uv run python scripts/ingest/02_mbox_to_sqlite.py", file=sys.stderr)
        raise SystemExit(1)

    mode = args.sample_mode or ("business" if args.filter_any else "random")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    min_len = args.min_body_len
    blob = "(COALESCE(subject,'') || ' ' || COALESCE(body,''))"
    snd = "LOWER(COALESCE(sender,''))"
    wheres = ["length(trim(coalesce(body,''))) >= ?"]
    params: list = [min_len]

    if args.year and len(args.year) == 4:
        wheres.append("substr(date_iso,1,4) = ?")
        params.append(args.year)

    if mode == "cotiz":
        wheres.append(f"{blob} LIKE ?")
        params.append("%cotiz%")
    elif mode == "no_bounce":
        wheres.append(f"{snd} NOT LIKE '%mailer-daemon%'")
        wheres.append(f"{snd} NOT LIKE '%postmaster%'")
        wheres.append("LOWER(COALESCE(subject,'')) NOT LIKE '%delivery status%'")
    elif mode == "universidad":
        u = [
            "%universidad%",
            "%uchile%",
            "%uc.cl%",
            "%puc.cl%",
            "%utfsm%",
            "%udec%",
            "%.edu.%",
        ]
        wheres.append("(" + " OR ".join(f"{blob} LIKE ?" for _ in u) + ")")
        params.extend(u)
    elif mode == "business":
        likes = [
            "%cotiz%",
            "%proveedor%",
            "%pedido%",
            "%factura%",
            "%envio%",
            "%entrega%",
            "%stock%",
            "%adjunto%",
            "%OC %",
        ]
        wheres.append("(" + " OR ".join(f"{blob} LIKE ?" for _ in likes) + ")")
        params.extend(likes)

    sql = f"""
        SELECT id, subject, sender, date_iso, body FROM emails
        WHERE {" AND ".join(wheres)}
        ORDER BY RANDOM() LIMIT ?
    """
    params.append(args.limit)
    cur = conn.execute(sql, tuple(params))
    rows = [
        {
            "id": r["id"],
            "subject": r["subject"] or "",
            "sender": r["sender"] or "",
            "date_iso": r["date_iso"] or "",
            "body": r["body"] or "",
            "text": row_text(
                r["subject"] or "",
                r["sender"] or "",
                r["body"] or "",
                args.max_body_chars,
            ),
        }
        for r in cur
    ]
    conn.close()

    if len(rows) < 10:
        print("Too few rows after filter. Try --sample-mode random or lower --min-body-len.")
        raise SystemExit(1)

    print("=== explore_email_clusters ===")
    print("db:", db_path)
    print("loaded:", len(rows), "| sample_mode:", mode, "| year:", args.year or "-", "| min_body:", args.min_body_len)
    print("model:", args.model)

    # Global keyword / noise stats on this sample
    print("\n--- Keyword hit rate in sample (subject + body) ---")
    for key, label in DEFAULT_TRACK:
        c = sum(1 for r in rows if key.lower() in norm(r["subject"] + " " + r["body"]))
        print(f"  {label:28} {c:5}  ({100 * c / len(rows):.1f}%)")
    noise_n = sum(
        1
        for r in rows
        if any(h in norm(r["subject"] + " " + r["body"][:2000]) for h in NOISE_HINTS)
    )
    print(f"  {'possible noise (heuristic)':28} {noise_n:5}  ({100 * noise_n / len(rows):.1f}%)")

    device = "cuda"
    try:
        import torch

        if not torch.cuda.is_available():
            device = "cpu"
    except Exception:
        device = "cpu"
    print("\nembedding device:", device)
    model = SentenceTransformer(args.model, device=device)
    texts = [r["text"] for r in rows]
    emb = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    n_clusters = min(args.n_clusters, len(rows) // 2)
    n_clusters = max(2, n_clusters)
    clust = AgglomerativeClustering(n_clusters=n_clusters, metric="cosine", linkage="average")
    labels = clust.fit_predict(emb)

    print("\n--- Clusters (agglomerative, cosine average linkage) ---")
    by_c: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        by_c.setdefault(int(lab), []).append(i)

    for lab in sorted(by_c.keys(), key=lambda k: -len(by_c[k])):
        idxs = by_c[lab]
        cluster_rows = [rows[i] for i in idxs]
        print(f"\n### Cluster {lab}  (n={len(idxs)})")
        # Keyword density in cluster
        for key, name in DEFAULT_TRACK[:6]:
            cc = sum(1 for r in cluster_rows if key.lower() in norm(r["subject"] + " " + r["body"]))
            if cc:
                print(f"    {name}: {cc} ({100 * cc / len(idxs):.0f}%)")
        print("    sample subjects:")
        for r in cluster_rows[:8]:
            print("     -", trunc_one_line(r["subject"] or "(no subject)", 90))
        # One body snippet from med-long body
        best = max(cluster_rows, key=lambda r: len(r["body"] or ""))
        print("    snippet:", trunc_one_line((best["body"] or "")[:400], 220))

    if args.report_dir:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        clusters_payload = {
            "model": args.model,
            "n_sample": len(rows),
            "n_clusters": n_clusters,
            "sample_mode": mode,
            "year": args.year,
            "clusters": {},
        }
        for lab in sorted(by_c.keys(), key=lambda k: -len(by_c[k])):
            idxs = by_c[lab]
            cluster_rows = [rows[i] for i in idxs]
            clusters_payload["clusters"][str(lab)] = [
                {
                    "subject": trunc_one_line(r["subject"] or "(no subject)", 120),
                    "sender": trunc_one_line(r["sender"], 80),
                }
                for r in cluster_rows[:25]
            ]
        try:
            import orjson

            p = args.report_dir / "explore_clusters.json"
            p.write_bytes(orjson.dumps(clusters_payload, option=orjson.OPT_INDENT_2))
            print("\nWrote:", p)
        except ImportError:
            import json

            p = args.report_dir / "explore_clusters.json"
            p.write_text(json.dumps(clusters_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            print("\nWrote:", p)


if __name__ == "__main__":
    main()
