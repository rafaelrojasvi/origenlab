/**
 * Read-only client for apps/api Postgres mirror commercial deal endpoints.
 * Uses credentialed GET only for the deals list mirror.
 */

import { parseCommercialDealsListResponse } from "./commercialDealsParse";
import type { CommercialDealsListUi } from "./commercialDealsTypes";
import { OperatorApiError, getOperatorApiBaseUrl, operatorApiUrl } from "./operatorClient";

export const MIRROR_COMMERCIAL_DEALS_PATH = "/mirror/commercial/deals";

const DEFAULT_DEALS_LIMIT = 20;

async function fetchMirrorJsonGet<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    method: "GET",
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new OperatorApiError(text || res.statusText || `HTTP ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export function mirrorCommercialDealsUrl(limit = DEFAULT_DEALS_LIMIT): string {
  return operatorApiUrl(MIRROR_COMMERCIAL_DEALS_PATH, { limit });
}

export function fetchCommercialDealsMirror(
  limit = DEFAULT_DEALS_LIMIT,
): Promise<CommercialDealsListUi> {
  return fetchMirrorJsonGet<unknown>(mirrorCommercialDealsUrl(limit)).then(
    parseCommercialDealsListResponse,
  );
}

export { getOperatorApiBaseUrl };
