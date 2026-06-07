import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TechnicalDetailDisclosure } from "./TechnicalDetailDisclosure";

describe("TechnicalDetailDisclosure", () => {
  it("renders collapsed details with custom label", () => {
    render(<TechnicalDetailDisclosure detail="Negocios (API 503): raw json" label="Ver detalle técnico" />);
    screen.getByText("Ver detalle técnico");
    const details = screen.getByText("Ver detalle técnico").closest("details");
    expect(details?.hasAttribute("open")).toBe(false);
  });

  it("returns null for empty detail", () => {
    const { container } = render(<TechnicalDetailDisclosure detail="   " />);
    expect(container.firstChild).toBeNull();
  });
});
