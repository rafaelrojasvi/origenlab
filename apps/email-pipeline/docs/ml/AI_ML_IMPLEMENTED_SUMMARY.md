# AI / ML — implemented summary & how to talk about it

Status: canonical (implementation + labeling guidance; backlog clearly marked)  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-24

## Three layers (label outputs like this for clients / ChatGPT)

| Layer | Meaning | Examples in this repo |
|-------|---------|----------------------|
| **Exact** | Counts tied to well-defined rows or dates | Total messages, rows with body, **by-year histogram** (GROUP BY `date_iso` year) |
| **Heuristic** | Rule-based signal, not ground truth | Keyword hits (`cotiz`, `proveedor`, NDR-like), domain tables, cotización∧equipo crosses |
| **Exploratory ML** | Sample-only, not operational truth | Embeddings + clusters (MiniLM + K-Means / Agglomerative / optional HDBSCAN) |

**Rule of thumb:** never sell clusters or keyword % as “exact business facts.” SQL year totals ≈ exact for that archive; “15% cotización” = heuristic mention rate; clusters = themes on a **sample**.

---

## What the pipeline does (non-AI)

- **PST → mbox → SQLite → JSONL** (no ML).
- **Deterministic + heuristic report** on full archive: SQL `LIKE`, domains (incl. operational / external), crosses, years.
- **No LLM** in the default import/report path.

---

## Implemented today (code in repo)

1. **Embeddings:** `all-MiniLM-L6-v2` → `explore_email_clusters.py`, `generate_client_report.py`, `email_ml_explore.py`.
2. **Clustering:** Agglomerative, K-Means in those scripts; **HDBSCAN** is an **optional** path where the code uses it — package `hdbscan` is in the **`ml`** dependency group in [`pyproject.toml`](../../pyproject.toml) (`uv sync --group ml`).
3. **Equipment models (heuristic):** regex catalog in `email_ml_explore.py`.

## Optional / not in default pipeline

- **LLM:** [Appendix: business signal prompt](#appendix-business-signal-llm-prompt) — for manual/API use on slices; **no** LLM in default ingest → report path.

---

## What is *not* implemented

Supervised classifier (needs labels), full LLM batch, RAG, NER — see unsupervised/supervised tables below.

---

## Example numbers (one historical corpus snapshot only — not repo truth)

The bullets below were **one** run on **one** archive; your DB will differ. Do **not** cite them as current project metrics—recompute from SQLite/reports for the archive you are holding.

- Illustrative only: ~130k messages; ~117k with body; ~18k NDR-heuristic; ~15.5% / ~12.8% / ~3.8% style breakdowns from that snapshot.
- Generalizations that stay true: full-corpus reporting is **SQL + heuristics**; clusters are **sample-only**; client report = mentions & network, not ERP sales.

---

## Backlog / next steps (not implemented as product requirements)

1. **Stratified sampling in workflows** — `explore_email_clusters.py` already has `--sample-mode` / `--year`; backlog is wider adoption in default report flows and clearer product defaults, not inventing the flag.
2. **LLM on slices** — high-value filter → chunks + prompt in appendix below (not whole archive).
3. **Small supervised model** — after **200–500 labels** (quote vs noise, etc.), linear or boosting on **same embeddings**.

**Do not rush:** full RAG, BERTopic, fancy NER — unless product clearly needs them.

---

## External review (why this architecture is sound)

* **Separated** deterministic reporting from exploratory ML — avoids slow, expensive, fragile “AI everywhere.”
* **ML where it fits** — discovery / themes on samples; not replacing exact counts.
* **Honest “not implemented”** — builds trust with clients.
* **Regex / model catalog** — often *more* business-useful than abstract topics for lab equipment.

**Verdict:** keep the layered stack; don’t collapse into a single “AI pipeline.”

---

## Commands

```bash
# Clusters on business-like rows only (heuristic slice)
uv run python scripts/ml/explore_email_clusters.py --limit 2000 --sample-mode cotiz --n-clusters 12

# No bounces in sample (cleaner themes)
uv run python scripts/ml/explore_email_clusters.py --limit 2000 --sample-mode no_bounce

uv run python scripts/ml/email_ml_explore.py --limit 5000 --out reports/out/ml.json
```

*Paths:* [`generate_client_report.py`](../../scripts/reports/generate_client_report.py), [`explore_email_clusters.py`](../../scripts/ml/explore_email_clusters.py), [`email_ml_explore.py`](../../scripts/ml/email_ml_explore.py), this doc (prompt appendix), [`REPORT_SCOPE_CLIENT.md`](../REPORT_SCOPE_CLIENT.md).

---

## ML technique options (reference)

Condensed from the former `ML_EMAIL_OPTIONS.md`.

### Unsupervised (fits without labels)

| Técnica | Qué hace | En este repo |
|--------|----------|--------------|
| **Embeddings + clustering** | Agrupa por tema semántico | `explore_email_clusters.py`, `generate_client_report.py` (MiniLM + agglomerative / k-means) |
| **K-Means** | Particiones esféricas; hay que elegir *k* | `email_ml_explore.py` |
| **Clustering jerárquico** | Árbol de fusión | Ya usado (cosine + average linkage) |
| **HDBSCAN** | Por densidad; ruido como `-1` | Opcional en código; dependencia declarada en [`pyproject.toml`](../../pyproject.toml) |
| **LDA / BERTopic** | Temas por palabras o embeddings | Posible; más pesado o sensible a ruido HTML |

### Supervised (requiere etiquetas)

| Técnica | Necesitas | Uso típico |
|--------|-----------|------------|
| **Clasificador** | Cientos/miles de mails etiquetados | Priorizar bandeja |
| **Detección de modelo** | Regex/catálogo o NER | Extraer modelos de equipo en texto |

Sin etiquetas reales, el supervisado se reduce a **pseudo-etiquetas** (keywords) → sesgo fuerte; solo experimento.

### Modelos de equipo en texto

1. **Catálogo + regex** — `email_ml_explore.py` bloque `EQUIPMENT_MODEL_PATTERNS`.
2. Ampliar catálogo desde fichas/PDFs.
3. **NER / LLM** — más flexible; ver [apéndice de prompt](#appendix-business-signal-llm-prompt).

### Comando rápido

```bash
uv sync --group ml
uv run python scripts/ml/email_ml_explore.py --limit 4000 --kmeans 16
```

La GPU acelera embeddings; clustering (sklearn) es CPU.

---

## Appendix: business signal LLM prompt

Use as **system instruction** or **first user message** when analyzing archived email text or chunks for **OrigenLab (Chile)**: B2B supplier of laboratory equipment, reagents, and related services. The company cares about **real operational and commercial signal**—not inbox noise.

### TASK

From the email text (or chunks) you are given, **extract and summarize ONLY** what is materially useful for understanding how the business runs and communicates. **Do not invent facts**; only use what appears in the text.

### KEEP / PRIORITIZE (important)

- Human business dialogue: quotes (**cotizaciones**), orders, deliveries, delays, technical questions about products, payment or invoice mentions, follow-ups after a quote.
- Named roles or companies when stated (client, supplier, carrier, lab).
- Concrete details: product names, brands, quantities, deadlines, Incoterms, attachments mentioned (“adjunto”), meeting or call arrangements tied to a deal.
- Complaints, returns, or service issues that affect customers or suppliers.
- Anything that changes obligations or next steps (“confirmamos”, “anexo”, “plazo”, “stock”).

### IGNORE / DROP (not important for this scope)

- Bounces, undeliverable mail, MAILER-DAEMON, postmaster.
- Out-of-office and auto-replies.
- Newsletters, promos, unsubscribe footers, generic marketing.
- Password resets, 2FA, login alerts, social notifications.
- Long repeated legal disclaimers and email signatures (summarize as “standard signature” if needed).
- Full quoted threads: prefer the **newest** reply; do not re-copy old quoted blocks unless they add new facts.

### OUTPUT FORMAT (unless the user asks otherwise)

1. **One short paragraph:** what this thread/message is about.
2. **Bullet list:** facts that matter (who, what, when, amounts/products if present).
3. **Optional:** “Open questions / risks” **only** if clearly stated in the text.
4. If the message is purely noise for this scope, respond with: **`NO_BUSINESS_SIGNAL`** — one line why.

### LANGUAGE

Match the language of the source (Spanish/English). Do not translate unless asked.

### PRIVACY

Do not echo full personal data unless needed for the summary; prefer roles (“cliente”, “proveedor”) when the name is not essential to the insight.

### Usage

- **Batch / RAG:** prepend this block to each chunk (or use as system prompt) before asking for a summary.
- **SQLite / JSONL:** pass `subject` + `sender` + `recipients` + truncated `body` (newest segment first if you split by quoted block).

*Former standalone file:* prompt lived in `EMAIL_BUSINESS_SIGNAL_PROMPT.md`; canonical text is this appendix.
