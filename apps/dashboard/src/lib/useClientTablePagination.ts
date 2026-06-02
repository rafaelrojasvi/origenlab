import { useEffect, useMemo, useState } from "react";
import {
  DEFAULT_CLIENT_PAGE_SIZE,
  paginateSlice,
  type ClientPageSizeOption,
} from "./clientTablePagination";

/** Client-side page state; resets to page 1 when `resetDeps` change. */
export function useClientTablePagination<T>(rows: T[], resetDeps: readonly unknown[]) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<ClientPageSizeOption>(DEFAULT_CLIENT_PAGE_SIZE);

  useEffect(() => {
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller supplies filter keys
  }, resetDeps);

  const pagination = useMemo(() => paginateSlice(rows, page, pageSize), [rows, page, pageSize]);

  useEffect(() => {
    if (page !== pagination.page) {
      setPage(pagination.page);
    }
  }, [pagination.page, page]);

  const setPageSizeAndReset = (size: ClientPageSizeOption) => {
    setPageSize(size);
    setPage(1);
  };

  return {
    page,
    setPage,
    pageSize,
    setPageSize: setPageSizeAndReset,
    pagination,
  };
}
