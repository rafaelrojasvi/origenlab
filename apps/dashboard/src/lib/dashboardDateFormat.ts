import { parseSortableTimestamp } from "./clientTableView";

function parseIsoTimestamp(iso: string | null | undefined): number | null {
  const trimmed = iso?.trim();
  if (!trimmed) return null;
  const ts = parseSortableTimestamp(trimmed);
  if (ts > 0) return ts;
  const fallback = Date.parse(trimmed);
  return Number.isFinite(fallback) ? fallback : null;
}

export function formatDashboardDateTime(iso: string | null | undefined): string {
  const trimmed = iso?.trim();
  if (!trimmed) return "—";
  const ts = parseIsoTimestamp(trimmed);
  if (ts == null) return trimmed;
  try {
    const date = new Date(ts);
    const datePart = new Intl.DateTimeFormat("es-CL", {
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(date);
    const timePart = new Intl.DateTimeFormat("es-CL", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
    return `${datePart}, ${timePart}`;
  } catch {
    return trimmed;
  }
}

export function formatDashboardDateShort(iso: string | null | undefined): string {
  const trimmed = iso?.trim();
  if (!trimmed) return "—";
  const ts = parseIsoTimestamp(trimmed);
  if (ts == null) return trimmed;
  try {
    return new Intl.DateTimeFormat("es-CL", {
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(new Date(ts));
  } catch {
    return trimmed;
  }
}
