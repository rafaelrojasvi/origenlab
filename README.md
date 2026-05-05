# OrigenLab

Commercial engineering monorepo for OrigenLab with two core products:

- a public marketing website built with Astro
- an email intelligence and outreach operations pipeline built with Python

![Astro](https://img.shields.io/badge/Astro-5.x-ff5d01?logo=astro&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-App-FF4B4B?logo=streamlit&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

## Overview

This repository supports real commercial workflows:

- **Web experience (`apps/web`)** for trust, discovery, and quotation intake.
- **Email pipeline (`apps/email-pipeline`)** for archive ingestion, business signal extraction, reporting, and human-reviewed drafting assistance.

This project is portfolio-grade engineering work with clear operational constraints:

- local-first data processing for sensitive email archives
- explicit business-truth rules for commercial claims
- mandatory human review for assisted drafting and outreach outputs

## What I built

- Built and maintained a dual-app commercial monorepo: a static Astro website plus a Python email intelligence pipeline.
- Implemented ingestion and transformation workflows (PST/mbox/IMAP -> SQLite -> marts/reports) for operational analysis.
- Developed internal tooling with Streamlit for reviewing business signals, data freshness, and outreach operations.
- Built portfolio-grade commercial assets, including responsive catalog HTML and production-ready marketing email HTML.
- Enforced safety boundaries in outbound assistance flows with explicit human review and operational gating.

## Scope and limitations

This repository is used for real internal commercial operations, but it should be read as an engineering portfolio artifact as well.

- The drafting/copilot flows provide suggestions, not autonomous outbound sending.
- Some workflows depend on local/private operational datasets that are intentionally not tracked in git.
- Public docs and site data are the source of truth for business claims; generated artifacts are operational outputs.

## Architecture at a glance

```text
                 ┌──────────────────────────────┐
                 │        apps/web (Astro)      │
                 │  Marketing pages + quote UX  │
                 └───────────────┬──────────────┘
                                 │
                                 │ Business context / public content
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    apps/email-pipeline (Python)                     │
│                                                                      │
│  PST / mbox / IMAP                                                   │
│         │                                                            │
│         ▼                                                            │
│      Ingest scripts  ->  SQLite  ->  JSONL / marts / reports        │
│                                │             │                       │
│                                │             ├─ HTML + JSON reports  │
│                                │             └─ Streamlit internal UI│
│                                │                                     │
│                                └─ Drafting assist (human reviewed)   │
└──────────────────────────────────────────────────────────────────────┘
```

## Monorepo apps

| App | Path | Stack |
|-----|------|-------|
| Website | [`apps/web/`](apps/web/) | Astro 5, Tailwind 4, TypeScript, Node 20 |
| Email pipeline | [`apps/email-pipeline/`](apps/email-pipeline/) | Python 3.12, `uv`, SQLite, Streamlit, optional CUDA ML |

## Key capabilities

### Website (`apps/web`)

- Spanish-language B2B marketing site for lab equipment and solutions
- static architecture with predictable deploys
- reusable components, data-driven pages, and canonical content in `src/data/`
- deployment workflow and runbooks for production publishing

### Email pipeline (`apps/email-pipeline`)

- PST/mbox/IMAP ingestion into structured SQLite datasets
- business marts and operational reports (HTML + JSON outputs)
- Streamlit internal tooling for data freshness and outreach operations
- guarded commercial email drafting copilot (human-in-the-loop)
- outbound candidate gate with suppression and sent-history checks

## Quick start

### Website

```bash
cd apps/web
npm ci
npm run check
npm run build
```

### Email pipeline

```bash
cd apps/email-pipeline
uv sync --group dev --group ui
uv run pytest
```

Notes:

- `--group ui` is required for Streamlit-related tests.
- default `uv sync` installs base dependencies only.
- use `uv sync --group ml` when running embeddings/CUDA workflows.

## Quick demo

### Demo 1: Website build + preview

```bash
cd apps/web
npm ci
npm run build
npm run preview
```

Open `http://localhost:4321`.

### Demo 2: Streamlit business mart app

```bash
cd apps/email-pipeline
uv sync --group ui
uv run --group ui streamlit run apps/business_mart_app.py
```

Open `http://localhost:8501`.

### Demo 3: Marketing email + catalog assets

Open these files directly in a browser:

- `docs/origenlab-brochures/catalog-premium/origenlab_presentacion_comercial_email_combined.html`
- `docs/origenlab-brochures/catalog-premium/OrigenLab_Catalogo_Tecnico_Editorial_Imagenes_Premium.html`
- `docs/origenlab-brochures/catalog-premium/catalog-pdf.html`

## Portfolio assets (website, email, catalog, Streamlit)

Use these artifacts directly in case studies, screenshots, and demo pages.

### Website

- source pages: [`apps/web/src/pages/`](apps/web/src/pages/)
- layout shell: [`apps/web/src/layouts/Layout.astro`](apps/web/src/layouts/Layout.astro)
- build output (after `npm run build`): `apps/web/dist/`

### Streamlit app

- app entrypoint: [`apps/email-pipeline/apps/business_mart_app.py`](apps/email-pipeline/apps/business_mart_app.py)
- note: Streamlit is server-rendered at runtime, so portfolio artifacts are typically screenshots/video captures.

### Marketing email HTML

- commercial email template: [`docs/origenlab-brochures/catalog-premium/origenlab_presentacion_comercial_email_combined.html`](docs/origenlab-brochures/catalog-premium/origenlab_presentacion_comercial_email_combined.html)

### Catalog HTML/PDF + images

- web catalog (responsive): [`docs/origenlab-brochures/catalog-premium/OrigenLab_Catalogo_Tecnico_Editorial_Imagenes_Premium.html`](docs/origenlab-brochures/catalog-premium/OrigenLab_Catalogo_Tecnico_Editorial_Imagenes_Premium.html)
- PDF source HTML: [`docs/origenlab-brochures/catalog-premium/catalog-pdf.html`](docs/origenlab-brochures/catalog-premium/catalog-pdf.html)
- PDF export instructions: [`docs/origenlab-brochures/catalog-premium/CATALOG_DELIVERY.md`](docs/origenlab-brochures/catalog-premium/CATALOG_DELIVERY.md)
- image assets folder: `docs/origenlab-brochures/catalog-premium/catalog_assets_premium/`


## Public release checklist

Before switching this repository from private to public, run:

1. verify no secrets are tracked (`.env`, API keys, OAuth secrets, tokens, private keys)
2. verify no operational datasets are tracked (PST/mbox/SQLite/JSONL/client exports)
3. confirm generated reports are excluded except intentional placeholders
4. scan git history for accidental credentials and rotate if anything is found
5. ensure published screenshots/docs contain no private customer information

Reference checklist: [`docs/PUBLIC_RELEASE_CHECKLIST.md`](docs/PUBLIC_RELEASE_CHECKLIST.md)

## Repository layout

```text
.
├── apps/
│   ├── web/              # Astro marketing site
│   └── email-pipeline/   # ingestion, marts, reports, streamlit, outreach tooling
├── docs/                 # monorepo-level context, business rules, architecture map
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

## Security and data handling

- never commit `.env`, API keys, OAuth tokens, or mailbox credentials
- operational artifacts (PST/mbox/SQLite/JSONL/reports) stay outside git by default
- use [`apps/email-pipeline/.env.example`](apps/email-pipeline/.env.example) as the template
- follow coordinated disclosure in [`SECURITY.md`](SECURITY.md)

Pipeline-specific handling is documented at [`apps/email-pipeline/docs/SECURITY.md`](apps/email-pipeline/docs/SECURITY.md).

## Documentation

- Monorepo context: [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md#m-proj-start)
- Documentation map: [`docs/DOCUMENTATION_MAP.md`](docs/DOCUMENTATION_MAP.md#m-docmap-entry)
- Commercial truth rules: [`docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md`](docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md)
- Web docs: [`apps/web/docs/README.md`](apps/web/docs/README.md)
- Email pipeline docs: [`apps/email-pipeline/docs/README.md`](apps/email-pipeline/docs/README.md)
- Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)

## CI

GitHub Actions are path-filtered under [`.github/workflows/`](.github/workflows/):

- web changes trigger website checks/builds
- email-pipeline changes trigger Python test workflows

## License

MIT — see [`LICENSE`](LICENSE).
