import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DailyCoreRunNote } from "./DailyCoreRunNote";

const VALID_RUN = {
  path: "/secret/active/current/daily_core_run_manifest.json",
  exists: true,
  loaded: true,
  workflow: "daily-core",
  status: "success",
  returncode: 0,
  step_count: 7,
  send_approval: false,
  postgres_mirror: "not included",
  generated_at_utc: "2026-06-05T12:00:00+00:00",
} as const;

describe("DailyCoreRunNote", () => {
  it("shows no run registered when prop is omitted", () => {
    render(<DailyCoreRunNote />);
    screen.getByText("Última ejecución daily-core");
    screen.getByText("Sin ejecución registrada todavía.");
    screen.getByText(/No aprueba envíos/);
  });

  it("shows no run registered when prop is null", () => {
    render(<DailyCoreRunNote dailyCoreRun={null} />);
    screen.getByText("Sin ejecución registrada todavía.");
  });

  it("shows parse error message", () => {
    render(
      <DailyCoreRunNote
        dailyCoreRun={{
          exists: true,
          loaded: false,
          parse_error: true,
          path: "/secret/daily_core_run_manifest.json",
        }}
      />,
    );
    screen.getByText("Manifest no legible; revisar status en CLI.");
  });

  it("shows valid manifest summary fields", () => {
    render(<DailyCoreRunNote dailyCoreRun={VALID_RUN} />);
    screen.getByText("success");
    screen.getByText("7");
    screen.getByText("0");
    screen.getByText("2026-06-05T12:00:00+00:00");
    screen.getByText("not included");
    screen.getByText("No");
    screen.getByText(/No aprueba envíos/);
  });

  it("does not render manifest filesystem path", () => {
    render(<DailyCoreRunNote dailyCoreRun={VALID_RUN} />);
    expect(screen.queryByText(/\/secret\/active/)).toBeNull();
    expect(screen.queryByText(/daily_core_run_manifest\.json/)).toBeNull();
  });

  it("hides safety note when showSafetyNote is false", () => {
    render(<DailyCoreRunNote dailyCoreRun={VALID_RUN} showSafetyNote={false} />);
    expect(screen.queryByText(/No aprueba envíos/)).toBeNull();
    screen.getByText("success");
  });
});
