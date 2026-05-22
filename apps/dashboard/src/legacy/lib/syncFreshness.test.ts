import { describe, expect, it } from "vitest";
import { isSyncMissing, isSyncStale, syncTimestampIso } from "./syncFreshness";
import type { DashboardSyncMeta } from "../api/types";

describe("syncFreshness", () => {
  it("marks missing sync", () => {
    expect(isSyncMissing(null)).toBe(true);
    expect(isSyncMissing({ table_available: false, status: "missing_table" } as DashboardSyncMeta)).toBe(
      true,
    );
  });

  it("detects stale sync older than 48h", () => {
    const old = new Date(Date.now() - 72 * 60 * 60 * 1000).toISOString();
    const meta: DashboardSyncMeta = {
      table_available: true,
      status: "success",
      latest_sync_id: 1,
      started_at: old,
      finished_at: old,
      elapsed_seconds: 1,
      postgres_mirror_note: "",
      canonical_contact_count: 0,
      canonical_organization_count: 0,
      canonical_opportunity_signal_count: 0,
      archive_contact_count: 0,
      archive_organization_count: 0,
      archive_opportunity_signal_count: 0,
      email_suppression_count: 0,
      domain_suppression_count: 0,
      outreach_state_count: 0,
      error_message: null,
    };
    expect(isSyncStale(meta)).toBe(true);
    expect(syncTimestampIso(meta)).toBe(old);
  });
});
