/**
 * Normalize partner logos and build origenlab-brand-strip.png for Gmail signatures.
 * Run: node scripts/build-email-brand-strip.mjs
 *
 * Export 820x68 @2x → display 410x34 in HTML. Logo max height ~19-21px at display.
 */
import { readFileSync, existsSync, copyFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';
import { Resvg } from '@resvg/resvg-js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const brandsDir = join(root, 'public', 'email', 'brands');
const emailDir = join(root, 'public', 'email');

const STRIP_EXPORT_WIDTH = 820;
const STRIP_EXPORT_HEIGHT = 68;
const STRIP_DISPLAY_WIDTH = 410;
const STRIP_DISPLAY_HEIGHT = 34;
const GAP = 28;
const PAD_X = 16;

/** Per-brand strip sizing @2x export (height-first; CRTOP width-capped) */
const BRANDS = [
  {
    key: 'serva',
    source: 'serva-source.png',
    fromWeb: join(root, 'public/brands/serva-logo.png'),
    stripHeight: 40,
    stripMaxWidth: 124,
  },
  {
    key: 'ortoalresa',
    source: 'ortoalresa-source.svg',
    svg: true,
    stripHeight: 40,
    stripMaxWidth: 108,
  },
  {
    key: 'ika',
    source: 'ika-source.png',
    stripHeight: 38,
    stripMaxWidth: 92,
  },
  {
    key: 'crtop',
    source: 'crtop-source.jpg',
    stripHeight: 38,
    stripMaxWidth: 84,
  },
  {
    key: 'ollital',
    source: 'ollital-source.jpeg',
    stripHeight: 40,
    stripMaxWidth: 118,
  },
  {
    key: 'hielscher',
    source: 'hielscher-source.svg',
    svg: true,
    stripHeight: 42,
    stripMaxWidth: 112,
  },
];

function loadInputBuffer(entry) {
  if (entry.fromWeb && existsSync(entry.fromWeb)) {
    copyFileSync(entry.fromWeb, join(brandsDir, entry.source));
  }
  const path = join(brandsDir, entry.source);
  if (!existsSync(path)) {
    throw new Error(`Missing source: ${path}`);
  }
  if (entry.svg) {
    return new Resvg(readFileSync(path, 'utf8'), {
      fitTo: { mode: 'width', value: 320 },
    }).render().asPng();
  }
  return readFileSync(path);
}

async function normalizeLogo(entry) {
  const out = join(brandsDir, `${entry.key}-logo.png`);
  let input = loadInputBuffer(entry);

  if (entry.key === 'crtop') {
    input = await sharp(input).trim({ threshold: 12 }).toBuffer();
    const m = await sharp(input).metadata();
    if (m.width / m.height > 2.8) {
      const cropW = Math.min(m.width, Math.round(m.height * 2.4));
      const left = Math.floor((m.width - cropW) / 2);
      input = await sharp(input)
        .extract({ left, top: 0, width: cropW, height: m.height })
        .toBuffer();
    }
  }

  await sharp(input)
    .flatten({ background: '#ffffff' })
    .resize({ height: 56, fit: 'inside' })
    .grayscale()
    .linear(1.45, -42)
    .modulate({ brightness: 0.88 })
    .png()
    .toFile(out);
  const meta = await sharp(out).metadata();
  console.log(`  ${entry.key}-logo.png  ${meta.width}x${meta.height}`);
  return { path: out, entry };
}

async function buildStrip(items) {
  const logos = await Promise.all(
    items.map(async ({ path, entry }) => {
      let buffer = await sharp(path)
        .resize({ height: entry.stripHeight, fit: 'inside' })
        .png()
        .toBuffer();
      let m = await sharp(buffer).metadata();
      if (m.width > entry.stripMaxWidth) {
        buffer = await sharp(buffer)
          .resize({ width: entry.stripMaxWidth, fit: 'inside' })
          .png()
          .toBuffer();
        m = await sharp(buffer).metadata();
      }
      return { buffer, width: m.width, height: m.height, key: entry.key };
    }),
  );

  const totalLogoWidth = logos.reduce((s, l) => s + l.width, 0);
  const totalGaps = GAP * (logos.length - 1);
  const contentWidth = totalLogoWidth + totalGaps + PAD_X * 2;
  const stripWidth = Math.max(STRIP_EXPORT_WIDTH, contentWidth);

  let x = Math.floor((stripWidth - contentWidth) / 2) + PAD_X;
  const composites = logos.map((logo) => {
    const top = Math.floor((STRIP_EXPORT_HEIGHT - logo.height) / 2);
    const left = x;
    x += logo.width + GAP;
    return { input: logo.buffer, left, top };
  });

  const stripPath = join(emailDir, 'origenlab-brand-strip.png');
  await sharp({
    create: {
      width: stripWidth,
      height: STRIP_EXPORT_HEIGHT,
      channels: 4,
      background: { r: 255, g: 255, b: 255, alpha: 0 },
    },
  })
    .composite(composites)
    .png()
    .toFile(stripPath);

  console.log(
    `  origenlab-brand-strip.png  ${stripWidth}x${STRIP_EXPORT_HEIGHT}  (display ${STRIP_DISPLAY_WIDTH}x${STRIP_DISPLAY_HEIGHT})`,
  );
  for (const l of logos) {
    console.log(`    ${l.key}: ${l.width}x${l.height} (@2x → ~${Math.round(l.height / 2)}px display)`);
  }
}

console.log('Normalizing brand logos...');
const items = [];
for (const brand of BRANDS) {
  try {
    items.push(await normalizeLogo(brand));
  } catch (e) {
    console.error(`  SKIP ${brand.key}: ${e.message}`);
  }
}
console.log('Building strip...');
await buildStrip(items);
console.log('Done.');
