# Full Site Consistency Audit — 2026-05-16

**Scope:** `apps/web` public Astro site (source + `dist/` after production build)  
**Method:** Route discovery, `npm run check` / `validate:catalog` / `build`, source review of pages/components/data, built HTML spot-checks (links, meta, WhatsApp URLs, removed products).  
**No fixes applied** — findings only.

---

## Executive summary

The site **builds cleanly** (16 static routes), **Bioprocen 22 R is absent** from routes/sitemap/HTML, and **Ortoalresa product data is largely consistent** across detail pages, family page, and homepage showcase. WhatsApp product CTAs use the correct number (`56962567816`) and prefilled Ortoalresa messages where `buildWhatsAppQuoteUrl` is used.

The **largest consistency gaps** are not broken links but **information architecture and visual hierarchy**:

1. **Brand parity on the homepage** — SERVA and Ortoalresa are equal in “Marcas y líneas disponibles”, but only Ortoalresa gets a large product showcase immediately below, which reads as secondary vs primary brand hierarchy in practice.
2. **Product discovery asymmetry** — All five Ortoalresa centrifuges have full fichas; **SERVA SKUs have no `/productos/...` detail routes** yet appear in “Productos destacados” on `/productos` without “Ver ficha”.
3. **CTA fragmentation** — At least five WhatsApp patterns (prefilled product, prefilled brand, bare `wa.me`, Tidio chat, unused `FloatingChat` component).
4. **`/productos` “destacados”** — Every catalog item has `featured: true`, so the section does not mean “highlighted subset”.
5. **Copy risk on `/nosotros`** — Warranty/installation stated more absolutely than on product fichas.

Secondary themes: duplicate related-product blocks on two category pages, product **sort order differs** by page, CTA label/style drift, dead `showOnHome` data field, missing Open Graph images, footer padding for third-party chat.

---

## Build/check status

| Command | Result |
|---------|--------|
| `npm run check` | **Pass** — 0 errors, 0 warnings, 0 hints (39 Astro/TS files) |
| `npm run validate:catalog` | **Pass** — Catalog validation OK |
| `npm run build` | **Pass** — **16 page(s)** built in ~715ms → `dist/` |

**Sitemap vs build:** `public/sitemap.xml` lists **16 URLs**; matches `dist/**/index.html` routes (trailing-slash canonical style in layout).

---

## Pages audited

| # | Route | Source | In sitemap |
|---|-------|--------|------------|
| 1 | `/` | `src/pages/index.astro` | Yes |
| 2 | `/nosotros/` | `src/pages/nosotros.astro` | Yes |
| 3 | `/productos/` | `src/pages/productos.astro` | Yes |
| 4 | `/productos/centrifugas/` | `src/pages/productos/centrifugas/index.astro` | Yes |
| 5 | `/productos/centrifugas/biocen-22/` | `[slug].astro` | Yes |
| 6 | `/productos/centrifugas/biocen-22-r/` | `[slug].astro` | Yes |
| 7 | `/productos/centrifugas/consul-22/` | `[slug].astro` | Yes |
| 8 | `/productos/centrifugas/digicen-22/` | `[slug].astro` | Yes |
| 9 | `/productos/centrifugas/digicen-22-r/` | `[slug].astro` | Yes |
| 10 | `/marcas/` | `src/pages/marcas.astro` | Yes |
| 11 | `/marcas/serva-electrophoresis/` | `src/pages/marcas/serva-electrophoresis.astro` | Yes |
| 12 | `/marcas/ortoalresa/` | `src/pages/marcas/ortoalresa.astro` | Yes |
| 13 | `/contacto/` | `src/pages/contacto.astro` | Yes |
| 14 | `/categorias/alimentos/` | `categorias/[slug].astro` | Yes |
| 15 | `/categorias/control-de-calidad/` | `categorias/[slug].astro` | Yes |
| 16 | `/categorias/laboratorio-clinico/` | `categorias/[slug].astro` | Yes |

**Not generated (by design):** `/categorias/` index, SERVA product detail URLs, Bioprocen 22 R, `/productos/{family}` beyond centrifugas.

**Built HTML checks:** One `<h1>` per page via `Hero` (home) or `PageHeader` (inner pages). No `bioprocen` / `marquee` / `ProductScrollRow` in `dist/`. Internal page links resolve; `/_astro/*.css` assets present in `dist/_astro/`.

---

## Critical issues

*None that break routing, show removed products publicly, or use wrong WhatsApp number.*

| ID | Severity | Page(s) | File(s) | Problem | Why it matters | Suggested fix | When |
|----|----------|---------|---------|---------|----------------|---------------|------|
| — | — | — | — | No critical defects found in this pass | — | — | — |

---

## High-priority inconsistencies

| ID | Severity | Page(s) | File(s) | Problem | Why it matters | Suggested fix | When |
|----|----------|---------|---------|---------|----------------|---------------|------|
| HIGH-001 | High | `/` | `index.astro`, `HomeBrandsSection.astro`, `ProductShowcaseGrid.astro` | After equal brand cards, **only Ortoalresa** gets a large 5-product showcase + comparison table. SERVA has no equivalent home product block. | Contradicts stated goal: same brand hierarchy; Ortoalresa dominates scroll depth and product exposure. | Add balanced home treatment (e.g. compact SERVA line + link to marca) or move Ortoalresa block under `/productos/centrifugas` only; keep brands section as sole home brand block. | Stage 3 |
| HIGH-002 | High | `/productos/` | `productos.astro`, `products.ts` | **“Productos destacados”** renders all 8 products (`featured: true` on every item). Header CTA is **“Ver línea SERVA”** only — no symmetric Ortoalresa CTA in that band. | “Destacados” has no editorial meaning; layout is 8 cards in 3 columns (awkward last row); brand balance skewed. | Set `featured` only on true subset; split or tag by brand; add “Ver centrífugas Ortoalresa” CTA. | Stage 2 |
| HIGH-003 | High | `/productos/`, `/marcas/serva-*` | `products.ts`, `ProductPreviewCard.astro` | **SERVA products lack `productFamilySlug`** → no `/productos/...` detail pages. Cards on `/productos` show **no “Ver ficha”** (only summary). | Quote funnel dead-ends for SERVA vs Ortoalresa; same grid looks broken/incomplete. | Add SERVA family/slug pages or brand-SKU template; until then, hide SERVA from grid or link all cards to marca + WhatsApp. | Stage 2 |
| HIGH-004 | High | Multiple | `QuoteCTA.astro`, `contact.ts`, `Layout.astro` vs `whatsapp.ts` | **Generic WhatsApp** (`QuoteCTA`, footer, contacto) uses `https://wa.me/56962567816` **without** prefilled quote text. Product/brand CTAs use `buildWhatsAppQuoteUrl` with message. | Inconsistent operator experience; more drop-off on generic buttons. | Route all WhatsApp CTAs through `buildWhatsAppQuoteUrl()` (or shared wrapper) with context-appropriate defaults. | Stage 2 |
| HIGH-005 | High | `/marcas/ortoalresa/` vs `/marcas/serva-electrophoresis/` | Brand page templates | Ortoalresa: `ProductQuoteActions` (WhatsApp + email) in hero. SERVA: **no** equivalent quote block in hero; only bottom `QuoteCTA`. | Same page type, different conversion paths; Ortoalresa feels more “ready to quote”. | Add `ProductQuoteActions` (or equivalent) to SERVA brand hero. | Stage 2 |
| HIGH-006 | High | `/nosotros/` | `nosotros.astro` | Copy: “Ofrecemos soporte, asesoría, **garantía**, e instalación o puesta en marcha…” without “según fabricante / según acuerdo” qualifiers used elsewhere. | Overclaims vs cautious product/ficha language; B2B trust risk. | Align with `company.ts` value props and product disclaimers. | Stage 1 |
| HIGH-007 | High | Family, brand, home showcase | `productFamilies.ts`, `catalog.ts`, `index.astro` | **Product order differs:** family/brand use `catalogSortOrder` (Consul before Digicen); home showcase uses `ortoalresaHomeShowcaseSlugs` (Consul last). | Users see different “canonical” ordering; comparison mentally harder. | Single exported order used everywhere or document intentional “home vs catalog” order. | Stage 2 |
| HIGH-008 | High | `/categorias/control-de-calidad/`, `/categorias/laboratorio-clinico/` | `categorias/[slug].astro`, `products.ts` | **Same five centrifuges** listed on both category pages (shared `categorySlugs`). | Duplicate content; unclear why both categories show identical equipment lists. | Differentiate copy, rotate products by category intent, or link to family page once. | Stage 2 |

---

## Medium-priority polish

| ID | Severity | Page(s) | File(s) | Problem | Why it matters | Suggested fix | When |
|----|----------|---------|---------|---------|----------------|---------------|------|
| MED-001 | Medium | Site-wide | `ProductPreviewCard.astro` vs `ProductShowcaseGrid.astro` | Link labels: **“Ver ficha”** vs **“Ver ficha del equipo →”**; WhatsApp: **“Cotizar”** vs **“Cotizar por WhatsApp”**. | Same actions look like different flows. | Standardize CTA dictionary in one module. | Stage 3 |
| MED-002 | Medium | Site-wide | `QuoteCTA.astro`, `contacto.astro`, `ProductQuoteActions.astro` | Email CTAs: **“Correo”**, **“Enviar correo”**, **“Solicitar cotización por email”** (mailto subjects differ). | Minor friction for users and analytics. | Unify labels; keep mailto helper everywhere. | Stage 3 |
| MED-003 | Medium | `/` | `HomeBrandsSection.astro`, `brands.ts` | **Legal name** (`Álvarez Redondo S.A.`) shown only for Ortoalresa on home brand cards, not for SERVA. | Subtle visual/legal hierarchy. | Show legal names for both or neither. | Stage 3 |
| MED-004 | Medium | Nav / footer | `site.ts`, `Footer.astro` | Header: Nosotros, Productos, Marcas, Contacto — **no “Categorías”**. Footer: “Productos y categorías” → `/productos` only. | Categories exist but are second-class in IA. | Add category discovery on `/productos` (already partial) or footer subsection. | Stage 3 |
| MED-005 | Medium | `/marcas/` vs `/` | `marcas.astro`, `HomeBrandsSection.astro` | Section titles differ: **“Marcas y líneas para cotización”** vs **“Marcas y líneas disponibles”**. | Wording drift. | Pick one phrase sitewide. | Stage 3 |
| MED-006 | Medium | `/marcas/ortoalresa/` vs `/marcas/serva-*` | Brand pages | Ortoalresa hero label **“Fabricante”**; SERVA **“Visión general”**. | Same template family, different semantics. | Harmonize section labels (e.g. “Sobre la línea”). | Stage 3 |
| MED-007 | Medium | Product fichas | `products.ts` | `ctaText` varies: most **“Solicitar cotización”**; Biocen 22 R / Digicen 22 R use **“Consultar configuración”** → changes bottom `QuoteCTA` title only on those pages. | Inconsistent primary CTA wording on detail pages. | Normalize `ctaText` or map to one label. | Stage 2 |
| MED-008 | Medium | Home showcase vs fichas | `productShowcase.ts`, `products.ts` | Showcase uses **short application lines** and comparison **“Tipo”** labels (e.g. “Universal ventilada”) that differ slightly from `equipmentType` on fichas (“Centrífuga universal”). | Not wrong, but two vocabularies for same thing. | Document as editorial shorthand or align strings. | Stage 3 |
| MED-009 | Medium | `/productos/centrifugas/` | `centrifugas/index.astro` | Filter chips (ventilada, refrigerada, …) are **non-interactive** decorations. | Looks like broken filters. | Remove or implement filtering. | Stage 4 |
| MED-010 | Medium | All pages | `Layout.astro` | **No `og:image`** (or Twitter image). Social previews are text-only. | Weak sharing/preview for B2B referrals. | Add default OG image asset. | Stage 3 |
| MED-011 | Medium | All pages | `Layout.astro` | Third-party **Tidio** script + footer `pb-28`/`pb-24` padding; **`FloatingChat.astro` exists but is not imported** (dead code, alternate WA widget with pulse animation). | Two chat implementations in repo; clutter risk if both enabled. | Delete or wire one; document chosen channel. | Stage 4 |
| MED-012 | Medium | Product fichas | `ProductSpecTable.astro` | Spec tables have no horizontal scroll wrapper; long values may **squeeze on ~390px**. | Mobile readability. | Add `overflow-x-auto` on narrow viewports. | Stage 3 |
| MED-013 | Medium | `/productos/centrifugas/digicen-*` | `products.ts` | Digicen 22 and 22 R share **same PDF URL** (`Catalogo_serie_Digicen_22_ESP.pdf`). | May be correct from manufacturer; worth confirming. | Verify with source; note on page if shared catalog is intentional. | Stage 2 |
| MED-014 | Medium | `products.ts` | Data model | **`showOnHome: true` on all products** but **never read** in codebase; home Ortoalresa list uses `getOrtoalresaCentrifugesForHome()` only. | Misleading maintainers; SERVA flagged “on home” but not shown in product grid. | Remove field or implement `getHomeProducts()`. | Stage 4 |
| MED-015 | Medium | `/productos/` | `productos.astro` | Centrifuge promo block duplicates messaging from marca/family pages; **“Disponible bajo cotización”** repeated. | Verbose, slightly patched feel. | Tighten copy once IA settled. | Stage 3 |
| MED-016 | Medium | Brand cards | `brands.ts` | SERVA `name` is **“SERVA Electrophoresis GmbH”** but cards use **“SERVA Electrophoresis”** — inconsistency when `brand.name` shown on `/productos` cards. | Naming inconsistency. | Use `homeCardTitle` everywhere or shorten `name`. | Stage 3 |
| MED-017 | Medium | Category cards | `Card.astro` | “Ver categoría →” hint is **`opacity-0` until hover** — easy to miss on touch/no-hover. | Discoverability / a11y. | Always visible or use `group-focus-within`. | Stage 3 |

---

## Low-priority cleanup

| ID | Severity | Page(s) | File(s) | Problem | Why it matters | Suggested fix | When |
|----|----------|---------|---------|---------|----------------|---------------|------|
| LOW-001 | Low | `public/brands/` | Assets | **`serva-wordmark.svg` unused**; `serva-logo.png` is referenced and **exists** (prior “missing logo” issue appears resolved). | Repo clutter. | Delete unused asset or switch to wordmark. | Stage 4 |
| LOW-002 | Low | `public/products/ortoalresa/` | Assets | **`bioprocen-22-r.avif` on disk**, correctly excluded from site/sitemap (documented in `product-assets.md`). | Disk vs public catalog drift. | Keep archived per docs or delete after approval. | Stage 4 |
| LOW-003 | Low | `brands.ts` | Data | `featuredIntro` on SERVA — legacy naming post–“featured brand” removal. | Naming confusion. | Rename to `brandIntro` or similar. | Stage 4 |
| LOW-004 | Low | `global.css` | CSS | Marquee/carousel CSS **removed**; showcase classes only. **`.showcase-product-grid` has no custom rules** (Tailwind only) — fine. | — | None required. | — |
| LOW-005 | Low | `validate-catalog.mjs` | Script | Validates showcase slugs and ProductScrollRow removal; does not validate **`showOnHome`**, SERVA detail gap, or sitemap↔`featured` logic. | Coverage gaps. | Extend validation rules. | Stage 4 |
| LOW-006 | Low | Docs | `company-scope.md` vs `product-assets.md` | **Last reviewed** dates differ (2026-03-24 vs 2026-05-16). | Doc freshness signal. | Align review dates when editing. | Stage 4 |
| LOW-007 | Low | Layout | `Layout.astro` | `meta name="generator" content={Astro.generator}`. | Minor SEO noise. | Remove if undesired. | Stage 4 |
| LOW-008 | Low | `contact.ts` | Data | `instagramHandle: null` — placeholder unused. | — | Remove or implement. | Stage 4 |
| LOW-009 | Low | FAQ | `index.astro` | Chevron uses `motion-safe:transition` (valid Tailwind v4 variant). | — | — | — |
| LOW-010 | Low | `product-assets.md` | Docs | **TODO:** permission for Ortoalresa/SERVA asset reproduction still open. | Legal/compliance. | Confirm with client. | Stage 1 |

---

## Product/catalog matrix

| Product | Active? | Data in `products.ts`? | Detail page? | Brand page? | Family page? | Homepage showcase? | Image? | PDF? | WhatsApp CTA? | Notes |
|---------|---------|------------------------|--------------|-------------|--------------|-------------------|--------|------|---------------|-------|
| Biocen 22 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes (prefilled) | `catalogSortOrder` 1 |
| Biocen 22 R | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | `ctaText`: “Consultar configuración” |
| Digicen 22 | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Shared PDF with 22 R |
| Digicen 22 R | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes | `ctaText`: “Consultar configuración” |
| Consul 22 | Yes | Yes | Yes | Yes | Yes | Yes (last) | Yes | Yes | Yes | Order 3 in family, 5th on home |
| Bioprocen 22 R | **No** | **No** | **No** | **No** | **No** | **No** | Archived file only | — | — | Not in sitemap/HTML; asset on disk |
| BlueSlick™ (SERVA) | Yes | Yes | **No** | Yes | No | No* | No | No | No on card | `showOnHome` true but unused |
| TEMED 25 ml (SERVA) | Yes | Yes | **No** | Yes | No | No* | No | No | No on card | Long title on cards |
| REPEL-SILANE (SERVA) | Yes | Yes | **No** | Yes | No | No* | No | No | No on card | — |

\* `showOnHome: true` in data is **not wired** to any home product UI.

---

## Brand hierarchy matrix

| Brand | Brand page | `/marcas` listing | Homepage block | Primary CTAs on brand page | Logo | Copy tone | Notes |
|-------|------------|-------------------|----------------|----------------------------|------|-----------|-------|
| SERVA | Yes | Yes (equal card) | Equal card in `HomeBrandsSection` | Bottom `QuoteCTA` only; no hero WhatsApp | `serva-logo.png` OK | Conservative; prepago noted | No product images in catalog |
| Ortoalresa | Yes | Yes (equal card) | Equal card + **large `ProductShowcaseGrid`** | Hero `ProductQuoteActions` + sections + `QuoteCTA` | SVG OK | Manufacturer attribution present | Legal name on home card only |

---

## CTA matrix

| CTA label / action | Where it appears | WhatsApp prefilled? | Email | Notes |
|--------------------|------------------|---------------------|-------|-------|
| Solicitar cotización | Hero `/`, home brand cards, multiple `QuoteCTA` | No (goes to `/contacto` or mailto in QuoteCTA) | Via contacto / QuoteCTA | — |
| Cotizar por WhatsApp | Showcase, family, brand product cards, `ProductQuoteActions` | **Yes** (product or brand) | — | Correct E.164 |
| Cotizar | Home showcase cards only | **Yes** (product) | — | Shorter label vs rest |
| Ver ficha | Home showcase | — | — | — |
| Ver ficha del equipo → | `ProductPreviewCard` | — | — | Arrow suffix unique |
| Ver ficha del fabricante → | Product detail | — | — | External |
| Ver línea completa | Home showcase | — | — | → `/productos/centrifugas` |
| Ver centrífugas / Ver marca… | `/productos`, family | — | — | Outline buttons |
| Correo / Enviar correo / WhatsApp | `QuoteCTA`, contacto | **No** on WhatsApp | mailto | Bare `wa.me` |
| Solicitar cotización por email | `ProductQuoteActions` | — | mailto with subject | — |
| WhatsApp (footer) | Footer | **No** | — | — |
| Tidio chat | `Layout.astro` script | N/A | — | Third-party |

---

## Mobile/responsive findings

| Route | ~390px | ~768px | ~1280px | Notes |
|-------|--------|--------|---------|-------|
| `/` | Showcase stacks 1 col; comparison → stacked cards | 2-col cards | 3+2 grid centered | Large showcase height; many CTAs |
| `/productos/` | 8 “destacados” cards tall stack | 2–3 cols | 3 cols, uneven last row | SERVA cards text-heavy |
| `/productos/centrifugas/*` | Image + spec table may feel tight | 2-col layout on detail | Side-by-side image/specs | Spec table (MED-012) |
| `/marcas/*` | 1-col product grids | 2–3 cols | OK | — |
| `/categorias/*` | Related products 1–2 col | OK | OK | Alimentos: no related block |
| All | Footer extra bottom padding (Tidio) | OK | OK | `pb-28` on copyright |

No horizontal scrollbar observed on showcase comparison (table hidden `<md`, cards on mobile). No carousel/marquee motion.

---

## SEO/meta findings

| Route | Title unique? | Meta description | Issues |
|-------|---------------|------------------|--------|
| `/` | Yes | Yes | No og:image |
| `/nosotros/` | Yes | Yes | — |
| `/productos/` | Yes | Yes | “destacados” not reflected in meta |
| `/productos/centrifugas/` | Yes | Yes | — |
| Each centrifuge | Yes (per `metaTitle`) | Yes (trimmed 158) | Good product specificity |
| `/marcas/*` | Yes | Yes | — |
| `/categorias/*` | Yes | Yes (sliced) | — |
| `/contacto/` | Yes | Yes | — |

Canonical: `https://origenlab.cl{path}/` via `Layout.astro`.  
Sitemap: matches build; no Bioprocen; no orphan HTML routes found.

---

## Asset findings

| Asset | Status | Notes |
|-------|--------|-------|
| Ortoalresa product AVIFs (×5) | Present | Used on site |
| Ortoalresa logo SVG | Present | — |
| SERVA `serva-logo.png` | Present | Referenced in `brands.ts` |
| SERVA `serva-wordmark.svg` | **Unused** | LOW-001 |
| Bioprocen AVIF | On disk only | Correctly excluded from HTML |
| SERVA product images | **None** in `public/` | Cards on `/productos` without images for SERVA |
| `favicon.svg` / `favicon.ico` | Both exist | Layout uses SVG |
| `docs/product-assets.md` | Accurate for active five | TODO permission note still open |

---

## Code/data structure notes

- **Removed:** `ProductScrollRow.astro`, marquee CSS — confirmed gone.
- **Added:** `ProductShowcaseGrid.astro`, `lib/productShowcase.ts` — homepage-only comparison copy duplicate of `products.ts` specs.
- **Dead:** `FloatingChat.astro` (not imported); `showOnHome` product flag unused.
- **Naming:** `ortoalresaHomeShowcaseSlugs` (good); `featured` on products still means “show in destacados grid”.
- **WhatsApp single source:** `lib/whatsapp.ts` — not used by `QuoteCTA` / footer / `contact.ts` `whatsappUrl()`.

---

## Recommended fix plan

### Stage 1 — Trust-breaking fixes
- HIGH-006: Soften `/nosotros` warranty/installation copy.
- LOW-010: Confirm asset reproduction rights (Ortoalresa/SERVA).

### Stage 2 — Product/catalog consistency
- HIGH-002, HIGH-003, HIGH-007, HIGH-008.
- HIGH-004, HIGH-005 (WhatsApp + brand page parity).
- MED-007, MED-013.
- Implement real `featured` flags or rename section.

### Stage 3 — Homepage and visual hierarchy polish
- HIGH-001 (brand vs showcase balance).
- MED-001–MED-008, MED-010, MED-012, MED-015, MED-016, MED-017.

### Stage 4 — Cleanup/refactor/docs
- MED-009, MED-011, MED-014.
- LOW-001–LOW-009; extend `validate-catalog.mjs`.

---

## Summary counts

| Severity | Count |
|----------|------:|
| Critical | 0 |
| High | 8 |
| Medium | 17 |
| Low | 10 |
| **Total issues logged** | **35** |

**Pages audited:** 16  
**Top issues to tackle first:** HIGH-001, HIGH-002, HIGH-003, HIGH-004, HIGH-006, HIGH-005, HIGH-007, HIGH-004 (WhatsApp unification), HIGH-002 (featured logic).

---

*End of audit — no code changes made.*
