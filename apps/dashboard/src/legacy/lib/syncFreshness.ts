import type { DashboardSyncMeta } from "../api/types";

const STALE_HOURS = 48;

export function syncTimestampIso(meta: DashboardSyncMeta | null): string | null {
  if (!meta?.table_available || meta.status === "no_rows") return null;
  return meta.finished_at ?? meta.started_at ?? null;
}

export function isSyncStale(meta: DashboardSyncMeta | null): boolean {
  const at = syncTimestampIso(meta);
  if (!at) return true;
  const ms = Date.now() - new Date(at).getTime();
  return ms > STALE_HOURS * 60 * 60 * 1000;
}

export function isSyncMissing(meta: DashboardSyncMeta | null): boolean {
  if (!meta) return true;
  return !meta.table_available || meta.status === "no_rows" || meta.status === "missing_table";
}
