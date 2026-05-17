import { LOGO_PALETTE } from './palette';
import type { MarkSolution } from './markGeometry';

export type LogoVariant = 'light' | 'dark' | 'color';

export interface VariantTokens {
  bg: string;
  primary: string;
  secondary: string;
  muted: string;
  nucleus: string;
  nucleusRing: string;
  /** Atom orbit ellipses — prefer brand-500/600 for visibility on dark */
  ring: string;
  wordmark: string;
}

export function tokensForVariant(variant: LogoVariant): VariantTokens {
  if (variant === 'light') {
    return {
      bg: LOGO_PALETTE.white,
      primary: LOGO_PALETTE.brand900,
      secondary: LOGO_PALETTE.brand800,
      muted: LOGO_PALETTE.brand600,
      nucleus: LOGO_PALETTE.brand900,
      nucleusRing: LOGO_PALETTE.brand500,
      ring: LOGO_PALETTE.brand600,
      wordmark: LOGO_PALETTE.brand950,
    };
  }
  if (variant === 'color') {
    return {
      bg: LOGO_PALETTE.brand950,
      primary: LOGO_PALETTE.brand200,
      secondary: LOGO_PALETTE.brand300,
      muted: LOGO_PALETTE.brand600,
      nucleus: LOGO_PALETTE.brand100,
      nucleusRing: LOGO_PALETTE.brand400,
      ring: LOGO_PALETTE.brand500,
      wordmark: LOGO_PALETTE.brand100,
    };
  }
  return {
    bg: LOGO_PALETTE.brand950,
    primary: LOGO_PALETTE.brand200,
    secondary: LOGO_PALETTE.brand300,
    muted: LOGO_PALETTE.brand700,
    nucleus: LOGO_PALETTE.brand50,
    nucleusRing: LOGO_PALETTE.brand300,
    ring: LOGO_PALETTE.brand500,
    wordmark: LOGO_PALETTE.brand50,
  };
}

export function trailStyleForSolution(solution: MarkSolution) {
  if (solution === 'trace') {
    return {
      tailLength: 220,
      gapPattern: 5,
      keep: 2,
      ringAlpha: 0.14,
      showRings: true,
      ringLinePx: 1.35,
    };
  }
  if (solution === 'minimal') {
    return { tailLength: 110, gapPattern: 6, keep: 1, ringAlpha: 0, showRings: false, ringLinePx: 0 };
  }
  return {
    tailLength: 210,
    gapPattern: 5,
    keep: 2,
    ringAlpha: 0.18,
    showRings: true,
    ringLinePx: 1.35,
  };
}

/** Static SVG ring stroke opacity per solution (dark backgrounds). */
export function ringOpacityForSolution(solution: MarkSolution): number {
  if (solution === 'premium') return 0.24;
  if (solution === 'trace') return 0.12;
  return 0;
}
