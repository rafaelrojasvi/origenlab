import { describe, expect, it } from "vitest";
import type { OperatorAutomationStatus } from "../api/operatorTypes";
import { buildAutomationRunSummary } from "./automationRunSummary";

const NOW = new Date("2026-06-10T18:30:00+00:00");

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
      last_run_started_at: "2026-06-10T18:10:00+00:00",
      last_run_finished_at: "2026-06-10T18:12:48+00:00",
      last_successful_refresh_at: "2026-06-10T18:12:48+00:00",
      consecutive_failures: 0,
    },
    dashboard_auto_mirror: {
      state_exists: true,
      paused: false,
      lock_live: false,
      last_result: "success",
      last_run_started_at: "2026-06-10T18:15:00+00:00",
      last_run_finished_at: "2026-06-10T18:18:33+00:00",
      last_successful_mirror_at: "2026-06-10T18:18:33+00:00",
      mirror_matches_daily_core: true,
      cooldown_seconds: 900,
      cooldown_remaining_seconds: 0,
      consecutive_failures: 0,
    },
    chilecompra_equipment_auto_refresh: {
      state_exists: true,
      lock_live: false,
      lock_age_seconds: null,
      last_result: "refreshed",
      last_run_started_at: "2026-06-10T17:30:00+00:00",
      last_run_finished_at: "2026-06-10T17:41:00+00:00",
      published_rows: 7,
      detail_error_count: 0,
      freshness_age_seconds: 3000,
      next_run_due: false,
      consecutive_failures: 0,
    },
    cron: { note: "not inspected by API" },
    recommended_action: "none",
    warnings: [],
    dashboard_mirror_sync: {
      status: "success",
      latest_sync_id: 135,
      started_at: "2026-06-10T18:20:00+00:00",
      finished_at: "2026-06-10T18:25:00+00:00",
      elapsed_seconds: 296,
    },
    ...overrides,
  };
}

describe("buildAutomationRunSummary", () => {
  it("returns four compact rows for known automation loops", () => {
    const rows = buildAutomationRunSummary(baseStatus(), { now: NOW });
    expect(rows).toHaveLength(4);
    expect(rows.map((row) => row.id)).toEqual([
      "gmail-sqlite",
      "sqlite-dashboard",
      "chilecompra",
      "postgres-sync",
    ]);
    expect(rows[0]).toMatchObject({
      label: "Gmail → SQLite",
      primary: "éxito",
      tone: "ok",
      finishedAt: "2026-06-10T18:12:48+00:00",
      startedAt: "2026-06-10T18:10:00+00:00",
    });
    expect(rows[1].primary).toBe("éxito");
    expect(rows[2].primary).toBe("éxito");
    expect(rows[2].secondary).toMatch(/7 filas/);
    expect(rows[3]).toMatchObject({
      label: "Espejo Postgres",
      primary: "éxito",
      tone: "ok",
    });
    expect(rows[3].secondary).toMatch(/sync #135/);
    expect(rows[3].secondary).toMatch(/296s/);
  });

  it("marks lock_live as en curso", () => {
    const rows = buildAutomationRunSummary(
      baseStatus({
        mail_auto_refresh: {
          ...baseStatus().mail_auto_refresh,
          lock_live: true,
          last_result: "success",
        },
      }),
      { now: NOW },
    );
    expect(rows[0].primary).toBe("en curso");
    expect(rows[0].tone).toBe("attention");
  });

  it("marks consecutive failures as falló", () => {
    const rows = buildAutomationRunSummary(
      baseStatus({
        dashboard_auto_mirror: {
          ...baseStatus().dashboard_auto_mirror,
          consecutive_failures: 2,
          last_result: "success",
        },
      }),
      { now: NOW },
    );
    expect(rows[1].primary).toBe("falló");
    expect(rows[1].secondary).toMatch(/2 fallas/);
  });

  it("shows mirror cooldown in secondary line", () => {
    const rows = buildAutomationRunSummary(
      baseStatus({
        dashboard_auto_mirror: {
          ...baseStatus().dashboard_auto_mirror,
          cooldown_remaining_seconds: 120,
          last_result: "cooldown",
        },
      }),
      { now: NOW },
    );
    expect(rows[1].primary).toBe("en cooldown");
    expect(rows[1].secondary).toMatch(/cooldown 120s/);
  });

  it("falls back mirror finished time to last_successful_mirror_at", () => {
    const rows = buildAutomationRunSummary(
      baseStatus({
        dashboard_auto_mirror: {
          ...baseStatus().dashboard_auto_mirror,
          last_run_finished_at: null,
          last_successful_mirror_at: "2026-06-10T18:00:00+00:00",
        },
      }),
      { now: NOW },
    );
    expect(rows[1].finishedAt).toBe("2026-06-10T18:00:00+00:00");
  });

  it("handles missing ChileCompra state with sin dato", () => {
    const rows = buildAutomationRunSummary(
      baseStatus({
        chilecompra_equipment_auto_refresh: {
          state_exists: false,
          lock_live: false,
          lock_age_seconds: null,
          freshness_age_seconds: null,
          next_run_due: null,
          consecutive_failures: 0,
        },
      }),
      { now: NOW },
    );
    expect(rows[2]).toMatchObject({
      label: "ChileCompra",
      primary: "sin dato",
      tone: "muted",
      secondary: null,
    });
  });

  it("handles missing dashboard_mirror_sync gracefully", () => {
    const rows = buildAutomationRunSummary(
      baseStatus({ dashboard_mirror_sync: null }),
      { now: NOW },
    );
    expect(rows[3]).toMatchObject({
      label: "Espejo Postgres",
      primary: "sin dato",
      tone: "muted",
      secondary: null,
    });
  });

  it("marks postgres sync failure from error_message", () => {
    const rows = buildAutomationRunSummary(
      baseStatus({
        dashboard_mirror_sync: {
          status: "failed",
          error_message: "connection refused",
          finished_at: "2026-06-10T18:25:00+00:00",
        },
      }),
      { now: NOW },
    );
    expect(rows[3].primary).toBe("falló");
    expect(rows[3].tone).toBe("blocked");
    expect(rows[3].secondary).toMatch(/con error/);
  });
});
