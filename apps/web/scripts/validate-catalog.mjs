#!/usr/bin/env node
/**
 * Catalog + asset integrity checks (no TypeScript runner required).
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
let failed = false;

function assert(condition, message) {
  if (!condition) {
    console.error(message);
    failed = true;
  }
}

function walkAstro(dir, acc = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) walkAstro(full, acc);
    else if (entry.name.endsWith('.astro')) acc.push(full);
  }
  return acc;
}

const brandsSrc = readFileSync(join(root, 'src/data/brands.ts'), 'utf8');
const productsSrc = readFileSync(join(root, 'src/data/products.ts'), 'utf8');
const familiesSrc = readFileSync(join(root, 'src/data/productFamilies.ts'), 'utf8');
const contactSrc = readFileSync(join(root, 'src/data/contact.ts'), 'utf8');
const layoutSrc = readFileSync(join(root, 'src/layouts/Layout.astro'), 'utf8');
const sitemapSrc = readFileSync(join(root, 'public/sitemap.xml'), 'utf8');

const REMOVED_SLUGS = ['bioprocen-22-r'];
const CANONICAL_ORTO_ORDER = [
  'biocen-22',
  'biocen-22-r',
  'digicen-22',
  'digicen-22-r',
  'consul-22',
];

const ACTIVE_ORTO_ASSETS = CANONICAL_ORTO_ORDER.map(
  (slug) => `public/products/ortoalresa/${slug}.avif`,
);

const brandIds = [...brandsSrc.matchAll(/id: '([^']+)'/g)].map((m) => m[1]);

assert(brandsSrc.includes("id: 'ortoalresa'"), 'brands.ts: missing ortoalresa');
assert(brandsSrc.includes('showOnHomeBrandsSection: true'), 'brands.ts: home brands section flags');
assert(
  (brandsSrc.match(/showOnHomeBrandsSection: true/g) ?? []).length >= 2,
  'brands.ts: expected SERVA and Ortoalresa on home brands section',
);
assert(!brandsSrc.includes('featuredOnHome:'), 'brands.ts: remove featuredOnHome hierarchy');
assert(!brandsSrc.includes('secondaryFeaturedOnHome'), 'brands.ts: remove secondaryFeaturedOnHome');
assert(!brandsSrc.includes('featuredIntro'), 'brands.ts: use brandIntro instead of featuredIntro');
assert(brandsSrc.includes('brandIntro:'), 'brands.ts: brandIntro expected for SERVA page');
assert(!brandsSrc.match(/distribuidor exclusivo|representante oficial/i), 'brands.ts: unsafe copy');

assert(!productsSrc.includes('showOnHome:'), 'products.ts: remove unused showOnHome');
assert(!productsSrc.includes('featured:'), 'products.ts: remove unused featured flag');
assert(!productsSrc.match(/\bfeatured\b/), 'products.ts: no featured field remnants');

assert(
  !existsSync(join(root, 'src/components/FloatingChat.astro')),
  'FloatingChat.astro should be removed (Tidio is active chat)',
);

assert(existsSync(join(root, 'public/og/origenlab-og.svg')), 'Missing default OG image');
assert(layoutSrc.includes('property="og:image"'), 'Layout.astro: missing og:image');
assert(layoutSrc.includes('twitter:card'), 'Layout.astro: missing twitter card');
assert(layoutSrc.includes('ogImageUrl'), 'Layout.astro: og image should use absolute site URL');

assert(
  !existsSync(join(root, 'public/brands/serva-wordmark.svg')),
  'serva-wordmark.svg removed; use serva-logo.png',
);

for (const slug of REMOVED_SLUGS) {
  assert(!productsSrc.includes(`slug: '${slug}'`), `products.ts: removed product still present: ${slug}`);
  assert(!sitemapSrc.includes(`/centrifugas/${slug}/`), `sitemap: removed route ${slug}`);
  assert(!sitemapSrc.includes(slug), `sitemap: removed slug ${slug}`);
}

const pageSources = walkAstro(join(root, 'src/pages')).map((p) => readFileSync(p, 'utf8')).join('\n');
for (const slug of REMOVED_SLUGS) {
  assert(!pageSources.includes(slug), `pages: public route/data for removed ${slug}`);
}

const slugMatches = [...productsSrc.matchAll(/slug: '([^']+)'/g)].map((m) => m[1]);
const slugCounts = new Map();
for (const slug of slugMatches) {
  slugCounts.set(slug, (slugCounts.get(slug) ?? 0) + 1);
}
for (const [slug, count] of slugCounts) {
  if (count > 1) {
    assert(false, `Duplicate slug in products.ts: ${slug}`);
  }
}

for (const slug of CANONICAL_ORTO_ORDER) {
  assert(productsSrc.includes(`slug: '${slug}'`), `products.ts: missing active product ${slug}`);
  assert(sitemapSrc.includes(`/productos/centrifugas/${slug}/`), `sitemap: missing ${slug}`);
}

const familiesOrderMatch = familiesSrc.match(
  /ortoalresaCentrifugeSlugs\s*=\s*\[([\s\S]*?)\]\s*as const/,
);
assert(familiesOrderMatch, 'productFamilies.ts: ortoalresaCentrifugeSlugs not found');
for (const slug of CANONICAL_ORTO_ORDER) {
  assert(
    familiesOrderMatch[1].includes(`'${slug}'`),
    `productFamilies.ts: canonical order missing ${slug}`,
  );
}
assert(
  !familiesSrc.includes('ortoalresaHomeShowcaseSlugs'),
  'productFamilies.ts: remove duplicate home slug list; use ortoalresaCentrifugeSlugs only',
);

function blockForSlug(src, slug) {
  const marker = `slug: '${slug}'`;
  const idx = src.indexOf(marker);
  if (idx < 0) return '';
  const start = src.lastIndexOf('\n  {', idx);
  const end = src.indexOf('\n  },', idx);
  return src.slice(start, end);
}

const requiredFields = [
  'manufacturerUrl:',
  'datasheetUrl:',
  'imagePath:',
  'availabilityNote:',
  'commercialNote:',
  'productFamilySlug:',
];

for (const slug of CANONICAL_ORTO_ORDER) {
  const block = blockForSlug(productsSrc, slug);
  assert(block.length > 0, `Could not parse product block for ${slug}`);
  for (const field of requiredFields) {
    assert(block.includes(field), `${slug}: missing ${field}`);
  }
  assert(
    block.includes("ctaText: 'Solicitar cotización'"),
    `${slug}: ctaText should be Solicitar cotización`,
  );

  const imageMatch = block.match(/imagePath: '([^']+)'/);
  const datasheetMatch = block.match(/datasheetUrl: '([^']+)'/);
  const manufacturerMatch = block.match(/manufacturerUrl: '([^']+)'/);
  assert(imageMatch, `${slug}: imagePath parse failed`);
  assert(datasheetMatch?.[1].startsWith('https://'), `${slug}: datasheetUrl must be https`);
  assert(manufacturerMatch?.[1].startsWith('https://'), `${slug}: manufacturerUrl must be https`);
  const publicImage = `public${imageMatch[1]}`;
  assert(existsSync(join(root, publicImage)), `${slug}: missing image ${publicImage}`);
  assert(
    imageMatch[1] === `/products/ortoalresa/${slug}.avif`,
    `${slug}: imagePath must match product slug`,
  );
}

for (const brandId of brandIds) {
  assert(
    productsSrc.includes(`brandId: '${brandId}'`),
    `products.ts: no products for brand ${brandId}`,
  );
}

const productBrandIds = [...productsSrc.matchAll(/brandId: '([^']+)'/g)].map((m) => m[1]);
for (const brandId of productBrandIds) {
  assert(brandIds.includes(brandId), `products.ts: unknown brandId ${brandId}`);
}

for (const rel of ['public/brands/ortoalresa-logo.svg', 'public/brands/serva-logo.png', ...ACTIVE_ORTO_ASSETS]) {
  assert(existsSync(join(root, rel)), `Missing asset: ${rel}`);
}

assert(
  existsSync(join(root, 'public/products/ortoalresa/bioprocen-22-r.avif')),
  'bioprocen asset archived on disk (do not delete without approval)',
);

assert(
  productsSrc.includes('buildWhatsAppQuoteUrl') === false,
  'sanity: products.ts should not import whatsapp helper',
);
assert(existsSync(join(root, 'src/lib/whatsapp.ts')), 'Missing src/lib/whatsapp.ts');
assert(
  contactSrc.includes('buildWhatsAppQuoteUrl'),
  'contact.ts: whatsappUrl should delegate to buildWhatsAppQuoteUrl',
);

const showcaseSrc = readFileSync(join(root, 'src/lib/productShowcase.ts'), 'utf8');
for (const slug of CANONICAL_ORTO_ORDER) {
  assert(
    showcaseSrc.includes(`'${slug}':`),
    `productShowcase.ts: missing home showcase copy for ${slug}`,
  );
}
assert(
  !existsSync(join(root, 'src/components/ProductScrollRow.astro')),
  'ProductScrollRow.astro should be removed (static showcase)',
);
assert(
  existsSync(join(root, 'src/components/BrandSkuCard.astro')),
  'BrandSkuCard.astro expected for SERVA SKU cards without detail pages',
);

const homeCommercialSrc = readFileSync(
  join(root, 'src/components/HomeCommercialLines.astro'),
  'utf8',
);
const indexSrc = readFileSync(join(root, 'src/pages/index.astro'), 'utf8');
assert(
  existsSync(join(root, 'src/components/HomeProductImagePreview.astro')),
  'HomeProductImagePreview.astro expected for compact Ortoalresa tiles on home',
);
assert(
  homeCommercialSrc.includes('HomeProductImagePreview'),
  'HomeCommercialLines should render HomeProductImagePreview',
);
const homePreviewLib = readFileSync(join(root, 'src/lib/homeProductPreview.ts'), 'utf8');
assert(
  homePreviewLib.includes("HOME_HERO_FEATURED_SLUG = 'biocen-22'"),
  'homeProductPreview: hero featured centrifuge is Biocen 22',
);
assert(
  homePreviewLib.includes('digicen-22-r'),
  'homeProductPreview: featured centrifuge slug for commercial card',
);
const homePreviewSrc = readFileSync(join(root, 'src/components/HomeProductImagePreview.astro'), 'utf8');
assert(
  !homePreviewSrc.includes('truncate') && !homePreviewSrc.includes('line-clamp'),
  'HomeProductImagePreview: product names must not be truncated',
);
assert(
  (homePreviewSrc.match(/role="list"/g) ?? []).length >= 1,
  'HomeProductImagePreview: supporting models as list rows',
);
assert(
  CANONICAL_ORTO_ORDER.length === 5,
  'expected 5 Ortoalresa centrifuges on home preview',
);
assert(indexSrc.includes('HomeHero'), 'homepage should use HomeHero');
assert(indexSrc.includes('HomeCategoryCards'), 'homepage should use HomeCategoryCards');
assert(indexSrc.includes('HomeProcess'), 'homepage should use HomeProcess');
assert(indexSrc.includes('HomeFinalCTA'), 'homepage should use HomeFinalCTA');
assert(!indexSrc.includes('HomeBrandsSection'), 'homepage must not duplicate HomeBrandsSection');
assert(!indexSrc.includes('ProductShowcaseGrid'), 'homepage must not use ProductShowcaseGrid');
assert(!indexSrc.includes('ProductComparisonStrip'), 'homepage must not use ProductComparisonStrip');

const servaBlocks = [...productsSrc.matchAll(/brandId: 'serva'[\s\S]*?slug: '([^']+)'/g)];
for (const match of servaBlocks) {
  const slug = match[1];
  const block = blockForSlug(productsSrc, slug);
  assert(
    !block.includes('productFamilySlug:'),
    `SERVA ${slug}: must not have productFamilySlug until detail pages exist`,
  );
}

if (failed) process.exit(1);
console.log('Catalog validation OK');
