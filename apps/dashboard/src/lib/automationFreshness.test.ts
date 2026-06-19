import { describe, expect, it } from "vitest";
import type { OperatorAutomationStatus } from "../api/operatorTypes";
import {
  buildAutomationFreshnessSummary,
  formatAutomationFreshnessAgeLabel,
} from "./automationFreshness";

const NOW = new Date("2026-06-10T18:20:00+00:00");

function baseStatus(overrides: Partial<OperatorAutomationStatus> = {}): OperatorAutomationStatus {
  return {
    generated_at_utc: "2026-06-10T18:12:48+00:00",
    active_current_dir: "/hidden/active/current",
    verdict: "healthy",
    daily_core: {
      exists: true,
      status: "success",
      returncode: 0,
      generated_at_utc: "2026-06-10T18:12:48+00:00",
      age_seconds: 432,
      steps: 8,
    },
    mail_auto_refresh: {
      state_exists: true,
      paused: false,
      lock_live: false,
      dirty: false,
      pending: false,
      last_result: "no_change",
      last_successful_refresh_at: "2026-06-10T18:12:48+00:00",
      last_seen_inbox_total: 403,
      last_seen_sent_total: 971,
      consecutive_failures: 0,
    },
    dashboard_auto_mirror: {
      state_exists: true,
      paused: false,
      lock_live: false,
      last_result: "success",
      last_successful_mirror_at: "2026-06-10T18:18:33+00:00",
      last_mirrored_daily_core_generated_at: "2026-06-10T18:12:48+00:00",
      mirror_matches_daily_core: true,
      cooldown_seconds: 900,
      cooldown_remaining_seconds: 0,
      consecutive_failures: 0,
    },
    chilecompra_equipment_auto_refresh: {
      state_exists: false,
      lock_live: false,
      lock_age_seconds: null,
      freshness_age_seconds: null,
      next_run_due: null,
      consecutive_failures: 0,
    },
    cron: { note: "not inspected by API" },
    recommended_action: "none",
    warnings: [],
    snapshot_updated_at: "2026-06-10T18:15:00+00:00",
    snapshot_stale: false,
    ...overrides,
  };
}

describe("buildAutomationFreshnessSummary", () => {
  it("returns fresh tone and Datos frescos when all timestamps are within thresholds", () => {
    const summary = buildAutomationFreshnessSummary(baseStatus(), { now: NOW });
    expect(summary.tone).toBe("fresh");
    expect(summary.title).toBe("Datos frescos");
    expect(summary.warning).toBeNull();
    expect(summary.gmailAgeLabel).toBe("hace 7 min");
    expect(summary.mirrorAgeLabel).toBe("hace 1 min");
    expect(summary.snapshotAgeLabel).toBe("hace 5 min");
  });

  it("returns warning when Gmail is stale but mirror is fresh", () => {
    const summary = buildAutomationFreshnessSummary(baseStatus(), {
      now: new Date("2026-06-10T18:25:00+00:00"),
    });
    expect(summary.tone).toBe("warning");
    expect(summary.title).toBe("Gmail/SQLite con retraso");
    expect(summary.detail).toMatch(/Gmail → SQLite/i);
  });

  it("returns stale when mirror is old", () => {
    const summary = buildAutomationFreshnessSummary(baseStatus(), {
      now: new Date("2026-06-10T18:45:00+00:00"),
    });
    expect(summary.tone).toBe("stale");
    expect(summary.title).toBe("Espejo dashboard desactualizado");
    expect(summary.detail).toMatch(/SQLite → Dashboard/i);
  });

  it("returns stale with dashboard warning when snapshot_stale is true", () => {
    const summary = buildAutomationFreshnessSummary(
      baseStatus({ snapshot_stale: true }),
      { now: NOW },
    );
    expect(summary.tone).toBe("stale");
    expect(summary.warning).toBe("Dashboard puede estar desactualizado.");
  });

  it("returns unknown when core timestamps are missing", () => {
    const summary = buildAutomationFreshnessSummary(
      baseStatus({
        mail_auto_refresh: {
          ...baseStatus().mail_auto_refresh,
          last_successful_refresh_at: null,
        },
        snapshot_updated_at: null,
        generated_at_utc: "",
      }),
      { now: NOW },
    );
    expect(summary.tone).toBe("unknown");
    expect(summary.warning).toBe("No se pudo confirmar frescura completa.");
    expect(summary.gmailAgeLabel).toBe("sin dato");
  });

  it("returns unknown for invalid timestamps", () => {
    const summary = buildAutomationFreshnessSummary(
      baseStatus({
        mail_auto_refresh: {
          ...baseStatus().mail_auto_refresh,
          last_successful_refresh_at: "not-a-date",
        },
        dashboard_auto_mirror: {
          ...baseStatus().dashboard_auto_mirror,
          last_successful_mirror_at: "also-bad",
        },
        snapshot_updated_at: "invalid",
        generated_at_utc: "invalid",
      }),
      { now: NOW },
    );
    expect(summary.tone).toBe("unknown");
    expect(summary.gmailAgeLabel).toBe("sin dato");
    expect(summary.mirrorAgeLabel).toBe("sin dato");
    expect(summary.snapshotAgeLabel).toBe("sin dato");
  });

  it("formats ages older than one hour in hours", () => {
    expect(
      formatAutomationFreshnessAgeLabel(
        NOW.getTime() - new Date("2026-06-10T16:50:00+00:00").getTime(),
      ),
    ).toBe("hace 1 h");
  });
});
