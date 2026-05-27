/**
 * Export Gmail signature PNGs from public/email/*.svg
 * Run: node scripts/export-email-signature-assets.mjs
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { Resvg } from '@resvg/resvg-js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const emailDir = join(root, 'public', 'email');

function md5(filePath) {
  return createHash('md5').update(readFileSync(filePath)).digest('hex').slice(0, 8);
}

function exportPng(svgName, pngName, width) {
  const svgPath = join(emailDir, svgName);
  const pngPath = join(emailDir, pngName);
  const svg = readFileSync(svgPath, 'utf8');
  const resvg = new Resvg(svg, { fitTo: { mode: 'width', value: width } });
  const png = resvg.render().asPng();
  writeFileSync(pngPath, png);
  console.log(`  ${pngName} @ ${width}px  md5=${md5(pngPath)}  (${png.length} bytes)`);
}

console.log('Exporting email signature assets...');

exportPng('origenlab-signature-mark.svg', 'origenlab-signature-mark-v3.png', 96);
exportPng('origenlab-signature-mark.svg', 'origenlab-signature-mark-v3@2x.png', 192);
exportPng('origenlab-signature-mark.svg', 'origenlab-signature-mark.png', 96);
// Gmail PNG (intrinsic 56x56 — legible al pegar; v3 sigue 96px para alta res)
exportPng('origenlab-signature-mark.svg', 'origenlab-signature-mark-SMALL.png', 56);

try {
  exportPng('origenlab-signature-lockup.svg', 'origenlab-signature-lockup.png', 480);
  exportPng('origenlab-signature-lockup.svg', 'origenlab-signature-lockup@2x.png', 960);
} catch {
  console.log('  (skipped lockup - SVG missing)');
}

const v2 = join(emailDir, 'origenlab-signature-mark-v2.png');
const v3 = join(emailDir, 'origenlab-signature-mark-v3.png');
if (existsSync(v2) && existsSync(v3)) {
  const same = md5(v2) === md5(v3);
  console.log(same ? '  WARNING: v2 and v3 PNG hashes match' : '  OK: v2 vs v3 PNG differ');
}

console.log('Done. HTML should reference origenlab-signature-mark-v3.png at 48x48 display.');
