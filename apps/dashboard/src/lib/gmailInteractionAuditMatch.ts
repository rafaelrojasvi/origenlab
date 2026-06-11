import type {
  GmailInteractionAuditDomainRow,
  GmailInteractionAuditSnapshot,
} from "../api/gmailInteractionAuditTypes";

const DOMAIN_ALIAS_GROUPS: Record<string, readonly string[]> = {
  "ika.net.br": ["ika.net.br", "ika.com", "ika.de"],
  "serva.de": ["serva.de", "serva-electrophoresis.com"],
  "ortoalresa.com": ["ortoalresa.com", "alvarezredondo.com"],
};

const ALIAS_TO_CANONICAL = new Map<string, string>();
for (const [canonical, aliases] of Object.entries(DOMAIN_ALIAS_GROUPS)) {
  ALIAS_TO_CANONICAL.set(canonical, canonical);
  for (const alias of aliases) {
    ALIAS_TO_CANONICAL.set(alias, canonical);
  }
}

export function canonicalAuditDomain(domain: string | null | undefined): string {
  const d = (domain ?? "").trim().toLowerCase();
  if (!d) return "";
  return ALIAS_TO_CANONICAL.get(d) ?? d;
}

export function findGmailAuditForDomains(
  snapshot: GmailInteractionAuditSnapshot | null | undefined,
  domains: readonly string[],
): GmailInteractionAuditDomainRow | null {
  if (!snapshot?.domains?.length || domains.length === 0) {
    return null;
  }
  const wanted = new Set(
    domains.map((d) => canonicalAuditDomain(d)).filter((d) => d.length > 0),
  );
  for (const row of snapshot.domains) {
    if (wanted.has(canonicalAuditDomain(row.domain))) {
      return row;
    }
    for (const alias of row.matched_aliases ?? []) {
      if (wanted.has(canonicalAuditDomain(alias))) {
        return row;
      }
    }
  }
  return null;
}

export function sqliteAuditMessageCount(
  snapshot: GmailInteractionAuditSnapshot | null | undefined,
  domain: string | null | undefined,
): number {
  const row = findGmailAuditForDomains(snapshot, domain ? [domain] : []);
  return row?.message_count ?? 0;
}
