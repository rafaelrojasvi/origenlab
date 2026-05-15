import type {
  DashboardSummary,
  OutboundReadiness,
  PaginatedContacts,
  PaginatedOrganizations,
} from "./types";

const DEFAULT_BASE = "http://127.0.0.1:8000";

export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_ORIGENLAB_API_BASE_URL?.trim() || DEFAULT_BASE;
  return raw.replace(/\/$/, "");
}

export function apiUrl(path: string, params?: Record<string, string | number>): string {
  const base = getApiBaseUrl();
  const url = new URL(path.startsWith("/") ? path : `/${path}`, `${base}/`);
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
  return fetchJson<DashboardSummary>(apiUrl("/dashboard/summary", params));
}

export function fetchOutboundReadiness(): Promise<OutboundReadiness> {
  return fetchJson<OutboundReadiness>(apiUrl("/outbound/readiness"));
}

export function fetchContacts(limit = 5): Promise<PaginatedContacts> {
  return fetchJson<PaginatedContacts>(apiUrl("/contacts", { limit, offset: 0 }));
}

export function fetchOrganizations(limit = 5): Promise<PaginatedOrganizations> {
  return fetchJson<PaginatedOrganizations>(apiUrl("/organizations", { limit, offset: 0 }));
}
