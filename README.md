# OrigenLab

<p align="center">
  Commercial engineering monorepo for OrigenLab — four apps:
  <br /><br />
  public website (Astro) · email pipeline (Python/SQLite) · operator API (FastAPI) · operator dashboard (React)
</p>

<p align="center">
  <img alt="Astro" src="https://img.shields.io/badge/Astro-5.x-ff5d01?logo=astro&logoColor=white" />
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" />
  <img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-App-FF4B4B?logo=streamlit&logoColor=white" />
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg" />
</p>

## Overview

Four applications share this monorepo:

| App | Role |
|-----|------|
| **`apps/web`** | Public marketing site (Astro) |
| **`apps/email-pipeline`** | Gmail ingest, SQLite operational truth, outbound safety, reports, mutation scripts |
| **`apps/api`** | Read-only operator HTTP API on **:8001** (Today routes + `GET /mirror/*` Postgres reporting) |
| **`apps/dashboard`** | Read-only operator UI on **:5173** (**Today** page → `apps/api` only) |

**Architecture (canonical):** [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) — do not duplicate full topology here.

**Operator dashboard + API:** [`apps/api/README.md`](apps/api/README.md) · [`apps/dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md`](apps/dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md)

Send/outreach truth stays in **SQLite + email-pipeline scripts**, not in Postgres mirror or dashboard reads.

## Scope and limitations

- Drafting/copilot flows generate suggestions only; there is no autonomous send path.
- Sensitive operational datasets are intentionally kept outside Git.
- Public business claims follow canonical docs and site data.

## Monorepo apps

| App | Path | Stack |
|-----|------|-------|
| Website | [`apps/web/`](apps/web/) | Astro 5, Tailwind 4, TypeScript, Node 20 |
| Email pipeline | [`apps/email-pipeline/`](apps/email-pipeline/) | Python 3.12, `uv`, SQLite, Streamlit, optional CUDA ML (**no FastAPI**) |
| Operator API | [`apps/api/`](apps/api/) | FastAPI :8001 — operator routes + `GET /mirror/*` Postgres reporting |
| Dashboard | [`apps/dashboard/`](apps/dashboard/) | React + Vite — read-only operator **Today** UI |

## Quick demo

```bash
cd apps/web
npm ci
npm run build
npm run preview
```

```bash
cd apps/email-pipeline
uv sync --group ui
uv run --group ui streamlit run apps/business_mart_app.py
```

Open `http://localhost:4321` for web preview and `http://localhost:8501` for Streamlit.

## Public release checklist

- Use [`docs/PUBLIC_RELEASE_CHECKLIST.md`](docs/PUBLIC_RELEASE_CHECKLIST.md) before switching repo visibility.
- Never commit secrets or operational datasets.

## Security and data handling

- Never commit `.env`, API keys, OAuth tokens, or mailbox credentials.
- Keep operational artifacts (PST/mbox/SQLite/JSONL/reports) outside Git by default.
- Use [`apps/email-pipeline/.env.example`](apps/email-pipeline/.env.example) as the template.
- Follow coordinated disclosure in [`SECURITY.md`](SECURITY.md).

Pipeline-specific handling is documented at [`apps/email-pipeline/docs/SECURITY.md`](apps/email-pipeline/docs/SECURITY.md).

## Documentation

- Monorepo architecture: [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md)
- Documentation map: [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md)
- Web app: [`apps/web/docs/README.md`](apps/web/docs/README.md)
- Email pipeline: [`apps/email-pipeline/docs/README.md`](apps/email-pipeline/docs/README.md)
- Operator API: [`apps/api/README.md`](apps/api/README.md)
- Dashboard (freeze handoff): [`apps/dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md`](apps/dashboard/docs/V1_FREEZE_OPERATOR_HANDOFF.md)
- Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security policy: [`SECURITY.md`](SECURITY.md)

## License

MIT — see [`LICENSE`](LICENSE).
