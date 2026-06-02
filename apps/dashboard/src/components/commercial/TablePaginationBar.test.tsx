import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TablePaginationBar } from "./TablePaginationBar";

describe("TablePaginationBar", () => {
  it("shows all page numbers for a small page count", () => {
    render(
      <TablePaginationBar
        page={2}
        totalPages={3}
        pageSize={15}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );
    const nav = screen.getByTestId("table-pagination-nav");
    expect(within(nav).getByRole("button", { name: "Página 1" })).toBeTruthy();
    expect(within(nav).getByRole("button", { name: "Página 2" }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(within(nav).getByRole("button", { name: "Página 3" })).toBeTruthy();
    expect(screen.queryByText("…")).toBeNull();
  });

  it("shows ellipsis for a large page count", () => {
    render(
      <TablePaginationBar
        page={6}
        totalPages={12}
        pageSize={15}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );
    const nav = screen.getByTestId("table-pagination-nav");
    expect(within(nav).getAllByText("…").length).toBeGreaterThanOrEqual(1);
    expect(within(nav).getByRole("button", { name: "Página 6" }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(within(nav).getByRole("button", { name: "Página 1" })).toBeTruthy();
    expect(within(nav).getByRole("button", { name: "Página 12" })).toBeTruthy();
  });

  it("disables first and last when on boundary pages", () => {
    render(
      <TablePaginationBar
        page={1}
        totalPages={5}
        pageSize={15}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );
    expect((screen.getByRole("button", { name: "Primera página" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect((screen.getByRole("button", { name: "Página anterior" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect((screen.getByRole("button", { name: "Última página" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
    expect(
      (screen.getByRole("button", { name: "Página siguiente" }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("calls onPageChange when a numbered page is clicked", () => {
    const onPageChange = vi.fn();
    render(
      <TablePaginationBar
        page={1}
        totalPages={4}
        pageSize={15}
        onPageChange={onPageChange}
        onPageSizeChange={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Página 3" }));
    expect(onPageChange).toHaveBeenCalledWith(3);
  });

  it("hides numbered pages when page size is Todos", () => {
    render(
      <TablePaginationBar
        page={1}
        totalPages={1}
        pageSize="all"
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: "Página 1" })).toBeNull();
    expect((screen.getByRole("button", { name: "Primera página" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});
