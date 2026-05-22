import type { ContactRow, OrganizationRow } from "../api/types";

export const INTERNAL_EMAILS = new Set(["contacto@origenlab.cl"]);

export const INTERNAL_DOMAINS = new Set(["origenlab.cl", "labdelivery.cl"]);

export const CONSUMER_EMAIL_DOMAINS = new Set([
  "gmail.com",
  "googlemail.com",
  "hotmail.com",
  "outlook.com",
  "live.com",
  "yahoo.com",
  "yahoo.es",
  "icloud.com",
]);

export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

export function domainFromEmail(email: string): string {
  const e = normalizeEmail(email);
  const at = e.lastIndexOf("@");
  return at >= 0 ? e.slice(at + 1) : "";
}

export function normalizeDomain(domain: string): string {
  return domain.trim().toLowerCase().replace(/^www\./, "");
}

export function isInternalEmail(email: string): boolean {
  const norm = normalizeEmail(email);
  if (INTERNAL_EMAILS.has(norm)) return true;
  const dom = domainFromEmail(norm);
  return INTERNAL_DOMAINS.has(dom);
}

export function isInternalOrganizationDomain(domain: string): boolean {
  return INTERNAL_DOMAINS.has(normalizeDomain(domain));
}

export function isConsumerEmailDomain(domain: string): boolean {
  const d = normalizeDomain(domain);
  return CONSUMER_EMAIL_DOMAINS.has(d);
}

export function filterContactsForDisplay(
  items: ContactRow[],
  maxRows = 5,
): ContactRow[] {
  const out: ContactRow[] = [];
  for (const row of items) {
    if (isInternalEmail(row.email)) continue;
    const dom = row.domain ? normalizeDomain(row.domain) : domainFromEmail(row.email);
    if (INTERNAL_DOMAINS.has(dom)) continue;
    out.push(row);
    if (out.length >= maxRows) break;
  }
  return out;
}

export function partitionOrganizationsForDisplay(items: OrganizationRow[]): {
  primary: OrganizationRow[];
  consumer: OrganizationRow[];
} {
  const primary: OrganizationRow[] = [];
  const consumer: OrganizationRow[] = [];
  for (const row of items) {
    const dom = normalizeDomain(row.domain);
    if (isInternalOrganizationDomain(dom)) continue;
    if (isConsumerEmailDomain(dom)) {
      consumer.push(row);
    } else {
      primary.push(row);
    }
  }
  return { primary, consumer };
}

export function selectOrganizationsForDisplay(
  items: OrganizationRow[],
  maxPrimary = 5,
): {
  primary: OrganizationRow[];
  consumer: OrganizationRow[];
} {
  const { primary, consumer } = partitionOrganizationsForDisplay(items);
  return {
    primary: primary.slice(0, maxPrimary),
    consumer: consumer.slice(0, 8),
  };
}
