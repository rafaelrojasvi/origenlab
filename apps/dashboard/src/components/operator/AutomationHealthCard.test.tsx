import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { OperatorAutomationStatus } from "../../api/operatorTypes";
import {
  AUTOMATION_MISSING_STATE_HELP,
  AUTOMATION_MISSING_STATE_PRIMARY,
} from "../../lib/automationHealthLabels";
import { AutomationHealthCard } from "./AutomationHealthCard";

const BASE_STATUS: OperatorAutomationStatus = {
  generated_at_utc: "2026-06-10T18:30:00+00:00",
  active_current_dir: "/hidden/active/current",
  active_current_dir_info: {
    redacted: true,
    basename: "current",
    kind: "directory",
  },
  path_redaction_applied: true,
  verdict: "healthy",
  daily_core: {
    exists: true,
    status: "success",
    returncode: 0,
    generated_at_utc: "2026-06-10T18:12:48+00:00",
    age_seconds: 1032,
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
};

vi.mock("../../api/operatorClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/operatorClient")>();
  return {
    ...actual,
    fetchOperatorAutomationStatus: vi.fn(),
  };
});

import {
  fetchOperatorAutomationStatus,
  parseOperatorAutomationStatus,
} from "../../api/operatorClient";

const mockFetch = vi.mocked(fetchOperatorAutomationStatus);

afterEach(() => {
  vi.clearAllMocks();
});

describe("AutomationHealthCard", () => {
  it("renders healthy state in summary mode", async () => {
    mockFetch.mockResolvedValue(BASE_STATUS);
    render(<AutomationHealthCard />);
    await waitFor(() => {
      screen.getByText("Automatización al día");
    });
    expect(screen.getByTestId("automation-snapshot-summary").textContent).toMatch(
      /Snapshot local publicado/i,
    );
    expect(screen.getByTestId("automation-snapshot-summary").textContent).toMatch(
      /daily-core visible/i,
    );
    expect(screen.getByTestId("automation-snapshot-summary").textContent).toMatch(
      /mirror visible/i,
    );
    screen.getByText("Sin acción requerida");
    screen.getByText(/Gmail → SQLite:/);
    screen.getByText(/limpio/);
    screen.getByText(/sincronizado/);
    screen.getByText(/403/);
    screen.getByText(/971/);
    expect(screen.queryByText(/hidden\/active\/current/)).toBeNull();
  });

  it("renders attention when mirror is behind", async () => {
    mockFetch.mockResolvedValue({
      ...BASE_STATUS,
      verdict: "attention",
      recommended_action: "run_auto_mirror_dashboard",
      dashboard_auto_mirror: {
        ...BASE_STATUS.dashboard_auto_mirror,
        mirror_matches_daily_core: false,
      },
    });
    render(<AutomationHealthCard />);
    await waitFor(() => {
      screen.getByText("Requiere atención");
    });
    screen.getByText("Publicar espejo dashboard");
    screen.getByText(/atrás/);
  });

  it("renders blocked state", async () => {
    mockFetch.mockResolvedValue({
      ...BASE_STATUS,
      verdict: "blocked",
      recommended_action: "inspect_failed_daily_core",
      daily_core: { ...BASE_STATUS.daily_core, status: "failed", returncode: 1 },
    });
    render(<AutomationHealthCard />);
    await waitFor(() => {
      screen.getByText("Bloqueado");
    });
    screen.getByText("Revisar daily-core");
  });

  it("renders fetch failure with refresh only (no mutation actions)", async () => {
    mockFetch.mockRejectedValue(new Error("HTTP 500"));
    render(<AutomationHealthCard />);
    await waitFor(() => {
      screen.getByText("No se pudo leer estado de automatización");
    });
    screen.getByRole("button", { name: /Actualizar estado/i });
    expect(screen.queryByRole("button", { name: /Publicar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Ejecutar/i })).toBeNull();
  });

  it("shows lock hint when mail refresh is running", async () => {
    mockFetch.mockResolvedValue({
      ...BASE_STATUS,
      verdict: "attention",
      recommended_action: "wait_for_running_mail_refresh",
      mail_auto_refresh: {
        ...BASE_STATUS.mail_auto_refresh,
        lock_live: true,
      },
    });
    render(<AutomationHealthCard />);
    await waitFor(() => {
      screen.getByTestId("automation-lock-pause-hint");
    });
    screen.getByText(/Refresh Gmail en curso/);
  });

  it("renders detailed fields in detailed mode", async () => {
    mockFetch.mockResolvedValue(BASE_STATUS);
    render(<AutomationHealthCard variant="detailed" />);
    await waitFor(() => {
      screen.getByText("Estado de automatización");
    });
    screen.getByText("Daily-core");
    screen.getByText("Mail auto-refresh");
    screen.getByText("Dashboard auto-mirror");
    screen.getByText("no_change");
    screen.getByText(/not inspected by API/);
    screen.getByText("current (directory, redacted)");
    expect(screen.queryByText(/hidden\/active\/current/)).toBeNull();
    expect(screen.queryByText(/\/home\//)).toBeNull();
  });

  it("shows postgres snapshot source when published to mirror", async () => {
    mockFetch.mockResolvedValue(
      parseOperatorAutomationStatus({
        ...BASE_STATUS,
        source: "postgres_snapshot",
        snapshot_updated_at: "2026-06-11T12:00:00+00:00",
        snapshot_stale: false,
      }),
    );
    render(<AutomationHealthCard variant="detailed" />);
    await waitFor(() => {
      screen.getByTestId("automation-postgres-snapshot");
    });
    expect(screen.getByTestId("automation-postgres-snapshot").textContent).toMatch(
      /Snapshot local publicado/i,
    );
    expect(screen.getByTestId("automation-postgres-snapshot").textContent).toMatch(
      /Fuente: espejo Postgres/i,
    );
    expect(screen.queryByTestId("automation-missing-state-help")).toBeNull();
  });

  it("shows friendly help when operator state files are missing", async () => {
    mockFetch.mockResolvedValue({
      ...BASE_STATUS,
      verdict: "attention",
      recommended_action: "create_missing_state_by_running_dry_run",
      daily_core: { ...BASE_STATUS.daily_core, exists: false },
      mail_auto_refresh: { ...BASE_STATUS.mail_auto_refresh, state_exists: false },
      dashboard_auto_mirror: { ...BASE_STATUS.dashboard_auto_mirror, state_exists: false },
    });
    render(<AutomationHealthCard variant="detailed" />);
    await waitFor(() => {
      screen.getByTestId("automation-missing-state-help");
    });
    screen.getByText(AUTOMATION_MISSING_STATE_PRIMARY);
    screen.getByText(AUTOMATION_MISSING_STATE_HELP);
    expect(screen.getAllByText("Publicar snapshot o revisar localmente").length).toBeGreaterThan(0);
    expect(screen.queryByText("Ejecutar dry-run para crear estado")).toBeNull();
  });

  it("does not update state after unmount when fetch resolves late", async () => {
    let resolveFetch: ((value: OperatorAutomationStatus) => void) | undefined;
    mockFetch.mockImplementation(
      () =>
        new Promise<OperatorAutomationStatus>((resolve) => {
          resolveFetch = resolve;
        }),
    );
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    const { unmount } = render(<AutomationHealthCard />);
    screen.getByTestId("automation-health-card");
    unmount();

    resolveFetch?.(BASE_STATUS);
    await new Promise((resolve) => {
      setTimeout(resolve, 0);
    });

    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("refetches when Actualizar estado is clicked", async () => {
    mockFetch.mockResolvedValue(BASE_STATUS);
    const onRefresh = vi.fn();
    render(<AutomationHealthCard variant="detailed" onRefresh={onRefresh} />);
    await screen.findByText("Estado de automatización");
    const callsBeforeRefresh = mockFetch.mock.calls.length;
    mockFetch.mockResolvedValueOnce({
      ...BASE_STATUS,
      verdict: "attention",
      recommended_action: "run_auto_mirror_dashboard",
    });
    fireEvent.click(screen.getByRole("button", { name: /Actualizar estado/i }));
    await waitFor(() => {
      expect(screen.getAllByText("Publicar espejo dashboard").length).toBeGreaterThan(0);
    });
    expect(mockFetch.mock.calls.length).toBeGreaterThan(callsBeforeRefresh);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("renders ChileCompra automation section in detailed mode", async () => {
    mockFetch.mockResolvedValue({
      ...BASE_STATUS,
      chilecompra_equipment_auto_refresh: {
        state_exists: true,
        lock_live: false,
        lock_age_seconds: null,
        last_result: "refreshed",
        last_successful_refresh_at: "2026-06-10T17:12:48+00:00",
        last_successful_publish_at: "2026-06-10T17:41:00+00:00",
        next_recommended_run_at: "2026-06-10T20:41:00+00:00",
        freshness_age_seconds: 4620,
        next_run_due: false,
        consecutive_failures: 0,
        detail_requests: 4,
        detail_cache_hits: 2,
        detail_error_count: 0,
        published_rows: 7,
      },
      cron: {
        chilecompra_entry_present: true,
        chilecompra_uses_tracked_script: true,
      },
    });
    render(<AutomationHealthCard variant="detailed" />);
    await waitFor(() => {
      screen.getByTestId("chilecompra-automation-section");
    });
    screen.getByText("ChileCompra equipment auto-refresh");
    screen.getByText("Actualizado");
    screen.getByText("7");
    screen.getByText("4 / 2 / 0");
    screen.getByText("Cron instalado");
    screen.getByText("Wrapper correcto");
  });

  it("shows ChileCompra summary line in summary mode", async () => {
    mockFetch.mockResolvedValue({
      ...BASE_STATUS,
      chilecompra_equipment_auto_refresh: {
        ...BASE_STATUS.chilecompra_equipment_auto_refresh,
        state_exists: true,
        published_rows: 7,
        next_recommended_run_at: "2026-06-10T17:41:00+00:00",
      },
    });
    render(<AutomationHealthCard />);
    await waitFor(() => {
      screen.getByText(/ChileCompra → Dashboard: 7 filas/);
    });
    expect(screen.getByText(/ChileCompra → Dashboard: 7 filas/).textContent).toMatch(/próximo/i);
  });

  it("handles missing ChileCompra section defensively", async () => {
    mockFetch.mockResolvedValue(
      parseOperatorAutomationStatus({
        ...BASE_STATUS,
        chilecompra_equipment_auto_refresh: undefined,
      }),
    );
    render(<AutomationHealthCard variant="detailed" />);
    await waitFor(() => {
      screen.getByTestId("chilecompra-automation-section");
    });
    expect(screen.getAllByText("no").length).toBeGreaterThan(0);
  });

  it("renders redacted active_current_dir_info basename in detailed mode", async () => {
    mockFetch.mockResolvedValue({
      ...BASE_STATUS,
      active_current_dir:
        "/home/rafael/dev/freelance/origenlab/apps/email-pipeline/reports/out/active/current",
      active_current_dir_info: {
        redacted: true,
        basename: "current",
        kind: "directory",
      },
      path_redaction_applied: true,
    });
    render(<AutomationHealthCard variant="detailed" />);
    await waitFor(() => {
      screen.getByText("Directorio activo");
    });
    screen.getByText("current (directory, redacted)");
    expect(screen.queryByText(/\/home\//)).toBeNull();
    expect(screen.queryByText(/email-pipeline/)).toBeNull();
  });

  it("falls back to legacy raw path when redacted info is absent", async () => {
    mockFetch.mockResolvedValue({
      ...BASE_STATUS,
      active_current_dir: "/legacy/path/to/current",
      active_current_dir_info: null,
      path_redaction_applied: undefined,
    });
    render(<AutomationHealthCard variant="detailed" />);
    await waitFor(() => {
      screen.getByText("Directorio activo");
    });
    screen.getByText("/legacy/path/to/current");
  });

  it("renders ChileCompra path_info basenames instead of raw queue paths", async () => {
    mockFetch.mockResolvedValue({
      ...BASE_STATUS,
      chilecompra_equipment_auto_refresh: {
        state_exists: true,
        lock_live: false,
        lock_age_seconds: null,
        last_result: "refreshed",
        freshness_age_seconds: 4620,
        next_run_due: false,
        consecutive_failures: 0,
        published_rows: 7,
        published_queue:
          "/home/ops/reports/out/active/current/equipment_first_operator_queue_20260616.csv",
        candidate_audit:
          "/home/ops/reports/out/active/current/chilecompra_equipment_candidate_audit_20260616.csv",
        path_info: {
          published_queue: {
            redacted: true,
            basename: "equipment_first_operator_queue_20260616.csv",
            kind: "file",
          },
          candidate_audit: {
            redacted: true,
            basename: "chilecompra_equipment_candidate_audit_20260616.csv",
            kind: "file",
          },
        },
      },
    });
    render(<AutomationHealthCard variant="detailed" />);
    await waitFor(() => {
      screen.getByText("Cola publicada");
    });
    screen.getByText("equipment_first_operator_queue_20260616.csv (file, redacted)");
    screen.getByText("chilecompra_equipment_candidate_audit_20260616.csv (file, redacted)");
    expect(screen.queryByText(/\/home\//)).toBeNull();
  });
});
