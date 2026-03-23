# OrigenLab — Repository Agent Instructions

## Project overview

OrigenLab is a Chile-based laboratory equipment company. The website is a primarily static, professional, Spanish-first company site that helps potential clients understand what the company offers and contact OrigenLab to request quotations.

The site should communicate trust, clarity, technical seriousness, and responsiveness without exaggeration.

## Reference documents

Files under `docs/` are **not** loaded into context automatically. When a task matches the area below, **read the relevant file first** before changing code or copy.

**Canonical business data (prefer these over hardcoded page text):**

- `src/data/company.ts` — narrative, audience, safe framing
- `src/data/contact.ts` — email, phone, WhatsApp, hours; **public location** = `locationPublic`; **full street** = `addressLine` (internal/legal/logistics only — see “Contact / address policy” below)
- `src/data/services.ts` — support/service lines
- `src/data/categories.ts` — product categories and buyer copy
- `src/data/brands.ts` — brands (conservative until formal list exists)
- `src/data/faq.ts` — FAQ entries
- `src/data/documents.ts` — future catalogs/fichas (empty until real files exist)

**When to open project docs:**

- Deployment, hosting, `dist/`, HostGator → `docs/deployment.md`
- Prior security/link/claims decisions → `docs/security-audit-v1.md`
- Full company scope (brief for humans/cotizations) → `docs/company-scope.md` (summary of `src/data/*` + prompt for quotation rewriting)
- Email DB → business signal (prompt for another AI) → `docs/EMAIL_BUSINESS_SIGNAL_PROMPT.md`
- Collaborator and AI onboarding (structure, Cursor rules, Claude skills) → `CONTRIBUTING.md`

If a task touches copy, SEO, contact details, categories, deployment, or trust/safety language, consult the relevant reference above. **Do not invent facts** not present in the data layer or referenced docs.

**Before making changes (quick check):**

- Use `src/data/*` as the canonical business source of truth.
- If the task involves deployment or hosting, read `docs/deployment.md`.
- If the task involves copy safety, prior decisions, or trust claims, read `docs/security-audit-v1.md`.
- Prefer referenced project docs over inferred assumptions.
- Do not invent brands, certifications, specifications, delivery times, warranty terms, or provider relationships.

## What OrigenLab does

OrigenLab sells laboratory equipment in Chile for service and research environments.

Current target customer types include:
- laboratorios de servicios
- laboratorios de investigación
- universidades
- clínicas
- hospitales
- industrias de I+D

Current known product/service areas:
- equipos para alimentos
- equipos para control de calidad
- equipos para laboratorio clínico

Current known service/support offerings:
- soporte
- asesorías
- garantía
- instalación
- puesta en marcha de equipos más complejos

## Website goals

The website should help visitors:
1. understand what OrigenLab offers
2. identify relevant product categories
3. request a quotation
4. contact the company quickly through the available channels
5. access product catalogs or technical sheets when available

This is not a flashy startup site. It should feel trustworthy, clear, and commercially useful.

## Current contact data

Use these details unless explicitly updated in the repo:

- Company name: OrigenLab
- Email: contacto@origenlab.cl
- Phone: +56 9 6256 7816
- WhatsApp: +56 9 6256 7816
- Hours: 09:00–18:00 (same as `contact.hours` in code)
- Geography: all Chile

### Contact / address policy

- **Public-facing default** (website, generic quotations, marketing copy): use **`locationPublic`** from `src/data/contact.ts` — currently **Valdivia, Chile** — and **do not** put the street in that material. `site.ts` already maps `site.location` from `locationPublic`.
- **Full street** (**Oettinger 51, depto 206, Valdivia, Chile**): **`contact.addressLine` in code** — for **internal**, **legal**, **logistics**, or any artifact that explicitly requires a postal address. Do not copy the street into new public web sections or public quote PDFs unless the business decides otherwise; align with `docs/company-scope.md`.

If Instagram is mentioned, only include it when the exact handle is available in repo data.

## Non-negotiable content rules

Do not invent:
- brands
- certifications
- official partnerships
- technical specifications
- product availability
- warranty terms beyond what is explicitly provided
- installation coverage details not confirmed in the repo
- response time promises
- client logos or customer names
- regulatory claims

If information is missing, use placeholders in code/comments or write copy that stays general and truthful.

## Tone and writing style

Public-facing copy must be:
- Spanish-first
- professional
- clear
- concise
- technically credible
- commercially useful
- restrained, never exaggerated

Avoid:
- hype
- vague marketing fluff
- "líder absoluto", "número uno", "soluciones revolucionarias"
- fake urgency
- unsupported claims

Prefer:
- direct explanations
- concrete business value
- short paragraphs
- clear CTAs like "Solicitar cotización" or "Contactar por WhatsApp"

## Product/content modeling rules

Treat current business reality carefully:
- OrigenLab mainly sells equipment today
- consumables/insumos may be added later
- brands are pending formal confirmation
- catalogs and technical sheets exist and can support future structured product data

When modeling data, prefer simple, extensible structures:
- categories
- services
- contact info
- downloadable documents
- optional brand references

Do not overengineer with a backend unless clearly needed.

## Technical preferences

Prefer:
- Astro for static pages
- Tailwind for styling
- reusable components
- clean content/data separation
- simple data files for categories, services, contact info
- static-first architecture

Avoid:
- unnecessary client-side JavaScript
- premature CMS complexity
- unnecessary backend work
- duplicated markup across pages
- large monolithic components

## Deployment assumptions

Assume static deployment to HostGator or similar shared hosting unless the repo states otherwise.

Important assumptions:
- production build output should be in `dist/`
- deployment should upload the built static site contents correctly
- avoid nested `dist/dist`
- verify asset paths carefully
- prefer robust, simple static deployment patterns

## When editing or generating content

Always optimize for:
1. factual correctness
2. clarity
3. maintainability
4. commercial usefulness
5. easy quotation/contact flow

If asked to create new copy and information is incomplete, write the safest truthful version.
