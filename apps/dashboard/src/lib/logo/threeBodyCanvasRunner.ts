/**
 * Canvas draw loop for OrigenLab three-body logo (adapted from apps/web canvasAnimator.ts).
 */

import { ATOM_RING_RX, ATOM_RING_RY, canvasWorldScale } from "./composition";
import { getSimHistoryForCanvas } from "./markGeometry";
import { LOGO_PALETTE } from "./palette";
import { HEADER_TRAIL_STYLE } from "./trailStyle";
import { getBodyXY } from "./threeBodySim";
import { getVisualProfile } from "./visualProfile";

const BODIES = 3;
const RING_RX = ATOM_RING_RX;
const RING_RY = ATOM_RING_RY;

export interface ThreeBodyCanvasOptions {
  loopSeconds?: number;
  showRings?: boolean;
}

function hexRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
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
  ctx.lineCap = "round";
  ctx.stroke();
  ctx.restore();
}

function drawTrail(
  ctx: CanvasRenderingContext2D,
  points: [number, number][],
  coreColor: string,
  glowColor: string,
  scale: number,
  visual: ReturnType<typeof getVisualProfile>,
) {
  if (points.length < 2) return;
  const [cr, cg, cb] = hexRgb(coreColor);
  const [gr, gg, gb] = hexRgb(glowColor);
  const n = points.length - 1;
  const { gapPattern, keep } = HEADER_TRAIL_STYLE;

  for (let pass = 0; pass < 2; pass++) {
    const isGlow = pass === 0;
    const [r, g, b] = isGlow ? [gr, gg, gb] : [cr, cg, cb];
    const mul = isGlow ? visual.trailGlowMul : visual.trailCoreMul;
    for (let i = 0; i < n; i++) {
      if (i % gapPattern >= keep) continue;
      const t = (i + 1) / n;
      const alpha = isGlow
        ? 0.18 * (0.35 + 0.65 * t) * mul
        : (0.12 + 0.78 * t) * mul;
      ctx.beginPath();
      ctx.moveTo(points[i][0], points[i][1]);
      ctx.lineTo(points[i + 1][0], points[i + 1][1]);
      ctx.strokeStyle = `rgba(${r},${g},${b},${Math.min(alpha, 0.9)})`;
      ctx.lineWidth = (isGlow ? 6 : 2.2) / scale;
      ctx.lineCap = "round";
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
  radiusScale: number,
  visual: ReturnType<typeof getVisualProfile>,
) {
  const [gr, gg, gb] = hexRgb(glowColor);
  const br = 0.058 * radiusScale;
  ctx.beginPath();
  ctx.arc(x, y, br * 2.2, 0, Math.PI * 2);
  ctx.fillStyle = `rgba(${gr},${gg},${gb},${Math.min(0.38 * visual.bodyGlowAlphaMul, 0.5)})`;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(x, y, br * 1.12, 0, Math.PI * 2);
  ctx.fillStyle = coreColor;
  ctx.fill();
}

function renderFrame(
  ctx: CanvasRenderingContext2D,
  history: Float64Array,
  frameIdx: number,
  frameIndices: number[],
  opts: ThreeBodyCanvasOptions,
  w: number,
  h: number,
) {
  const visual = getVisualProfile("header");
  const size = Math.min(w, h);
  const scale = canvasWorldScale(size);
  const idx = frameIndices[frameIdx % frameIndices.length];
  const radiusScale = Math.max(size / 320, 0.85);
  const trailLength = HEADER_TRAIL_STYLE.tailLength;

  ctx.clearRect(0, 0, w, h);

  ctx.save();
  ctx.translate(w / 2, h / 2);
  ctx.scale(scale, -scale);

  if (opts.showRings !== false && HEADER_TRAIL_STYLE.showRings) {
    for (const ang of [0, 60, -60]) {
      drawAtomRing(ctx, ang, visual.ringColor, visual.ringAlpha, visual.ringLinePx, scale);
    }
  }

  const nr = 0.17;
  ctx.beginPath();
  ctx.arc(0, 0, nr, 0, Math.PI * 2);
  ctx.fillStyle = visual.nucleusFill;
  ctx.fill();

  for (let b = 0; b < BODIES; b++) {
    const tail: [number, number][] = [];
    const start = Math.max(0, idx - trailLength);
    for (let s = start; s <= idx; s++) {
      tail.push(getBodyXY(history, s, b));
    }
    drawTrail(ctx, tail, visual.bodyCoreColors[b], visual.bodyGlowColors[b], scale, visual);
  }

  for (let b = 0; b < BODIES; b++) {
    const [x, y] = getBodyXY(history, idx, b);
    drawBody(ctx, x, y, visual.bodyCoreColors[b], visual.bodyGlowColors[b], radiusScale, visual);
  }

  ctx.restore();
}

/** Start animation on canvas; returns cleanup. No-op when prefers-reduced-motion. */
export function startThreeBodyCanvas(
  canvas: HTMLCanvasElement,
  options: ThreeBodyCanvasOptions = {},
): () => void {
  if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return () => {};
  }

  const loopSeconds = options.loopSeconds ?? 18;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(Math.round(rect.width), 32);
  const h = Math.max(Math.round(rect.height), 32);
  canvas.width = w * dpr;
  canvas.height = h * dpr;

  const ctx = canvas.getContext("2d");
  if (!ctx) return () => {};

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const { history, frameIndices } = getSimHistoryForCanvas(loopSeconds, 30);
  const fps = 30;
  const frameMs = 1000 / fps;
  let frame = 0;
  let last = 0;
  let raf = 0;
  let running = true;

  const draw = (fi: number) => renderFrame(ctx, history, fi, frameIndices, options, w, h);
  draw(0);

  const tick = (now: number) => {
    if (!running) return;
    if (now - last >= frameMs) {
      last = now;
      frame = (frame + 1) % frameIndices.length;
      draw(frame);
    }
    raf = requestAnimationFrame(tick);
  };

  raf = requestAnimationFrame(tick);

  return () => {
    running = false;
    cancelAnimationFrame(raf);
  };
}

/** Static mark colors for reduced-motion fallback SVG fill. */
export const STATIC_MARK_NUCLEUS = LOGO_PALETTE.brand50;
