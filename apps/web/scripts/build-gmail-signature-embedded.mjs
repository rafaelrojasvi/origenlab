/**
 * Build Gmail paste HTML with embedded PNGs (atom + brand strip).
 * Run: node scripts/build-gmail-signature-embedded.mjs
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const emailDir = join(root, 'public', 'email');

function dataUri(pngName) {
  const b64 = readFileSync(join(emailDir, pngName)).toString('base64');
  return `data:image/png;base64,${b64}`;
}

const markUri = dataUri('origenlab-signature-mark-SMALL.png');
const stripUri = dataUri('origenlab-brand-strip.png');

let html = readFileSync(
  join(emailDir, 'origenlab-contacto-signature-SMALL-paste.html'),
  'utf8',
);
html = html.replace(
  /<img src="origenlab-signature-mark-SMALL\.png"[^>]*\/>/,
  `<img src="${markUri}" width="56" height="56" alt="OrigenLab" style="display:block;width:56px;height:56px;max-width:56px;border:0;" />`,
);
html = html.replace(
  /<img src="origenlab-brand-strip\.png"[^>]*\/>/,
  `<img src="${stripUri}" width="410" height="34" alt="SERVA, Ortoalresa, IKA, CRTOP, Ollital, Hielscher" style="display:block;width:410px;height:34px;max-width:100%;border:0;" />`,
);

const box = html.match(/<div style="background: #ffffff[\s\S]*<\/div>/)[0];
const out = `<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8" /><title>OrigenLab firma Gmail (embebida)</title></head>
<body style="margin:24px;background:#f1f5f9;font-family:Arial,sans-serif">
<p style="font-size:13px;color:#64748b;max-width:520px;line-height:1.5">
  Copia <strong>solo el recuadro blanco</strong> y pegalo en Gmail → Firma → Guardar.
</p>
${box}
</body>
</html>`;

writeFileSync(join(emailDir, 'origenlab-contacto-signature-SMALL-embedded.html'), out);
console.log('Wrote origenlab-contacto-signature-SMALL-embedded.html');
