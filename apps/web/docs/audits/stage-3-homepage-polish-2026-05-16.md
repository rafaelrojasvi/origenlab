# Stage 3 — Homepage & CTA polish — 2026-05-16

Follow-up to [full-site-consistency-audit-2026-05-16.md](./full-site-consistency-audit-2026-05-16.md) and [stage-1-2-fixes-2026-05-16.md](./stage-1-2-fixes-2026-05-16.md).

## Audit issues addressed

| ID | Status |
|----|--------|
| **HIGH-001** | **Fixed** — Homepage no longer uses large Ortoalresa-only `ProductShowcaseGrid` |
| **MED-001** | **Fixed** — CTA labels standardized via `src/lib/ctaLabels.ts` |
| **MED-002** | **Fixed** — Email CTAs and mailto subjects aligned |

## What changed

### Homepage
- Removed `ProductShowcaseGrid` from `index.astro`.
- Added **`HomeCommercialLines.astro`**: two equal cards (SERVA + Ortoalresa) with compact SKU/model chips and line-level CTAs.
- Kept **`HomeBrandsSection`** unchanged (equal brand cards).

### Full Ortoalresa catalog
- **5-product grid:** `/productos` (Ortoalresa block), `/productos/centrifugas`, `/marcas/ortoalresa`.
- **Comparison table:** `/productos/centrifugas` via new **`ProductComparisonStrip.astro`** (removed from homepage).

### CTA labels (`src/lib/ctaLabels.ts`)
| Key | Label |
|-----|--------|
| `viewProductDetail` | Ver ficha |
| `whatsapp` | Cotizar por WhatsApp |
| `quoteLine` | Cotizar línea |
| `email` | Solicitar por email |
| `solicitarCotizacion` | Solicitar cotización |

### Mailto subjects (`src/lib/whatsapp.ts`)
- Product: `Cotización OrigenLab - [PRODUCT_NAME]`
- Brand: `Cotización OrigenLab - [BRAND_NAME]`
- Generic: `Cotización OrigenLab`

## Files changed

- `src/components/HomeCommercialLines.astro` (new)
- `src/components/ProductComparisonStrip.astro` (new)
- `src/lib/ctaLabels.ts` (new)
- `src/pages/index.astro`
- `src/pages/productos/centrifugas/index.astro`
- `src/lib/whatsapp.ts`
- `src/components/ProductPreviewCard.astro`
- `src/components/ProductQuoteActions.astro`
- `src/components/QuoteCTA.astro`
- `src/components/BrandSkuCard.astro`
- `src/components/ProductShowcaseGrid.astro` (labels only; not on homepage)
- `src/pages/productos.astro`
- `src/pages/contacto.astro`
- `src/styles/global.css`

## Intentionally deferred

- MED-003 — Legal name asymmetry on home brand cards
- MED-004 — Nav/footer category discovery
- MED-005 — Marcas vs home section title wording
- MED-010 — Open Graph images
- MED-011 — Tidio / FloatingChat
- SERVA product detail pages
- Homepage section order beyond commercial-lines swap (no full redesign)

## Commands

```bash
cd apps/web
npm run check
npm run validate:catalog
npm run build
```
