# Product assets — provenance

Status: canonical  
Owner: web-maintainers  
Last reviewed: 2026-05-16

Assets for public product/brand pages are stored under `public/` (not hotlinked in production).

## Ortoalresa — active catalog (2026-05-16)

| Product | Local image | Source image | PDF |
|---------|-------------|--------------|-----|
| Biocen 22 | `public/products/ortoalresa/biocen-22.avif` | https://ortoalresa.com/imagen_producto/Biocen_22.avif | https://ortoalresa.com/catalogo_producto/Catalogo_Biocen_22_ESP.pdf |
| Biocen 22 R | `public/products/ortoalresa/biocen-22-r.avif` | https://ortoalresa.com/imagen_producto/Biocen_22_R.avif | https://ortoalresa.com/catalogo_producto/Catalogo_Biocen_22_R_ESP.pdf |
| Consul 22 | `public/products/ortoalresa/consul-22.avif` | https://ortoalresa.com/imagen_producto/Consul_22.avif | https://ortoalresa.com/catalogo_producto/Catalogo_serie_Consul_22_ESP.pdf |
| Digicen 22 | `public/products/ortoalresa/digicen-22.avif` | https://ortoalresa.com/imagen_producto/Digicen_22.avif | https://ortoalresa.com/catalogo_producto/Catalogo_serie_Digicen_22_ESP.pdf |
| Digicen 22 R | `public/products/ortoalresa/digicen-22-r.avif` | https://ortoalresa.com/imagen_producto/Digicen_22_R.avif | Mismo PDF de serie Digicen 22 (fabricante) |

**Nota:** Digicen 22 y Digicen 22 R comparten el catálogo PDF de la serie Digicen 22 según documentación del fabricante.

Logo: `public/brands/ortoalresa-logo.svg` — https://ortoalresa.com/static/images/logo-header-normal-1c27f117243d1215a0b668f0ee824e57.svg

**TODO:** Confirm with OrigenLab that local reproduction of logo and product images on origenlab.cl is permitted.

## SERVA

Logo: `public/brands/serva-logo.png` (referenciado en `brands.ts`).

`public/brands/serva-wordmark.svg` — **removed** (unused duplicate; logo PNG is canonical).

**TODO:** Confirm with OrigenLab that local reproduction of SERVA logo on origenlab.cl is permitted.

## Open Graph (sitio)

| Asset | Notes |
|-------|--------|
| `public/og/origenlab-og.svg` | Default social preview (`og:image` / `twitter:image` → `https://origenlab.cl/og/origenlab-og.svg`). |

## Archived / unused on site

| Asset | Notes |
|-------|--------|
| `public/products/ortoalresa/bioprocen-22-r.avif` | **Archived — do not delete** without explicit approval. Removed from public catalog (product Bioprocen 22 R). Kept on disk for reference; must not appear in `products.ts`, routes, or sitemap. Validated by `npm run validate:catalog`. |

## Commercial copy

Public pages must **not** state exclusive distribution or official representation. WhatsApp CTAs use prefilled quote messages via `src/lib/whatsapp.ts` (`https://wa.me/56962567816?text=...`).
