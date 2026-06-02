import {
  CLIENT_PAGE_SIZE_OPTIONS,
  getVisiblePageNumbers,
  type ClientPageSizeOption,
} from "../../lib/clientTablePagination";

const navButtonClass =
  "rounded-md border border-[var(--color-border)] bg-white px-2.5 py-1 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50";

export function TablePaginationBar({
  page,
  totalPages,
  pageSize,
  onPageChange,
  onPageSizeChange,
  disabled,
}: {
  page: number;
  totalPages: number;
  pageSize: ClientPageSizeOption;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: ClientPageSizeOption) => void;
  disabled?: boolean;
}) {
  const showPageNav = totalPages > 1 && pageSize !== "all";
  const pageTokens = showPageNav ? getVisiblePageNumbers(page, totalPages) : [];

  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] px-3 py-2"
      data-testid="table-pagination-bar"
    >
      <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-muted)]">
        <span className="font-medium text-slate-700">Filas por página</span>
        <select
          className="rounded-md border border-[var(--color-border)] bg-white px-2 py-1 text-sm text-slate-800"
          value={pageSize === "all" ? "all" : String(pageSize)}
          onChange={(e) => {
            const v = e.target.value;
            onPageSizeChange(v === "all" ? "all" : (Number(v) as ClientPageSizeOption));
          }}
          disabled={disabled}
          aria-label="Filas por página"
        >
          {CLIENT_PAGE_SIZE_OPTIONS.map((n) => (
            <option key={n} value={String(n)}>
              {n}
            </option>
          ))}
          <option value="all">Todos</option>
        </select>
      </div>
      <nav
        className="flex flex-wrap items-center gap-1"
        aria-label="Paginación de tabla"
        data-testid="table-pagination-nav"
      >
        <button
          type="button"
          className={navButtonClass}
          disabled={disabled || !showPageNav || page <= 1}
          onClick={() => onPageChange(1)}
          aria-label="Primera página"
        >
          Primera
        </button>
        <button
          type="button"
          className={navButtonClass}
          disabled={disabled || !showPageNav || page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="Página anterior"
        >
          Anterior
        </button>
        {showPageNav ? (
          <ol className="flex flex-wrap items-center gap-1 px-1" role="list">
            {pageTokens.map((token, index) =>
              token === "ellipsis" ? (
                <li
                  key={`ellipsis-${index}`}
                  className="px-1 text-sm text-slate-500"
                  aria-hidden
                >
                  …
                </li>
              ) : (
                <li key={token}>
                  <button
                    type="button"
                    className={`min-w-[2rem] rounded-md border px-2 py-1 text-sm ${
                      token === page
                        ? "border-brand-600 bg-brand-600 font-semibold text-white"
                        : "border-[var(--color-border)] bg-white text-slate-700 hover:bg-slate-50"
                    }`}
                    disabled={disabled}
                    onClick={() => onPageChange(token)}
                    aria-label={`Página ${token}`}
                    aria-current={token === page ? "page" : undefined}
                  >
                    {token}
                  </button>
                </li>
              ),
            )}
          </ol>
        ) : null}
        <button
          type="button"
          className={navButtonClass}
          disabled={disabled || !showPageNav || page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label="Página siguiente"
        >
          Siguiente
        </button>
        <button
          type="button"
          className={navButtonClass}
          disabled={disabled || !showPageNav || page >= totalPages}
          onClick={() => onPageChange(totalPages)}
          aria-label="Última página"
        >
          Última
        </button>
      </nav>
    </div>
  );
}
