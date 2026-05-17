/**
 * Canvas renderer for OrigenThreeBodyCanvas.
 * Header uses transparentBg + HEADER_PROFILE colours (see visualProfile.ts).
 */

import { getSimHistoryForCanvas } from './markGeometry';
import { getBodyXY, type History } from './threeBodySim';
import { trailStyleForSolution, tokensForVariant, type LogoVariant } from './variants';
import { getVisualProfile, type CanvasVisualProfile } from './visualProfile';
import type { MarkSolution } from './markGeometry';
import type { MotionContext } from './motionPresets';
import { ATOM_RING_RX, ATOM_RING_RY, canvasWorldScale } from './composition';

const BODIES = 3;
const RING_RX = ATOM_RING_RX;
const RING_RY = ATOM_RING_RY;

interface CanvasOpts {
  loopSeconds: number;
  trailLength: number;
  showRings: boolean;
  showWordmark: boolean;
  solution: MarkSolution;
  variant: LogoVariant;
  motionContext?: MotionContext;
}

function parseOpts(el: HTMLCanvasElement): CanvasOpts {
  const ctx = el.dataset.motionContext as MotionContext | undefined;
  return {
    loopSeconds: Number(el.dataset.loopSeconds) || 14,
    trailLength: Number(el.dataset.trailLength) || 210,
    showRings: el.dataset.showRings !== 'false',
    showWordmark: el.dataset.showWordmark === 'true',
    solution: (el.dataset.solution as MarkSolution) || 'premium',
    variant: (el.dataset.variant as LogoVariant) || 'dark',
    motionContext: ctx && ctx.length > 0 ? ctx : undefined,
  };
}

function hexRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ];
}

function drawAtomRing(
  ctx: CanvasRenderingContext2D,
  angleDeg: number,
  color: string,
  alpha: number,
  linePx: number,
  scale: number,
) {
  ctx.save();
  ctx.rotate((angleDeg * Math.PI) / 180);
  ctx.beginPath();
  ctx.ellipse(0, 0, RING_RX, RING_RY, 0, 0, Math.PI * 2);
  ctx.strokeStyle = color;
  ctx.globalAlpha = alpha;
  ctx.lineWidth = linePx / scale;
  ctx.lineCap = 'round';
  ctx.stroke();
  ctx.restore();
}

function drawTrail(
  ctx: CanvasRenderingContext2D,
  points: [number, number][],
  coreColor: string,
  glowColor: string,
  gapPattern: number,
  keep: number,
  scale: number,
  visual: CanvasVisualProfile,
) {
  if (points.length < 2) return;
  const [cr, cg, cb] = hexRgb(coreColor);
  const [gr, gg, gb] = hexRgb(glowColor);
  const n = points.length - 1;

  for (let pass = 0; pass < 2; pass++) {
    const isGlow = pass === 0;
    const [r, g, b] = isGlow ? [gr, gg, gb] : [cr, cg, cb];
    const mul = isGlow ? visual.trailGlowMul : visual.trailCoreMul;
    for (let i = 0; i < n; i++) {
      if (i % gapPattern >= keep) continue;
      const t = (i + 1) / n;
      const tailBoost = t > 0.72 ? 1.15 : 1;
      const alpha = isGlow
        ? 0.18 * (0.35 + 0.65 * t) * tailBoost * mul
        : (0.12 + 0.78 * t) * tailBoost * mul;
      ctx.beginPath();
      ctx.moveTo(points[i][0], points[i][1]);
      ctx.lineTo(points[i + 1][0], points[i + 1][1]);
      ctx.strokeStyle = `rgba(${r},${g},${b},${Math.min(alpha, 0.9)})`;
      ctx.lineWidth = (isGlow ? 6 : 2.2) / scale;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.stroke();
    }
  }
}

function drawBody(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  coreColor: string,
  glowColor: string,
  scale: number,
  radiusScale: number,
  visual: CanvasVisualProfile,
) {
  const [gr, gg, gb] = hexRgb(glowColor);
  const br = 0.058 * radiusScale;
  const gMul = visual.bodyGlowAlphaMul;

  if (!visual.compactBodies) {
    ctx.beginPath();
    ctx.arc(x, y, br * 4.2, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${gr},${gg},${gb},${Math.min(0.28 * gMul, 0.55)})`;
    ctx.fill();
  }

  ctx.beginPath();
  ctx.arc(x, y, br * (visual.compactBodies ? 2.2 : 2.5), 0, Math.PI * 2);
  ctx.fillStyle = `rgba(${gr},${gg},${gb},${Math.min(0.38 * gMul, 0.5)})`;
  ctx.fill();

  ctx.beginPath();
  ctx.arc(x, y, br * 1.12, 0, Math.PI * 2);
  ctx.fillStyle = coreColor;
  ctx.globalAlpha = 1;
  ctx.fill();
  if (!visual.compactBodies) {
    ctx.strokeStyle = visual.bodyCoreStroke;
    ctx.lineWidth = 0.4 / scale;
    ctx.stroke();
  }
}

function renderFrame(
  ctx: CanvasRenderingContext2D,
  history: History,
  frameIdx: number,
  frameIndices: number[],
  opts: CanvasOpts,
  tokens: ReturnType<typeof tokensForVariant>,
  trail: ReturnType<typeof trailStyleForSolution>,
  visual: CanvasVisualProfile,
  w: number,
  h: number,
) {
  const size = Math.min(w, h);
  const scale = canvasWorldScale(size);
  const idx = frameIndices[frameIdx % frameIndices.length];
  const radiusScale = Math.max(size / 320, 0.85);

  if (visual.transparentBg) {
    ctx.clearRect(0, 0, w, h);
  } else {
    ctx.fillStyle = tokens.bg;
    ctx.fillRect(0, 0, w, h);
  }

  ctx.save();
  ctx.translate(w / 2, h / 2);
  ctx.scale(scale, -scale);

  if (opts.showRings && trail.showRings) {
    const angles =
      opts.solution === 'trace' ? [0, 60, -60] : opts.solution === 'minimal' ? [] : [0, 60, -60];
    for (const ang of angles) {
      drawAtomRing(ctx, ang, visual.ringColor, visual.ringAlpha, visual.ringLinePx, scale);
    }
  }

  const nr = 0.17;

  ctx.beginPath();
  ctx.arc(0, 0, nr * 1.55, 0, Math.PI * 2);
  ctx.strokeStyle = visual.nucleusRingColor;
  ctx.globalAlpha = visual.nucleusRingAlpha;
  ctx.lineWidth = 0.9 / scale;
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(0, 0, nr, 0, Math.PI * 2);
  ctx.fillStyle = visual.nucleusFill;
  ctx.globalAlpha = 1;
  ctx.fill();

  for (let b = 0; b < BODIES; b++) {
    const tail: [number, number][] = [];
    const start = Math.max(0, idx - opts.trailLength);
    for (let s = start; s <= idx; s++) {
      tail.push(getBodyXY(history, s, b));
    }
    drawTrail(
      ctx,
      tail,
      visual.bodyCoreColors[b],
      visual.bodyGlowColors[b],
      trail.gapPattern,
      trail.keep,
      scale,
      visual,
    );
  }

  for (let b = 0; b < BODIES; b++) {
    const [x, y] = getBodyXY(history, idx, b);
    drawBody(
      ctx,
      x,
      y,
      visual.bodyCoreColors[b],
      visual.bodyGlowColors[b],
      scale,
      radiusScale,
      visual,
    );
  }

  ctx.restore();

  if (opts.showWordmark) {
    ctx.save();
    ctx.fillStyle = tokens.wordmark;
    ctx.font = `bold ${size * 0.11}px "Plus Jakarta Sans", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('OrigenLab', w / 2, h * 0.88);
    ctx.restore();
  }
}

function attachCanvas(canvas: HTMLCanvasElement) {
  if (canvas.dataset.origenInitialized === 'true') return () => {};
  canvas.dataset.origenInitialized = 'true';

  const opts = parseOpts(canvas);
  const trail = trailStyleForSolution(opts.solution);
  const tokens = tokensForVariant(opts.variant);
  const visual = getVisualProfile(opts.motionContext);
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if (reducedMotion) return () => {};

  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(Math.round(rect.width), 64);
  const h = Math.max(Math.round(rect.height), 64);
  canvas.width = w * dpr;
  canvas.height = h * dpr;

  const ctx = canvas.getContext('2d');
  if (!ctx) return () => {};

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const { history, frameIndices } = getSimHistoryForCanvas(opts.loopSeconds, 30);
  const fps = 30;
  const frameMs = 1000 / fps;
  let frame = 0;
  let last = 0;
  let raf = 0;
  let visible = true;
  let running = true;

  const draw = (fi: number) =>
    renderFrame(ctx, history, fi, frameIndices, opts, tokens, trail, visual, w, h);

  draw(0);

  const tick = (now: number) => {
    if (!running) return;
    if (!visible) {
      raf = requestAnimationFrame(tick);
      return;
    }
    if (now - last >= frameMs) {
      last = now;
      frame = (frame + 1) % frameIndices.length;
      draw(frame);
    }
    raf = requestAnimationFrame(tick);
  };

  raf = requestAnimationFrame(tick);

  const observer = new IntersectionObserver(
    (entries) => {
      visible = entries[0]?.isIntersecting ?? true;
    },
    { threshold: 0.05 },
  );
  observer.observe(canvas);

  return () => {
    running = false;
    cancelAnimationFrame(raf);
    observer.disconnect();
  };
}

export function initThreeBodyCanvases() {
  const cleanups: (() => void)[] = [];
  document.querySelectorAll<HTMLCanvasElement>('canvas[data-origen-three-body]').forEach((el) => {
    cleanups.push(attachCanvas(el));
  });
  return () => cleanups.forEach((fn) => fn());
}
