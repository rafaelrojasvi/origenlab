# Homepage redesign (2026-05-16)

## Before (problem)

- Weak, centered hero with little product presence above the fold.
- Long text blocks before visuals (`homeIntro`, “Por qué contactarnos”).
- Duplicate brand blocks: `HomeBrandsSection` + `HomeCommercialLines`.
- Many similar flat white cards; poor hierarchy.
- Ortoalresa previews too small; page felt administrative, not B2B commercial.

## New structure (top → bottom)

1. **Header** — Larger logo, nav, visible “Cotizar” CTA, mobile menu.
2. **`HomeHero`** — Split layout: headline, chips, CTAs | product/brand panel (featured centrifuge, thumb, SERVA logo, category links).
3. **`HomeCommercialLines`** — Single “Líneas disponibles” section: Ortoalresa (prominent image tiles) + SERVA (logo + SKU rows), equal cards.
4. **`HomeCategoryCards`** — “Explore por necesidad del laboratorio” (3 visual category cards).
5. **`HomeProcess`** — “Cómo trabajamos” (4 steps + cautious support notes).
6. **FAQ** — Cleaner spacing (still on `index.astro`).
7. **`HomeFinalCTA`** — Strong closing band before footer.

## Files changed

| File | Change |
|------|--------|
| `src/pages/index.astro` | Rewritten to new section stack |
| `src/components/HomeHero.astro` | **New** |
| `src/components/HomeCategoryCards.astro` | **New** |
| `src/components/HomeProcess.astro` | **New** |
| `src/components/HomeFinalCTA.astro` | **New** |
| `src/components/HomeCommercialLines.astro` | Redesigned; Ortoalresa first, prominent previews |
| `src/components/HomeProductImagePreview.astro` | `variant="prominent"` for larger tiles |
| `src/components/Header.astro` | Stronger bar + Cotizar + mobile menu |
| `src/layouts/Layout.astro` | Optional `mainClass` prop |
| `src/components/Footer.astro` | `max-w-7xl` alignment with header |
| `src/styles/global.css` | Home section/panel/chip utilities |
| `scripts/validate-catalog.mjs` | Homepage component guards |

## Components removed from homepage (not deleted)

- `HomeBrandsSection` — no longer on `/` (still used conceptually via `/marcas`).
- Generic `Hero.astro` — not used on index (kept for possible inner pages).
- `Card` category row, `company.valueProps`, `serviceOfferings`, `QuoteCTA` block on home.

## Intentionally unchanged

- Product data (`products.ts`, `brands.ts`).
- Product detail pages, brand pages, `/productos/centrifugas` + `ProductComparisonStrip`.
- Tidio chat, OG meta, Stage 4 footer link set.
- No carousel, marquee, or horizontal product scroll.

## Manual inspection

- Desktop/mobile hero: Consul 22 (or fallback) large in panel; CTAs readable.
- Commercial lines: 5 Ortoalresa tiles legible on mobile (2-col grid).
- No horizontal overflow at ~390px width.
- Header “Menú” on small screens opens nav + cotizar.

## Checks

```bash
cd apps/web && npm run check && npm run validate:catalog && npm run build
```

| Command | Result |
|---------|--------|
| `npm run check` | 0 errors (48 files) |
| `npm run validate:catalog` | OK |
| `npm run build` | 16 pages, success |
