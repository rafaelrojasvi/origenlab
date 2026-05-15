import type { ReactNode } from "react";

interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
}

interface Props<T> {
  title: string;
  caption?: string;
  columns: Column<T>[];
  rows: T[];
  emptyMessage?: string;
}

export function DataTable<T>({
  title,
  caption,
  columns,
  rows,
  emptyMessage = "Sin registros.",
}: Props<T>) {
  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] shadow-sm overflow-hidden">
      <div className="border-b border-[var(--color-border)] px-4 py-3">
        <h3 className="font-semibold text-slate-900">{title}</h3>
        {caption ? <p className="mt-1 text-xs text-[var(--color-muted)]">{caption}</p> : null}
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-[var(--color-muted)]">
            <tr>
              {columns.map((col) => (
                <th key={col.key} className="px-4 py-2 font-medium">
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-6 text-center text-[var(--color-muted)]"
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              rows.map((row, i) => (
                <tr key={i} className="hover:bg-slate-50/80">
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-2 text-slate-800">
                      {col.render(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
