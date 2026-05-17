# Stage 3 addendum — Homepage centrifuge image preview (2026-05-16)

Correction after Stage 3: Ortoalresa **product images** return to the homepage in a compact form. The problem was never the images themselves; it was the **large catalog-style block** (`ProductShowcaseGrid` + comparison table) that made Ortoalresa dominate the page.

## What changed

| Item | Detail |
|------|--------|
| Component | `HomeProductImagePreview.astro` — 5 compact image tiles inside the Ortoalresa card in `HomeCommercialLines.astro` |
| Helper | `src/lib/homeProductPreview.ts` — short type labels for tiles |
| SERVA card | Logo + 3 SKU mini-tiles (no fake images) for visual balance |
| Layout | Mobile 2 cols · tablet 3 cols (3+2) · desktop 5 cols · no scroll, no animation |

## HIGH-001 status

**Still fixed.** The homepage does **not** restore `ProductShowcaseGrid` or a comparison table. Images are preview tiles only (name + short type + link to ficha). Full grid and `ProductComparisonStrip` remain on **`/productos/centrifugas`** only.

## Files

- `src/components/HomeProductImagePreview.astro` (new)
- `src/components/HomeCommercialLines.astro`
- `src/lib/homeProductPreview.ts` (new)
