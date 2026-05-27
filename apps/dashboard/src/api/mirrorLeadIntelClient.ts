import {
  parseLeadProspectDetailResponse,
  parseLeadProspectsListResponse,
  parseLeadResearchSummaryResponse,
} from "./leadIntelParse";
import type {
  LeadProspectDetailResponseUi,
  LeadProspectsListQuery,
  LeadProspectsListUi,
  LeadResearchSummaryUi,
} from "./leadIntelTypes";
import { OperatorApiError, operatorApiUrl } from "./operatorClient";

export const MIRROR_LEADS_PROSPECTS_PATH = "/mirror/leads/prospects";
export const MIRROR_LEADS_SUMMARY_PATH = "/mirror/leads/summary";

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

export function mirrorLeadProspectsUrl(query: LeadProspectsListQuery = {}): string {
  const params: Record<string, string | number | boolean> = {
    limit: query.limit ?? 100,
    include_blocked: query.include_blocked ?? false,
  };
  if (query.q?.trim()) params.q = query.q.trim();
  if (query.classification?.trim()) params.classification = query.classification.trim();
  if (query.sector?.trim()) params.sector = query.sector.trim();
  if (query.region?.trim()) params.region = query.region.trim();
  if (query.buyer_type?.trim()) params.buyer_type = query.buyer_type.trim();
  if (query.campaign_bucket?.trim()) params.campaign_bucket = query.campaign_bucket.trim();
  if (query.min_score != null) params.min_score = query.min_score;
  return operatorApiUrl(MIRROR_LEADS_PROSPECTS_PATH, params);
}

export function mirrorLeadProspectDetailUrl(prospectKey: string): string {
  return operatorApiUrl(`${MIRROR_LEADS_PROSPECTS_PATH}/${encodeURIComponent(prospectKey.trim())}`);
}

export function fetchLeadProspectsMirror(
  query: LeadProspectsListQuery = {},
): Promise<LeadProspectsListUi> {
  return fetchMirrorJsonGet<unknown>(mirrorLeadProspectsUrl(query)).then(parseLeadProspectsListResponse);
}

export function fetchLeadProspectDetailMirror(
  prospectKey: string,
): Promise<LeadProspectDetailResponseUi> {
  return fetchMirrorJsonGet<unknown>(mirrorLeadProspectDetailUrl(prospectKey)).then(
    parseLeadProspectDetailResponse,
  );
}

export function fetchLeadResearchSummaryMirror(): Promise<LeadResearchSummaryUi> {
  return fetchMirrorJsonGet<unknown>(operatorApiUrl(MIRROR_LEADS_SUMMARY_PATH)).then(
    parseLeadResearchSummaryResponse,
  );
}
