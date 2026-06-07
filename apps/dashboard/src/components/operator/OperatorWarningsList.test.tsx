import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OperatorWarningsList } from "./OperatorWarningsList";

describe("OperatorWarningsList", () => {
  it("renders warning emails as contact drilldown buttons without mailto", () => {
    const onSelect = vi.fn();
    render(
      <OperatorWarningsList
        warnings={["Quiteca: institutional caution — jorgepc@quiteca.cl contacted April 2026."]}
        onContactSelect={onSelect}
      />,
    );

    const btn = screen.getByRole("button", { name: "jorgepc@quiteca.cl" });
    fireEvent.click(btn);
    expect(onSelect).toHaveBeenCalledWith("jorgepc@quiteca.cl");
    expect(screen.queryByRole("link", { name: /mailto/i })).toBeNull();
    expect(screen.getByText(/perfil de solo lectura/i)).toBeTruthy();
  });

  it("keeps email drilldown when display text is humanized", () => {
    const onSelect = vi.fn();
    const original =
      "FastLab (contacto@fastlab.cl): corrected to not_contacted; no Gmail Sent evidence; future outreach requires deliberate manual review.";
    render(
      <OperatorWarningsList
        warnings={[
          {
            display:
              "FastLab quedó marcado como no contactado porque no hay evidencia en Gmail Enviados. Revisar manualmente antes de contactar.",
            parseText: original,
          },
        ]}
        onContactSelect={onSelect}
      />,
    );

    screen.getByText(/FastLab quedó marcado como no contactado/);
    const btn = screen.getByRole("button", { name: "contacto@fastlab.cl" });
    fireEvent.click(btn);
    expect(onSelect).toHaveBeenCalledWith("contacto@fastlab.cl");
  });
});
