/** PARKED — legacy multi-tab client (not mounted). Targets apps/api :8001 /mirror/*. See ../README.md */
import type {
  ClassificationActions,
  ClassificationRecent,
  ClassificationSummary,
  CommercialPurchaseEventsList,
  DashboardSummary,
  DashboardSyncMeta,
  OutboundReadiness,
  PaginatedContacts,
  PaginatedOrganizations,
} from "./types";

const DEFAULT_BASE = "http://127.0.0.1:8001";

export function getApiBaseUrl(): string {
  if (import.meta.env.DEV && import.meta.env.MODE === "development") {
    return "";
  }
  const raw = import.meta.env.VITE_ORIGENLAB_API_BASE_URL?.trim() || DEFAULT_BASE;
  return raw.replace(/\/$/, "");
}

export function apiUrl(path: string, params?: Record<string, string | number>): string {
  const base = getApiBaseUrl();
  const origin = base || (typeof window !== "undefined" ? window.location.origin : DEFAULT_BASE);
  const url = new URL(path.startsWith("/") ? path : `/${path}`, `${origin}/`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { method: "GET", headers: { Accept: "application/json" } });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(text || res.statusText || `HTTP ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export function fetchDashboardSummary(scope?: "archive"): Promise<DashboardSummary> {
  const params = scope === "archive" ? { scope: "archive" } : undefined;
  return fetchJson<DashboardSummary>(apiUrl("/mirror/dashboard/summary", params));
}

export function fetchOutboundReadiness(): Promise<OutboundReadiness> {
  return fetchJson<OutboundReadiness>(apiUrl("/mirror/outbound/readiness"));
}

export function fetchContacts(limit = 5): Promise<PaginatedContacts> {
  return fetchJson<PaginatedContacts>(apiUrl("/mirror/contacts", { limit, offset: 0 }));
}

export function fetchOrganizations(limit = 5): Promise<PaginatedOrganizations> {
  return fetchJson<PaginatedOrganizations>(apiUrl("/mirror/organizations", { limit, offset: 0 }));
}

export function fetchDashboardSyncMeta(): Promise<DashboardSyncMeta> {
  return fetchJson<DashboardSyncMeta>(apiUrl("/mirror/meta/dashboard-sync"));
}

export function fetchClassificationSummary(): Promise<ClassificationSummary> {
  return fetchJson<ClassificationSummary>(apiUrl("/mirror/classification/summary"));
}

export function fetchClassificationRecent(
  label?: string,
  limit = 20,
): Promise<ClassificationRecent> {
  const params: Record<string, string | number> = { limit };
  if (label) params.label = label;
  return fetchJson<ClassificationRecent>(apiUrl("/mirror/classification/recent", params));
}

export function fetchClassificationActions(): Promise<ClassificationActions> {
  return fetchJson<ClassificationActions>(apiUrl("/mirror/classification/actions"));
}

export function fetchCommercialPurchaseEvents(
  limit = 20,
): Promise<CommercialPurchaseEventsList> {
  return fetchJson<CommercialPurchaseEventsList>(
    apiUrl("/mirror/commercial/purchase-events", { limit }),
  );
}
