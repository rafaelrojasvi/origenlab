import { render, screen, waitFor, type RenderOptions, type RenderResult } from "@testing-library/react";
import { DashboardApp } from "../pages/DashboardApp";

/** Waits until DashboardDataProvider initial parallel loads have settled. */
export async function waitForDashboardReady(): Promise<void> {
  await waitFor(() => {
    const refresh = screen.getByRole("button", { name: /Actualizar|Actualizando/ });
    if (refresh.hasAttribute("disabled") || refresh.textContent !== "Actualizar") {
      throw new Error("Dashboard still refreshing");
    }
  });
}

export async function renderDashboardApp(options?: RenderOptions): Promise<RenderResult> {
  const view = render(<DashboardApp />, options);
  await waitForDashboardReady();
  return view;
}
