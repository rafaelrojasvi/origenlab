import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CatalogProductDrawer } from "./CatalogProductDrawer";
import { servaBlueslickDetailFixture } from "../../test/fixtures/catalogMirrorFixtures";

describe("CatalogProductDrawer", () => {
  it("renders a safe website link for valid slugs", () => {
    const product = servaBlueslickDetailFixture().product!;
    render(<CatalogProductDrawer product={product} loading={false} error={null} open onClose={vi.fn()} />);

    const dialog = screen.getByRole("dialog");
    const link = within(dialog).getByRole("link", { name: "Ver ficha web" });
    expect(link.getAttribute("href")).toBe("https://origenlab.cl/productos/blueslick-42500");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.getAttribute("target")).toBe("_blank");
  });

  it("omits the website link when website_slug is unsafe", () => {
    const product = {
      ...servaBlueslickDetailFixture().product!,
      website_slug: "javascript:alert(1)",
    };
    render(<CatalogProductDrawer product={product} loading={false} error={null} open onClose={vi.fn()} />);

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByRole("link", { name: "Ver ficha web" })).toBeNull();
  });

  it("omits the website link when website_slug is missing", () => {
    const product = {
      ...servaBlueslickDetailFixture().product!,
      website_slug: null,
    };
    render(<CatalogProductDrawer product={product} loading={false} error={null} open onClose={vi.fn()} />);

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByRole("link", { name: "Ver ficha web" })).toBeNull();
  });
});
