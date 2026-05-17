/**
 * Generates public/logo/*.svg from figure-eight three-body simulation.
 * Run: node scripts/generate-logo-svgs.mjs
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = join(__dirname, '../public/logo');

const PALETTE = {
  brand100: '#ccfbf1',
  brand200: '#99f6e4',
  brand300: '#5eead4',
  brand400: '#2dd4bf',
  brand500: '#14b8a6',
  brand600: '#0d9488',
  brand700: '#0f766e',
  brand900: '#134e4a',
  brand950: '#042f2e',
  white: '#ffffff',
};

const BODY = [PALETTE.brand200, PALETTE.brand300, PALETTE.brand400];

function simulate(steps = 12000, dt = 0.0035, eps = 0.02) {
  const pos = [
    [0.97000436, -0.24308753],
    [-0.97000436, 0.24308753],
    [0, 0],
  ];
  const vel = [
    [0.466203685, 0.43236573],
    [0.466203685, 0.43236573],
    [-0.93240737, -0.86473146],
  ];
  const hist = [];

  function acc() {
    const a = [
      [0, 0],
      [0, 0],
      [0, 0],
    ];
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) {
        if (i === j) continue;
        const dx = pos[j][0] - pos[i][0];
        const dy = pos[j][1] - pos[i][1];
        const d2 = dx * dx + dy * dy + eps * eps;
        const f = 1 / d2 ** 1.5;
        a[i][0] += dx * f;
        a[i][1] += dy * f;
      }
    }
    return a;
  }

  let a = acc();
  for (let s = 0; s < steps; s++) {
    hist.push(pos.map((p) => [p[0], p[1]]));
    for (let i = 0; i < 3; i++) {
      pos[i][0] += vel[i][0] * dt + 0.5 * a[i][0] * dt * dt;
      pos[i][1] += vel[i][1] * dt + 0.5 * a[i][1] * dt * dt;
    }
    const newA = acc();
    for (let i = 0; i < 3; i++) {
      vel[i][0] += 0.5 * (a[i][0] + newA[i][0]) * dt;
      vel[i][1] += 0.5 * (a[i][1] + newA[i][1]) * dt;
    }
    a = newA;
  }
  return hist;
}

function normalize(hist) {
  let cx = 0,
    cy = 0;
  const n = hist.length * 3;
  for (const frame of hist) {
    for (const [x, y] of frame) {
      cx += x;
      cy += y;
    }
  }
  cx /= n;
  cy /= n;
  let maxR = 0;
  const centered = hist.map((frame) =>
    frame.map(([x, y]) => {
      const px = x - cx;
      const py = y - cy;
      maxR = Math.max(maxR, Math.hypot(px, py));
      return [px, py];
    }),
  );
  const sc = 2.15 / maxR;
  const rad = (-18 * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  return centered.map((frame) =>
    frame.map(([x, y]) => {
      const sx = x * sc;
      const sy = y * sc;
      return [sx * cos - sy * sin, sx * sin + sy * cos];
    }),
  );
}

function findLoopEnd(hist) {
  const ref = hist[0].flat();
  let best = 400;
  let bestErr = Infinity;
  for (let i = 400; i < hist.length; i++) {
    const flat = hist[i].flat();
    let err = 0;
    for (let k = 0; k < flat.length; k++) {
      const d = flat[k] - ref[k];
      err += d * d;
    }
    err = Math.sqrt(err);
    if (err < bestErr) {
      bestErr = err;
      best = i;
    }
  }
  return best + 1;
}

function pathFor(hist, body, end, maxPts = 40) {
  const stride = Math.max(1, Math.floor(end / maxPts));
  const pts = [];
  for (let s = 0; s < end; s += stride) pts.push(hist[s][body]);
  const last = hist[end - 1][body];
  if (pts[pts.length - 1][0] !== last[0] || pts[pts.length - 1][1] !== last[1]) pts.push(last);
  return 'M ' + pts.map(([x, y]) => `${x.toFixed(3)} ${y.toFixed(3)}`).join(' L ');
}

function buildSvg(tokens, hist, paths, rings, bodyR = 0.085) {
  const end = findLoopEnd(hist);
  const mid = hist[Math.floor(end * 0.35)];
  const ringEls = rings
    .map(
      ([rx, ry, ang]) =>
        `<ellipse cx="0" cy="0" rx="${(rx * 0.72).toFixed(2)}" ry="${(ry * 0.72).toFixed(2)}" transform="rotate(${ang})" fill="none" stroke="${tokens.ring}" stroke-width="0.06" opacity="0.1"/>`,
    )
    .join('\n  ');
  const trails = paths
    .map(
      (d, i) =>
        `<path d="${d}" fill="none" stroke="${BODY[i]}" stroke-width="0.12" stroke-linecap="round" opacity="${(0.85 - i * 0.08).toFixed(2)}"/>`,
    )
    .join('\n  ');
  const dots = mid
    .map(
      ([x, y], i) =>
        `<circle cx="${x.toFixed(3)}" cy="${y.toFixed(3)}" r="${bodyR}" fill="${BODY[i]}"/>`,
    )
    .join('\n  ');
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="-3.5 -3.5 7 7" width="512" height="512">
  <rect width="7" height="7" x="-3.5" y="-3.5" fill="${tokens.bg}"/>
  ${ringEls}
  ${trails}
  <circle cx="0" cy="0" r="0.32" fill="none" stroke="${tokens.nucleusRing}" stroke-width="0.05" opacity="0.2"/>
  <circle cx="0" cy="0" r="0.18" fill="${tokens.nucleus}"/>
  ${dots}
</svg>`;
}

const hist = normalize(simulate());
const end = findLoopEnd(hist);
const paths = [0, 1, 2].map((b) => pathFor(hist, b, end));
const fullRings = [
  [4.6, 1.55, 0],
  [4.6, 1.55, 60],
  [4.6, 1.55, -60],
];
const oneRing = [[4.6, 1.55, 0]];

mkdirSync(outDir, { recursive: true });

const dark = {
  bg: PALETTE.brand950,
  ring: PALETTE.brand700,
  nucleus: PALETTE.brand100,
  nucleusRing: PALETTE.brand400,
};
const light = {
  bg: PALETTE.white,
  ring: PALETTE.brand600,
  nucleus: PALETTE.brand900,
  nucleusRing: PALETTE.brand500,
};

writeFileSync(join(outDir, 'origenlab-mark-dark.svg'), buildSvg(dark, hist, paths, fullRings));
writeFileSync(join(outDir, 'origenlab-mark-light.svg'), buildSvg(light, hist, paths, fullRings));
writeFileSync(join(outDir, 'origenlab-mark-static.svg'), buildSvg(dark, hist, paths, fullRings));
writeFileSync(
  join(outDir, 'origenlab-favicon-candidate.svg'),
  buildSvg(dark, hist, paths, oneRing, 0.11),
);

console.log('Wrote SVG candidates to public/logo/ (favicon.svg is managed separately)');
