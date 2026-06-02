import { renderHook, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useClientTablePagination } from "./useClientTablePagination";

describe("useClientTablePagination", () => {
  it("resets to page 1 when reset deps change", () => {
    const rows = Array.from({ length: 30 }, (_, i) => i);
    const { result, rerender } = renderHook(
      ({ search }: { search: string }) =>
        useClientTablePagination(rows, [search]),
      { initialProps: { search: "" } },
    );

    act(() => {
      result.current.setPage(2);
    });
    expect(result.current.pagination.page).toBe(2);

    rerender({ search: "acme" });
    expect(result.current.pagination.page).toBe(1);
  });
});
