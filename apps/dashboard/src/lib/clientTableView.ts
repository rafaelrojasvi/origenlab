/** Client-side table search, filter, and sort helpers (no API calls). */

export function normalizeSearchQuery(query: string): string {
  return query.trim().toLowerCase();
}

export function matchesSearch(haystack: string, query: string): boolean {
  const q = normalizeSearchQuery(query);
  if (!q) {
    return true;
  }
  return haystack.toLowerCase().includes(q);
}

export function emailDomain(email: string): string {
  const at = email.lastIndexOf("@");
  if (at < 0) {
    return "";
  }
  return email.slice(at + 1).toLowerCase();
}

/** Best-effort ISO-ish date parse for sorting (invalid → 0). */
export function parseSortableTimestamp(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }
  const iso = Date.parse(value);
  if (!Number.isNaN(iso)) {
    return iso;
  }
  const dm = value.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (dm) {
    const [, d, m, y] = dm;
    return Date.parse(`${y}-${m.padStart(2, "0")}-${d.padStart(2, "0")}T12:00:00`);
  }
  return 0;
}

export function formatTableCountLabel(args: {
  visible: number;
  loaded: number;
  apiTotal?: number;
  filtered: boolean;
  noun: string;
  extra?: string;
}): string {
  const { visible, loaded, apiTotal, filtered, noun, extra } = args;
  const apiPart =
    apiTotal != null && apiTotal !== loaded ? ` · API reported ${apiTotal}` : "";
  const filterPart = filtered && visible < loaded ? " · client filters active" : "";
  const extraPart = extra ? ` · ${extra}` : "";
  return `Showing ${visible} of ${loaded} loaded ${noun}${apiPart}${filterPart}${extraPart} · read-only`;
}
