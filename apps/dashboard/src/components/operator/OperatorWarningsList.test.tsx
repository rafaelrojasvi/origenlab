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
});
