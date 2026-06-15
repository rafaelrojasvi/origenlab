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

function parseChileanDateTime(value: string): number | null {
  const match = value.match(
    /^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$/,
  );
  if (!match) return null;
  const [, d, m, y, hh = "0", mm = "0", ss = "0"] = match;
  const iso = `${y}-${m.padStart(2, "0")}-${d.padStart(2, "0")}T${hh.padStart(2, "0")}:${mm.padStart(2, "0")}:${ss.padStart(2, "0")}`;
  const ts = Date.parse(iso);
  return Number.isFinite(ts) ? ts : null;
}

function formatTimestampEsCl(ts: number, includeTime: boolean): string {
  const date = new Date(ts);
  const datePart = new Intl.DateTimeFormat("es-CL", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
  if (!includeTime) return datePart;
  const timePart = new Intl.DateTimeFormat("es-CL", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
  return `${datePart}, ${timePart}`;
}

/** Equipment close display: prefers mirror close_at, else Chilean or ISO close_date. */
export function formatEquipmentCloseDate(
  closeDate: string | null | undefined,
  closeAt?: string | null,
): string {
  const at = closeAt?.trim();
  if (at) return formatDashboardDateTime(at);
  const date = closeDate?.trim();
  if (!date) return "—";
  const chileanTs = parseChileanDateTime(date);
  if (chileanTs != null) {
    const hasTime = /\d{1,2}:\d{2}/.test(date);
    return formatTimestampEsCl(chileanTs, hasTime);
  }
  const isoTs = parseIsoTimestamp(date);
  if (isoTs != null) {
    const hasTime = /T\d{2}:\d{2}/.test(date);
    return formatTimestampEsCl(isoTs, hasTime);
  }
  return date;
}

export function formatEquipmentPublicationDate(value: string | null | undefined): string {
  const trimmed = value?.trim();
  if (!trimmed) return "";
  const chileanTs = parseChileanDateTime(trimmed);
  if (chileanTs != null) {
    return formatTimestampEsCl(chileanTs, /\d{1,2}:\d{2}/.test(trimmed));
  }
  const isoTs = parseIsoTimestamp(trimmed);
  if (isoTs != null) {
    return formatTimestampEsCl(isoTs, /T\d{2}:\d{2}/.test(trimmed));
  }
  return trimmed;
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
