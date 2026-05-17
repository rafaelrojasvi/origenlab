# Stage 4 — Cleanup & hardening (2026-05-16)

Controlled pass after Stages 1–3. No homepage redesign, no SERVA detail pages, Tidio retained.

## Files changed

| Area | Files |
|------|--------|
| Chat | Deleted `src/components/FloatingChat.astro` |
| OG | `public/og/origenlab-og.svg`, `src/config/site.ts`, `src/layouts/Layout.astro` |
| Brand cards / legal names | `src/components/HomeBrandsSection.astro`, `src/pages/marcas.astro`, `src/pages/marcas/ortoalresa.astro`, `src/pages/marcas/serva-electrophoresis.astro` |
| Data | `src/data/products.ts`, `src/data/brands.ts` (`featuredIntro` → `brandIntro`) |
| Footer IA | `src/components/Footer.astro` |
| Spec tables | `src/components/ProductSpecTable.astro` |
| Assets / docs | `docs/product-assets.md`; removed `public/brands/serva-wordmark.svg` |
| Validation | `scripts/validate-catalog.mjs` |

## Issues addressed

| Audit ref | Action |
|-----------|--------|
| MED-011 | **FloatingChat removed** — Tidio remains the active live chat (`Layout.astro` inline script). |
| MED-012 | Default **OG image** + `og:image`, `og:image:alt`, `twitter:card=summary_large_image`, `twitter:image` (absolute `https://origenlab.cl/og/origenlab-og.svg`). |
| MED-013 / legal asymmetry | Home + `/marcas`: **public brand names only** (`homeCardTitle`). Legal name on Ortoalresa brand page with label **“Fabricante / referencia comercial”**. |
| MED-003 (partial) | Footer exposes Productos, Marcas, three category hubs, Centrífugas Ortoalresa, Contacto. Header unchanged. |
| MED-014 | Removed unused `showOnHome` and `featured` from all products. |
| LOW-001 | Removed unused `serva-wordmark.svg`. |
| LOW-002 | Bioprocen asset **kept archived**; `product-assets.md` + validator document status. |
| LOW-003 | `featuredIntro` renamed to **`brandIntro`**. |
| LOW-005 | Extended `validate-catalog.mjs` (see below). |
| Spec tables (mobile) | Responsive scroll region + smaller type/padding on narrow viewports. |

## Tidio / FloatingChat

**Decision:** Keep Tidio. **FloatingChat removed** because Tidio is the active chat implementation. No Tidio script changes in this pass.

## OG image

- Path: `public/og/origenlab-og.svg`
- Public URL: `https://origenlab.cl/og/origenlab-og.svg`
- Copy: OrigenLab, “Equipos para laboratorio”, `contacto@origenlab.cl`, Valdivia, Chile

## Nav / footer

- **Header:** unchanged (`site.nav`).
- **Footer:** Productos, Marcas, Alimentos, Control de calidad, Laboratorio clínico, Centrífugas Ortoalresa, Contacto. `/productos` remains main discovery hub.

## Data fields

| Field | Action |
|-------|--------|
| `showOnHome` (products) | **Removed** (unused) |
| `featured` (products) | **Removed** (all were `true`; no editorial meaning) |
| `featuredIntro` (brands) | **Renamed** to `brandIntro` |
| `showOnHomeBrandsSection` (brands) | **Kept** — drives home + `/marcas` brand grid |

## Assets

| Asset | Decision |
|-------|----------|
| `bioprocen-22-r.avif` | **Kept** on disk (archived; not in catalog/sitemap/pages) |
| `serva-wordmark.svg` | **Removed** (unused; `serva-logo.png` canonical) |
| Ortoalresa / SERVA logos | **Kept**; permission TODOs remain in `product-assets.md` |

## Validation improvements (`npm run validate:catalog`)

- No `FloatingChat.astro`
- No `showOnHome` / `featured` / `featuredIntro` in data
- Default OG asset + Layout meta tags
- No public Bioprocen slug in products, sitemap, or page sources
- Active Ortoalresa images + https manufacturer/datasheet URLs on disk
- Each brand has products; each `brandId` resolves
- Canonical Ortoalresa order unchanged
- `serva-wordmark.svg` must not return

## Intentionally deferred

- SERVA product detail pages (`/productos/...`)
- Homepage structure / `HomeCommercialLines` layout
- Tidio removal or replacement
- Bioprocen file delete (needs explicit approval)
- Ortoalresa/SERVA logo reproduction sign-off
- PNG variant of OG image (SVG sufficient for now)
- Header “Categorías” dropdown
- `floating-chat-widget-notes.md` archive (historical notes only)

## Checks

Run after changes:

```bash
cd apps/web
npm run check
npm run validate:catalog
npm run build
```

| Command | Result |
|---------|--------|
| `npm run check` | 0 errors, 0 warnings (42 files) |
| `npm run validate:catalog` | Catalog validation OK |
| `npm run build` | 16 pages built successfully |
