import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OrigenLabAnimatedLogo } from "./OrigenLabAnimatedLogo";

vi.mock("../../lib/logo/threeBodyCanvasRunner", () => ({
  startThreeBodyCanvas: vi.fn(() => () => {}),
}));

describe("OrigenLabAnimatedLogo", () => {
  it("renders OrigenLab with canvas for header animation", () => {
    const { container } = render(<OrigenLabAnimatedLogo />);
    expect(screen.getByTestId("origenlab-logo-animated")).toBeTruthy();
    expect(screen.getByText("OrigenLab")).toBeTruthy();
    expect(container.querySelector("canvas")).toBeTruthy();
    expect(screen.queryByText("Panel operador")).toBeNull();
  });
});
