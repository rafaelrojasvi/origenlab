import type { LeadProspectsListQuery, ProspectOriginFilter } from "../api/leadIntelTypes";

const SOURCE_TYPE_ORIGINS = new Set<ProspectOriginFilter>([
  "deepsearch",
  "gmail_historico",
  "followup_antiguo",
  "caso_activo",
]);

/** Map UI “Origen” filter to mirror list query params. */
export function leadProspectsQueryFromOrigin(
  origin: ProspectOriginFilter,
  base: LeadProspectsListQuery,
): LeadProspectsListQuery {
  const q: LeadProspectsListQuery = { ...base };
  delete q.classification;
  delete q.source_type;
  delete q.blocked_only;

  if (!origin) {
    return q;
  }
  if (origin === "blocked") {
    return { ...q, blocked_only: true, include_blocked: true };
  }
  if (SOURCE_TYPE_ORIGINS.has(origin)) {
    return { ...q, source_type: origin };
  }
  return { ...q, classification: origin };
}
