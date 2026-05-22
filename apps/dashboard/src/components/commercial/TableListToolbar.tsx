import type { ReactNode } from "react";

export function TableListToolbar({ children }: { children: ReactNode }) {
  return (
    <div
      className="flex flex-wrap items-end gap-3 rounded-lg border border-[var(--color-border)] bg-slate-50/80 px-3 py-3"
      role="search"
    >
      {children}
    </div>
  );
}

export function ToolbarField({
  label,
  children,
  className = "",
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`flex min-w-[8rem] flex-col gap-1 text-xs ${className}`}>
      <span className="font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}

export function toolbarInputClass(): string {
  return "rounded-md border border-[var(--color-border)] bg-white px-2 py-1.5 text-sm text-slate-900 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500";
}

export function toolbarSelectClass(): string {
  return toolbarInputClass();
}
