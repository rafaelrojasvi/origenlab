/** Precomputed three-body history for dashboard canvas logo (from apps/web). */

import {
  buildFrameIndices,
  findLoopEnd,
  normalizeHistory,
  simulateThreeBody,
} from "./threeBodySim";

let cachedHistory: { history: Float64Array; loopEnd: number } | null = null;

function getSimCache(loopSeconds: number, fps: number) {
  if (!cachedHistory) {
    const history = normalizeHistory(simulateThreeBody());
    const loopEnd = findLoopEnd(history);
    cachedHistory = { history, loopEnd };
  }
  const nFrames = Math.max(Math.round(loopSeconds * fps), 1);
  const frameIndices = buildFrameIndices(cachedHistory.history, cachedHistory.loopEnd, nFrames);
  return { ...cachedHistory, frameIndices };
}

export function getSimHistoryForCanvas(loopSeconds: number, fps: number) {
  return getSimCache(loopSeconds, fps);
}

export function resetSimCacheForTests(): void {
  cachedHistory = null;
}
