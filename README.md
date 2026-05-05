# OrigenLab

<p align="center">
  Commercial engineering monorepo for OrigenLab with two core products:
  <br /><br />
  a public marketing website built with Astro
  <br />
  an email intelligence and outreach operations pipeline built with Python
</p>

<p align="center">
  <img alt="Astro" src="https://img.shields.io/badge/Astro-5.x-ff5d01?logo=astro&logoColor=white" />
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" />
  <img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-App-FF4B4B?logo=streamlit&logoColor=white" />
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg" />
</p>

## Overview

This repository contains two production-oriented workstreams:

- **Website (`apps/web`)**: Astro-based marketing site for quotation and product discovery.
- **Email pipeline (`apps/email-pipeline`)**: Python workflows for ingestion, reporting, and human-reviewed outreach assistance.

## Scope and limitations

- Drafting/copilot flows generate suggestions only; there is no autonomous send path.
- Sensitive operational datasets are intentionally kept outside Git.
- Public business claims follow canonical docs and site data.

## Monorepo apps

| App | Path | Stack |
|-----|------|-------|
| Website | [`apps/web/`](apps/web/) | Astro 5, Tailwind 4, TypeScript, Node 20 |
| Email pipeline | [`apps/email-pipeline/`](apps/email-pipeline/) | Python 3.12, `uv`, SQLite, Streamlit, optional CUDA ML |

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

- Monorepo context: [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md)
- Web app docs: [`apps/web/docs/README.md`](apps/web/docs/README.md)
- Email pipeline docs: [`apps/email-pipeline/docs/README.md`](apps/email-pipeline/docs/README.md)
- Contribution guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security policy: [`SECURITY.md`](SECURITY.md)

## License

MIT — see [`LICENSE`](LICENSE).
