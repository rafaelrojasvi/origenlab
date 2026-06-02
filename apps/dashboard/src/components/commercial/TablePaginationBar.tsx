import {
  CLIENT_PAGE_SIZE_OPTIONS,
  type ClientPageSizeOption,
} from "../../lib/clientTablePagination";

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
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="rounded-md border border-[var(--color-border)] bg-white px-3 py-1 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          disabled={disabled || page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="Página anterior"
        >
          Anterior
        </button>
        <span className="text-xs text-slate-700" aria-live="polite">
          Página {page} de {totalPages}
        </span>
        <button
          type="button"
          className="rounded-md border border-[var(--color-border)] bg-white px-3 py-1 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          disabled={disabled || page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label="Página siguiente"
        >
          Siguiente
        </button>
      </div>
    </div>
  );
}
