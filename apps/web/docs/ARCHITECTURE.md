# Web Architecture

Status: canonical  
Owner: web-maintainers  
Last reviewed: 2026-03-23

<a id="m-webarch-stack"></a>
## Stack

- Astro + Tailwind
- Static output in `dist/`
- No backend runtime in production by default

<a id="m-webarch-structure"></a>
## Core structure

- [`src/config/site.ts`](../src/config/site.ts): global site metadata
- [`src/data/`](../src/data/): business/content source of truth
- [`src/pages/`](../src/pages/): route pages
- [`src/components/`](../src/components/): reusable UI blocks
- [`public/.htaccess`](../public/.htaccess): HTTPS redirect and basic headers

<a id="m-webarch-constraints"></a>
## Design constraints

- Static-first architecture
- Minimal JavaScript
- Reusable components and data-driven content
- Truthful, conservative business claims only

<a id="m-webarch-related"></a>
## Related docs

- Security baseline: [`security-audit-v1.md`](security-audit-v1.md)
- Deployment behavior: [`RUNBOOK.md`](RUNBOOK.md#m-webrun-deploy)
