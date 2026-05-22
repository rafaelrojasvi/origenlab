/**
 * Read-only client for apps/api operator endpoints.
 * Do not add mutation methods (POST/PUT/PATCH/DELETE).
 */

import { parseContactDetailResponse } from "./contactParse";
import type { ContactProfileUi } from "./contactTypes";
import {
  parseEquipmentOpportunitiesResponse,
  parseWarmCasesResponse,
} from "./commercialParse";
import type {
  EquipmentOpportunitiesQuery,
  EquipmentOpportunitiesUiResponse,
  WarmCasesQuery,
  WarmCasesResponse,
} from "./commercialTypes";
import type { HealthResponse, OperatorStatusResponse, TodayPanelData } from "./operatorTypes";

export const PRODUCTION_API_BASE_URL_REQUIRED =
  "VITE_ORIGENLAB_API_BASE_URL is required for production builds (npm run build). Set it to your public apps/api URL.";

export class OperatorApiConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "OperatorApiConfigError";
  }
}

function isProductionBuild(): boolean {
  return import.meta.env.MODE === "production";
}

/** Resolve API base URL. Production builds must set VITE_ORIGENLAB_API_BASE_URL (no localhost fallback). */
export function getOperatorApiBaseUrl(): string {
  if (isProductionBuild()) {
    const raw = import.meta.env.VITE_ORIGENLAB_API_BASE_URL?.trim();
    if (!raw) {
      throw new OperatorApiConfigError(PRODUCTION_API_BASE_URL_REQUIRED);
    }
    return raw.replace(/\/$/, "");
  }
  const raw = import.meta.env.VITE_ORIGENLAB_API_BASE_URL?.trim();
  if (raw) {
    return raw.replace(/\/$/, "");
  }
  return "";
}

export function operatorApiUrl(
  path: string,
  params?: Record<string, string | number | boolean>,
): string {
  const base = getOperatorApiBaseUrl();
  const origin =
    base ||
    (typeof window !== "undefined"
      ? window.location.origin
      : (() => {
          throw new OperatorApiConfigError(
            "Cannot resolve API URL without window. Set VITE_ORIGENLAB_API_BASE_URL or run via npm run dev.",
          );
        })());
  const url = new URL(path.startsWith("/") ? path : `/${path}`, `${origin}/`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export class OperatorApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "OperatorApiError";
  }
}

async function fetchJsonGet<T>(url: string): Promise<T> {
  const res = await fetch(url, { method: "GET", headers: { Accept: "application/json" } });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new OperatorApiError(text || res.statusText || `HTTP ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export function fetchHealth(): Promise<HealthResponse> {
  return fetchJsonGet<HealthResponse>(operatorApiUrl("/health"));
}

export function fetchOperatorStatus(
  maxStalenessDays = 14,
): Promise<OperatorStatusResponse> {
  return fetchJsonGet<OperatorStatusResponse>(
    operatorApiUrl("/operator/status", { max_staleness_days: maxStalenessDays }),
  );
}

export async function fetchTodayPanel(): Promise<TodayPanelData> {
  const [health, operator] = await Promise.all([fetchHealth(), fetchOperatorStatus()]);
  return { health, operator };
}

const DEFAULT_WARM_QUERY: Required<Pick<WarmCasesQuery, "days" | "limit" | "positive_signal_only">> =
  {
    days: 14,
    limit: 30,
    positive_signal_only: false,
  };

const DEFAULT_EQUIPMENT_QUERY: Required<
  Pick<EquipmentOpportunitiesQuery, "limit" | "include_account_intelligence">
> = {
  limit: 30,
  include_account_intelligence: false,
};

export function fetchWarmCases(query: WarmCasesQuery = {}): Promise<WarmCasesResponse> {
  const params: Record<string, string | number | boolean> = {
    days: query.days ?? DEFAULT_WARM_QUERY.days,
    limit: query.limit ?? DEFAULT_WARM_QUERY.limit,
    positive_signal_only:
      query.positive_signal_only ?? DEFAULT_WARM_QUERY.positive_signal_only,
  };
  if (query.category) {
    params.category = query.category;
  }
  if (query.include_noise) {
    params.include_noise = query.include_noise;
  }
  return fetchJsonGet<unknown>(operatorApiUrl("/cases/warm", params)).then(parseWarmCasesResponse);
}

/** Build GET /contacts/{email} path with encoded email segment. */
export function contactDetailPath(email: string): string {
  const trimmed = email.trim();
  if (!trimmed || !trimmed.includes("@")) {
    throw new OperatorApiError("Invalid contact email", 422);
  }
  return `/contacts/${encodeURIComponent(trimmed)}`;
}

export function fetchContactProfile(email: string): Promise<ContactProfileUi> {
  return fetchJsonGet<unknown>(operatorApiUrl(contactDetailPath(email))).then(
    parseContactDetailResponse,
  );
}

export function fetchEquipmentOpportunities(
  query: EquipmentOpportunitiesQuery = {},
): Promise<EquipmentOpportunitiesUiResponse> {
  const params: Record<string, string | number | boolean> = {
    limit: query.limit ?? DEFAULT_EQUIPMENT_QUERY.limit,
    include_account_intelligence:
      query.include_account_intelligence ?? DEFAULT_EQUIPMENT_QUERY.include_account_intelligence,
  };
  if (query.priority != null) {
    params.priority = query.priority;
  }
  if (query.next_action) {
    params.next_action = query.next_action;
  }
  if (query.safe_channel) {
    params.safe_channel = query.safe_channel;
  }
  return fetchJsonGet<unknown>(operatorApiUrl("/opportunities/equipment", params)).then(
    parseEquipmentOpportunitiesResponse,
  );
}

/** Parse health JSON (for tests and defensive UI). */
export function parseHealthResponse(data: unknown): HealthResponse {
  const row = data as HealthResponse;
  return {
    ok: Boolean(row.ok),
    service: String(row.service ?? "origenlab-api"),
    mode: String(row.mode ?? ""),
    backend: row.backend === "postgres" ? "postgres" : "sqlite",
    postgres_configured: Boolean(row.postgres_configured),
  };
}

/** Parse operator status JSON (for tests and defensive UI). */
export function parseOperatorStatusResponse(data: unknown): OperatorStatusResponse {
  const row = data as OperatorStatusResponse;
  return {
    verdict: String(row.verdict ?? "UNKNOWN"),
    sqlite_path: String(row.sqlite_path ?? ""),
    campaign_mode: row.campaign_mode == null ? null : String(row.campaign_mode),
    operator_focus: row.operator_focus == null ? null : String(row.operator_focus),
    outbound_readiness: String(row.outbound_readiness ?? "n/a"),
    warnings: Array.isArray(row.warnings) ? row.warnings.map(String) : [],
  };
}
