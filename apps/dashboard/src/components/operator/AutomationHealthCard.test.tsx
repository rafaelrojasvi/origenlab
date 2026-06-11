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
  cron: { note: "not inspected by API" },
  recommended_action: "none",
  warnings: [],
};

vi.mock("../../api/operatorClient", () => ({
  fetchOperatorAutomationStatus: vi.fn(),
}));

import { fetchOperatorAutomationStatus } from "../../api/operatorClient";

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
    expect(screen.queryByText(/hidden\/active\/current/)).toBeNull();
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
});
