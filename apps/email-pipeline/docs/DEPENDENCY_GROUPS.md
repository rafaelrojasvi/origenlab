# Dependency groups

Status: canonical install guide  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-06-03

## Purpose

Explain which `uv sync` dependency groups are needed for each workflow.

Default **`uv sync`** is intentionally small and supports **daily SQLite / document / operator tooling**. Optional groups install heavier or external-service-specific dependencies (OpenAI, Torch, Streamlit, Postgres drivers, Google OAuth).

**Phase 8F context:** OpenAI moved to **`lab`** (8F-1); HDBSCAN moved to **`ml`** (8F-2). This document is the canonical matrix after those changes.

---

## Quick commands

| Workflow | Command |
|----------|---------|
| Daily operator / SQLite / document tooling | `uv sync` |
| Gmail ingest / Workspace OAuth | `uv sync --group gmail` or `uv sync --group workspace` |
| Tatiana / research / OpenAI-backed lab tools | `uv sync --group lab` |
| ML / embeddings / HDBSCAN / FAISS / Torch | `uv sync --group ml` |
| Streamlit legacy UI | `uv sync --group ui` |
| Postgres mirror / Alembic / verifiers | `uv sync --group postgres` |
| Full CI-style local test install | `uv sync --group dev --group ui --group postgres --group lab --frozen` |
| Full local kitchen-sink install (only when needed) | `uv sync --group dev --group ui --group postgres --group lab --group gmail --group ml` |

---

## Default dependencies

Packages in **`[project.dependencies]`** (no extra `--group` flags):

| Package | Role |
|---------|------|
| `orjson` | Fast JSON |
| `pydantic` / `pydantic-settings` | Settings and validation |
| `python-dotenv` | `.env` loading |
| `tqdm` | Progress bars |
| `pymupdf` | PDF attachment/text extraction |
| `python-docx` | Word documents |
| `openpyxl` | Excel spreadsheets |

**Not included in default sync:**

- **OpenAI** → `lab`
- **HDBSCAN** → `ml`
- **Torch** / sentence-transformers / FAISS → `ml`
- **Streamlit** / pandas (UI stack) → `ui`
- **Postgres** driver / Alembic → `postgres`
- **Google OAuth** (Gmail IMAP) → `gmail` / `workspace`

Daily operator commands such as `uv run origenlab status`, `refresh-safety`, and **plan-only** `uv run origenlab refresh-dashboard` work after default sync (subprocess scripts may still need their own groups at runtime — e.g. Gmail ingest needs `gmail`).

---

## Groups

### `lab`

| | |
|---|---|
| **Purpose** | Tatiana copilot, research automation, and other OpenAI-backed lab tooling |
| **Main packages** | `openai` |
| **Example** | `uv sync --group lab` · `uv run python scripts/tatiana/run_tatiana_pilot_batch.py --help` |
| **Daily operator?** | **No** — not required for outbound lanes or `origenlab` daily subcommands |

See also: [`TATIANA_LAB_BOUNDARY.md`](TATIANA_LAB_BOUNDARY.md).

### `ml`

| | |
|---|---|
| **Purpose** | Embeddings, clustering, exploratory ML scripts under `scripts/ml/` |
| **Main packages** | `torch`, `torchvision`, `torchaudio`, `sentence-transformers`, `faiss-cpu`, `scikit-learn`, `numpy`, **`hdbscan`**, `pandas` (pinned subset) |
| **Example** | `uv sync --group ml` · `uv run python scripts/ml/explore_email_clusters.py --help` |
| **Daily operator?** | **No** |

**Note:** `ml` uses the explicit PyTorch **CUDA** index (`pytorch-cu129`) in `pyproject.toml`. Avoid raw `pip install -U torch` without that index — see [`README.md`](../README.md#ml-environment-setup-wsl-project-local-venv-only).

### `gmail`

| | |
|---|---|
| **Purpose** | Google Workspace Gmail IMAP ingest and OAuth helpers |
| **Main packages** | `google-auth`, `google-auth-oauthlib` |
| **Example** | `uv sync --group gmail` · `uv run origenlab gmail-ingest-help` |
| **Daily operator?** | **Only if** you run Gmail ingest (`gmail-ingest` or `scripts/ingest/05_workspace_gmail_imap_to_sqlite.py`) on this machine |

### `workspace`

| | |
|---|---|
| **Purpose** | **Back-compat alias** for `gmail` — same packages |
| **Example** | `uv sync --group workspace` |
| **Daily operator?** | Same as `gmail` |

### `postgres`

| | |
|---|---|
| **Purpose** | Postgres mirror lane: Alembic migrations, psycopg drivers, verify scripts |
| **Main packages** | `alembic`, `sqlalchemy`, `psycopg[binary]` |
| **Example** | `uv sync --group postgres` · `uv run alembic -c alembic.ini history` |
| **Daily operator?** | **No** — SQLite remains operational truth; mirror is **parked** |

See: [`EXPERIMENTAL_PARKED.md`](EXPERIMENTAL_PARKED.md).

### `api`

| | |
|---|---|
| **Purpose** | Legacy FastAPI/uvicorn stack declared inside email-pipeline (historical read API slice) |
| **Main packages** | `fastapi`, `uvicorn[standard]` |
| **Example** | `uv sync --group postgres --group api` (bootstrap notes in RUNBOOK) |
| **Daily operator?** | **No** — active operator HTTP API is **`apps/api`** on port **8001** |

### `ui`

| | |
|---|---|
| **Purpose** | Legacy **Streamlit** app (`apps/business_mart_app.py`) — not the primary React dashboard |
| **Main packages** | `streamlit`, `pandas`, `xlrd` |
| **Example** | `uv sync --group ui` · `uv run --group ui streamlit run apps/business_mart_app.py` |
| **Daily operator?** | **No** — optional review UI; primary operator UI is `apps/dashboard` |

### `dev`

| | |
|---|---|
| **Purpose** | Local development and **pytest** |
| **Main packages** | `pytest` + **`{ include-group = "postgres" }`** |
| **Example** | `uv sync --group dev` |
| **Daily operator?** | **No** (test tooling) |

**Note:** Because `dev` **includes** `postgres`, `uv sync --group dev` already pulls Alembic/psycopg. CI still passes **`--group postgres`** explicitly for clarity alongside `dev`.

---

## Safety

Installing a dependency group **does not** approve running mutating commands in that lane.

| Lane | Still requires explicit operator intent |
|------|----------------------------------------|
| Gmail ingest | OAuth + network; writes SQLite |
| Postgres mirror / migrate | `--apply`, `--replace`, Alembic upgrade |
| Send / purge | Break-glass scripts |
| Broad NDR apply | Documented apply paths only |

**Daily plan-only check (safe after default sync):**

```bash
uv run origenlab refresh-dashboard
```

This prints the workflow plan only — no Gmail ingest, mart rebuild, or Postgres writes unless you pass **`--apply`** separately and deliberately.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: google` | `uv sync --group gmail` |
| `ModuleNotFoundError: openai` | `uv sync --group lab` |
| `ModuleNotFoundError: hdbscan` | `uv sync --group ml` |
| Streamlit import fails | `uv sync --group ui` |
| `psycopg` / `alembic` import fails | `uv sync --group postgres` (or `--group dev`, which includes postgres) |

After adding groups, re-run your command with `uv run …` so the project venv is used.

---

## Related docs

- [`README.md`](../README.md) — clone setup, ML CUDA notes
- [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) — what git can and cannot reproduce
- [`TATIANA_LAB_BOUNDARY.md`](TATIANA_LAB_BOUNDARY.md) — lab vs daily outbound
- [`OPERATOR_COMMAND_SURFACE.md`](OPERATOR_COMMAND_SURFACE.md) — `origenlab` subcommands
- [`EXPERIMENTAL_PARKED.md`](EXPERIMENTAL_PARKED.md) — Postgres / API / Tatiana parked index
- [`audits/PHASE8F_BACKEND_REDUCTION_AUDIT_20260603.md`](audits/PHASE8F_BACKEND_REDUCTION_AUDIT_20260603.md) — 8F reduction audit
