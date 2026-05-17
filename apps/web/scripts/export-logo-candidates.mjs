/**
 * Generates candidate SVGs under public/logo/ from the same three-body sim as the app.
 * Run: node scripts/export-logo-candidates.mjs
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = join(__dirname, '../public/logo');

const PALETTE = {
  brand50: '#f0fdfa',
  brand100: '#ccfbf1',
  brand200: '#99f6e4',
  brand300: '#5eead4',
  brand400: '#2dd4bf',
  brand600: '#0d9488',
  brand700: '#0f766e',
  brand900: '#134e4a',
  brand950: '#042f2e',
  white: '#ffffff',
};

const BODY = [PALETTE.brand200, PALETTE.brand300, PALETTE.brand400];
const BODIES = 3;

function acceleration(positions, masses, g, eps) {
  const acc = new Float64Array(BODIES * 2);
  for (let i = 0; i < BODIES; i++) {
    for (let j = 0; j < BODIES; j++) {
      if (i === j) continue;
      const dx = positions[j * 2] - positions[i * 2];
      const dy = positions[j * 2 + 1] - positions[i * 2 + 1];
      const distSq = dx * dx + dy * dy + eps * eps;
      const inv = 1 / distSq ** 1.5;
      acc[i * 2] += g * masses[j] * dx * inv;
      acc[i * 2 + 1] += g * masses[j] * dy * inv;
    }
  }
  return acc;
}

function simulate(steps = 12000, dt = 0.0035, g = 1, eps = 0.02) {
  const positions = new Float64Array([
    0.97000436, -0.24308753, -0.97000436, 0.24308753, 0, 0,
  ]);
  const velocities = new Float64Array([
    0.466203685, 0.43236573, 0.466203685, 0.43236573, -0.93240737, -0.86473146,
  ]);
  const masses = new Float64Array([1, 1, 1]);
  const history = new Float64Array(steps * BODIES * 2);
  let acc = acceleration(positions, masses, g, eps);
  for (let s = 0; s < steps; s++) {
    const base = s * BODIES * 2;
    for (let i = 0; i < BODIES * 2; i++) history[base + i] = positions[i];
    for (let i = 0; i < BODIES * 2; i++) {
      positions[i] += velocities[i] * dt + 0.5 * acc[i] * dt * dt;
    }
    const newAcc = acceleration(positions, masses, g, eps);
    for (let i = 0; i < BODIES * 2; i++) {
      velocities[i] += 0.5 * (acc[i] + newAcc[i]) * dt;
    }
    acc = newAcc;
  }
  return history;
}

function normalize(history, targetRadius = 2.15) {
  const steps = history.length / (BODIES * 2);
  let cx = 0;
  let cy = 0;
  const n = steps * BODIES;
  for (let s = 0; s < steps; s++) {
    for (let b = 0; b < BODIES; b++) {
      const i = (s * BODIES + b) * 2;
      cx += history[i];
      cy += history[i + 1];
    }
  }
  cx /= n;
  cy /= n;
  let maxR = 0;
  const out = new Float64Array(history.length);
  for (let i = 0; i < history.length; i += 2) {
    const x = history[i] - cx;
    const y = history[i + 1] - cy;
    out[i] = x;
    out[i + 1] = y;
    maxR = Math.max(maxR, Math.hypot(x, y));
  }
  const scale = targetRadius / maxR;
  const rad = (-18 * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  for (let i = 0; i < out.length; i += 2) {
    const x = out[i] * scale;
    const y = out[i + 1] * scale;
    out[i] = x * cos - y * sin;
    out[i + 1] = x * sin + y * cos;
  }
  return out;
}

function findLoopEnd(history, minStep = 400) {
  const ref = history.slice(0, BODIES * 2);
  const steps = history.length / (BODIES * 2);
  let bestI = minStep;
  let bestErr = Infinity;
  for (let s = minStep; s < steps; s++) {
    const base = s * BODIES * 2;
    let err = 0;
    for (let i = 0; i < BODIES * 2; i++) {
      const d = history[base + i] - ref[i];
      err += d * d;
    }
    err = Math.sqrt(err);
    if (err < bestErr) {
      bestErr = err;
      bestI = s;
    }
  }
  return bestI + 1;
}

function samplePath(history, body, loopEnd, maxPts) {
  const pts = [];
  const stride = Math.max(1, Math.floor(loopEnd / maxPts));
  for (let s = 0; s < loopEnd; s += stride) {
    const i = (s * BODIES + body) * 2;
    pts.push([history[i], history[i + 1]]);
  }
  const li = (loopEnd - 1) * BODIES * 2 + body * 2;
  const last = [history[li], history[li + 1]];
  const p = pts[pts.length - 1];
  if (p[0] !== last[0] || p[1] !== last[1]) pts.push(last);
  return pts;
}

function pathD(points) {
  if (!points.length) return '';
  let d = `M ${points[0][0].toFixed(3)} ${points[0][1].toFixed(3)}`;
  for (let i = 1; i < points.length; i++) {
    d += ` L ${points[i][0].toFixed(3)} ${points[i][1].toFixed(3)}`;
  }
  return d;
}

function getXY(history, step, body) {
  const i = (step * BODIES + body) * 2;
  return [history[i], history[i + 1]];
}

function markSvg({ bg, ring, nucleus, nucleusRing, wordmark, solution }) {
  const loopEnd = findLoopEnd(history);
  const maxPts = solution === 'minimal' ? 24 : solution === 'trace' ? 56 : 40;
  const paths = [0, 1, 2].map((b) => pathD(samplePath(history, b, loopEnd, maxPts)));
  const mid = Math.floor(loopEnd * 0.35);
  const bodies = [0, 1, 2].map((b) => getXY(history, mid, b));
  const tw = solution === 'trace' ? 0.14 : solution === 'minimal' ? 0.1 : 0.12;
  const top = solution === 'trace' ? 0.92 : solution === 'minimal' ? 0.75 : 0.85;
  const br = solution === 'minimal' ? 0.11 : 0.085;

  const rings =
    solution === 'trace'
      ? [{ rx: 3.17, ry: 1.01, angle: 0, o: 0.08 }]
      : solution === 'minimal'
        ? []
        : [
            { rx: 3.31, ry: 1.12, angle: 0, o: 0.1 },
            { rx: 3.31, ry: 1.12, angle: 60, o: 0.09 },
            { rx: 3.31, ry: 1.12, angle: -60, o: 0.09 },
          ];

  const ringEls = rings
    .map(
      (r) =>
        `<ellipse cx="0" cy="0" rx="${r.rx}" ry="${r.ry}" transform="rotate(${r.angle})" fill="none" stroke="${ring}" stroke-width="0.06" opacity="${r.o}"/>`,
    )
    .join('\n  ');

  const trailEls = paths
    .map(
      (d, i) =>
        `<path d="${d}" fill="none" stroke="${BODY[i]}" stroke-width="${tw}" stroke-linecap="round" stroke-linejoin="round" opacity="${(top - i * 0.08).toFixed(2)}"/>`,
    )
    .join('\n  ');

  const bodyEls = bodies
    .map(
      ([x, y], i) =>
        `<circle cx="${x.toFixed(3)}" cy="${y.toFixed(3)}" r="${(br * 2.2).toFixed(3)}" fill="${BODY[i]}" opacity="0.28"/>
  <circle cx="${x.toFixed(3)}" cy="${y.toFixed(3)}" r="${br}" fill="${BODY[i]}"/>`,
    )
    .join('\n  ');

  const word = wordmark
    ? `<text x="0" y="2.85" text-anchor="middle" font-family="'Plus Jakarta Sans', system-ui, sans-serif" font-size="0.55" font-weight="700" fill="${wordmark}">OrigenLab</text>`
    : '';

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="-3.5 -3.5 7 7" role="img" aria-label="OrigenLab">
  <rect width="7" height="7" x="-3.5" y="-3.5" fill="${bg}"/>
  ${ringEls}
  ${trailEls}
  <circle cx="0" cy="0" r="0.32" fill="none" stroke="${nucleusRing}" stroke-width="0.05" opacity="0.2"/>
  <circle cx="0" cy="0" r="0.18" fill="${nucleus}"/>
  ${bodyEls}
  ${word}
</svg>`;
}

const history = normalize(simulate());
mkdirSync(outDir, { recursive: true });

const marks = {
  'origenlab-mark-premium.svg': markSvg({
    bg: PALETTE.brand950,
    ring: PALETTE.brand700,
    nucleus: PALETTE.brand100,
    nucleusRing: PALETTE.brand400,
    solution: 'premium',
  }),
  'origenlab-mark-trace.svg': markSvg({
    bg: PALETTE.brand950,
    ring: PALETTE.brand700,
    nucleus: PALETTE.brand100,
    nucleusRing: PALETTE.brand400,
    solution: 'trace',
  }),
  'origenlab-mark-minimal.svg': markSvg({
    bg: PALETTE.brand950,
    ring: PALETTE.brand700,
    nucleus: PALETTE.brand100,
    nucleusRing: PALETTE.brand400,
    solution: 'minimal',
  }),
};

for (const [name, svg] of Object.entries(marks)) {
  writeFileSync(join(outDir, name), svg, 'utf8');
  console.log('wrote', name);
}

writeFileSync(
  join(outDir, 'origenlab-lockup-dark.svg'),
  `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 48" role="img" aria-label="OrigenLab">
  <rect width="220" height="48" fill="${PALETTE.brand950}"/>
  <g transform="translate(8 6) scale(5.2)">
    ${marks['origenlab-mark-premium.svg']
      .replace(/<\?xml[^>]*>\s*/, '')
      .replace(/<svg[^>]*>/, '')
      .replace(/<rect[^/]*\/>/, '')
      .replace(/<\/svg>/, '')}
  </g>
  <text x="62" y="30" font-family="'Plus Jakarta Sans', system-ui, sans-serif" font-size="18" font-weight="700" fill="${PALETTE.brand100}">OrigenLab</text>
</svg>`,
  'utf8',
);

writeFileSync(
  join(outDir, 'origenlab-lockup-light.svg'),
  `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 48" role="img" aria-label="OrigenLab">
  <rect width="220" height="48" fill="${PALETTE.white}"/>
  <g transform="translate(8 6) scale(5.2)">
    ${marks['origenlab-mark-premium.svg']
      .replace(/<\?xml[^>]*>\s*/, '')
      .replace(/<svg[^>]*>/, '')
      .replace(/<rect[^/]*\/>/, '')
      .replace(/#042f2e/g, PALETTE.white)
      .replace(/#ccfbf1/g, PALETTE.brand900)
      .replace(/<\/svg>/, '')}
  </g>
  <text x="62" y="30" font-family="'Plus Jakarta Sans', system-ui, sans-serif" font-size="18" font-weight="700" fill="${PALETTE.brand950}">OrigenLab</text>
</svg>`,
  'utf8',
);

writeFileSync(
  join(outDir, 'origenlab-favicon-candidate.svg'),
  marks['origenlab-mark-minimal.svg'].replace('viewBox="-3.5 -3.5 7 7"', 'viewBox="-2.2 -2.2 4.4 4.4"'),
  'utf8',
);

console.log('Done — public/logo/');
