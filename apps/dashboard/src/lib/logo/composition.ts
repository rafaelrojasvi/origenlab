/**
 * Shared atom layout metrics — keeps canvas + SVG aligned and inside safe bounds.
 */

/** Orbit ellipse radii (world units, slightly inset for padding). */
export const ATOM_RING_RX = 3.88;
export const ATOM_RING_RY = 1.32;

/** Max radius budget: rings + stroke halo (world units). */
export const ATOM_CONTENT_RADIUS = 4.12;

/** Use ~81% of half-canvas for drawing → ~9.5% margin per side. */
export const CANVAS_PADDING_FACTOR = 0.81;

/** SVG viewBox half-extent (symmetric padding around atom). */
export const SVG_VIEW_HALF = 4.25;

/** Multiplier on ring specs inside SVG viewBox. */
export const SVG_RING_SCALE = 0.78;

/** Lockup icon display sizes (px). */
export const LOCKUP_MARK_PX = {
  sm: 28,
  md: 36,
  lg: 48,
} as const;

/** Header: larger canvas, same visual icon — breathing room for orbits. */
export const HEADER_CANVAS_PX = 44;
export const HEADER_DISPLAY_PX = 36;

export function canvasWorldScale(canvasPx: number): number {
  return ((canvasPx / 2) * CANVAS_PADDING_FACTOR) / ATOM_CONTENT_RADIUS;
}

export function lockupMarkPx(size: 'sm' | 'md' | 'lg'): number {
  return LOCKUP_MARK_PX[size];
}
