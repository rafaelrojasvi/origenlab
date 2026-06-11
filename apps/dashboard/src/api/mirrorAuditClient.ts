import type { GmailInteractionAuditResponse } from "./gmailInteractionAuditTypes";
import { OperatorApiError, operatorApiUrl } from "./operatorClient";

export const MIRROR_GMAIL_INTERACTIONS_PATH = "/mirror/audits/gmail-interactions";

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

export function mirrorGmailInteractionsUrl(): string {
  return operatorApiUrl(MIRROR_GMAIL_INTERACTIONS_PATH);
}

export async function fetchGmailInteractionAudit(): Promise<GmailInteractionAuditResponse> {
  return fetchMirrorJsonGet<GmailInteractionAuditResponse>(mirrorGmailInteractionsUrl());
}
