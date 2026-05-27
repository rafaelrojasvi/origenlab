import { useMemo, useState } from "react";
import type { ApiBackend } from "../../api/operatorTypes";
import type { WarmCaseCategory, WarmCaseItem, WarmCaseStatus } from "../../api/commercialTypes";
import { formatTableCountLabel } from "../../lib/clientTableView";
import { warmCasesSourceLabel } from "../../lib/dataSourceLabel";
import {
  clearWarmCaseTableFilters,
  DEFAULT_WARM_FILTERS,
  WARM_VIEW_PRESET_LABELS,
  WARM_VIEW_PRESET_ORDER,
  applyWarmCaseTableView,
  uniqueWarmCategories,
  uniqueWarmStatuses,
  warmFiltersActive,
  type WarmCaseSortKey,
  type WarmCaseTableFilters,
} from "../../lib/warmCaseTableView";
import { formatOperatorToken } from "../../lib/operatorLabels";
import { truncate } from "../../lib/safeText";
import { TokenLabel } from "../operator/TokenLabel";
import { ContactEmailButton } from "./ContactEmailButton";
import { CopyTextButton } from "./CopyTextButton";
import { TableListToolbar, ToolbarField, toolbarInputClass, toolbarSelectClass } from "./TableListToolbar";
import { TableSection } from "./TableSection";
import { CaseDetailDrawer } from "./CaseDetailDrawer";

export function WarmCasesTable({
  backend,
  items,
  meta,
  loading,
  error,
  onRetry,
  onContactSelect,
  title = "Casos tibios / Warm cases",
  subtitle = "Read-only queue · subject/snippet previews only (no email bodies).",
  initialFilters,
  showViewPresets = true,
}: {
  backend: ApiBackend;
  items: WarmCaseItem[];
  onContactSelect: (email: string) => void;
  meta: {
    data_source: "sqlite" | "postgres_mirror";
    reduced_mode: boolean;
    note: string;
    count: number;
  } | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  title?: string;
  subtitle?: string;
  initialFilters?: Partial<WarmCaseTableFilters>;
  showViewPresets?: boolean;
}) {
  const [filters, setFilters] = useState<WarmCaseTableFilters>({
    ...DEFAULT_WARM_FILTERS,
    ...initialFilters,
  });
  const [selectedCase, setSelectedCase] = useState<WarmCaseItem | null>(null);

  const sourceLabel = meta
    ? warmCasesSourceLabel(backend, meta.data_source)
    : warmCasesSourceLabel(backend, "sqlite");

  const visibleRows = useMemo(() => applyWarmCaseTableView(items, filters), [items, filters]);
  const statusOptions = useMemo(() => uniqueWarmStatuses(items), [items]);
  const categoryOptions = useMemo(() => uniqueWarmCategories(items), [items]);
  const filtersActive = warmFiltersActive(filters);
  const loadedCount = items.length;
  const apiCount = meta?.count ?? loadedCount;
  const presetLabel = WARM_VIEW_PRESET_LABELS[filters.preset];

  const presetChips = (
    <div
      className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--color-border)] bg-slate-50/80 px-3 py-3"
      role="group"
      aria-label="Warm queue view preset"
    >
      <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
        Vista
      </span>
      {WARM_VIEW_PRESET_ORDER.map((preset) => {
        const active = filters.preset === preset;
        return (
          <button
            key={preset}
            type="button"
            aria-pressed={active}
            className={`rounded-full px-3 py-1 text-sm font-medium transition-colors ${
              active
                ? "bg-brand-600 text-white shadow-sm"
                : "border border-[var(--color-border)] bg-white text-slate-700 hover:bg-slate-100"
            }`}
            onClick={() => setFilters((f) => ({ ...f, preset }))}
          >
            {WARM_VIEW_PRESET_LABELS[preset]}
          </button>
        );
      })}
    </div>
  );

  const toolbar = (
    <TableListToolbar>
      <ToolbarField label="Search" className="min-w-[12rem] flex-1">
        <input
          type="search"
          className={toolbarInputClass()}
          placeholder="Contact, domain, org, subject, snippet…"
          value={filters.search}
          onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          aria-label="Search warm cases"
        />
      </ToolbarField>
      <ToolbarField label="Status">
        <select
          className={toolbarSelectClass()}
          value={filters.status}
          onChange={(e) =>
            setFilters((f) => ({ ...f, status: e.target.value as WarmCaseStatus | "" }))
          }
          aria-label="Filter by status"
        >
          <option value="">All</option>
          {statusOptions.map((s) => (
            <option key={s} value={s} title={s}>
              {formatOperatorToken(s, "warm_status").label}
            </option>
          ))}
        </select>
      </ToolbarField>
      <ToolbarField label="Category">
        <select
          className={toolbarSelectClass()}
          value={filters.category}
          onChange={(e) =>
            setFilters((f) => ({ ...f, category: e.target.value as WarmCaseCategory | "" }))
          }
          aria-label="Filter by category"
        >
          <option value="">All</option>
          {categoryOptions.map((c) => (
            <option key={c} value={c} title={c}>
              {formatOperatorToken(c, "warm_category").label}
            </option>
          ))}
        </select>
      </ToolbarField>
      <ToolbarField label="Sort">
        <select
          className={toolbarSelectClass()}
          value={filters.sort}
          onChange={(e) =>
            setFilters((f) => ({ ...f, sort: e.target.value as WarmCaseSortKey }))
          }
          aria-label="Sort warm cases"
        >
          <option value="last_seen_desc">Last seen (newest)</option>
          <option value="last_seen_asc">Last seen (oldest)</option>
          <option value="status">Status</option>
          <option value="category">Category</option>
          <option value="contact">Contact email</option>
        </select>
      </ToolbarField>
      <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
        <input
          type="checkbox"
          checked={filters.hideInternalContacts}
          onChange={(e) =>
            setFilters((f) => ({ ...f, hideInternalContacts: e.target.checked }))
          }
          aria-label="Hide internal OrigenLab contacts"
        />
        <span title="Hides @origenlab.cl and @labdelivery.cl in the loaded table only (client-side).">
          Hide internal OrigenLab contacts
        </span>
      </label>
      {filtersActive ? (
        <button
          type="button"
          className="rounded-md border border-[var(--color-border)] bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          onClick={() => setFilters(clearWarmCaseTableFilters())}
          aria-label="Clear search and dropdown filters; reset view to Clientes reales"
          title="Clears search, status, and category filters and resets the view preset to Clientes reales."
        >
          Clear filters
        </button>
      ) : null}
    </TableListToolbar>
  );

  return (
    <TableSection
      title={title}
      subtitle={subtitle}
      dataSourceLabel={sourceLabel}
      loading={loading}
      error={error}
      onRetry={onRetry}
      empty={!loading && !error && loadedCount === 0}
      emptyMessage="No warm cases returned from the API."
      filterEmpty={!loading && !error && loadedCount > 0 && visibleRows.length === 0}
      filterEmptyMessage="No warm cases match the current search or filters."
      reducedNote={
        meta?.reduced_mode && meta.note
          ? `Reduced mode: ${meta.note}`
          : meta?.reduced_mode
            ? "Reduced mode: enrichment or data unavailable."
            : undefined
      }
      toolbar={
        loadedCount > 0 ? (
          <div className="space-y-3">
            {showViewPresets ? presetChips : null}
            {toolbar}
          </div>
        ) : undefined
      }
    >
      <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-[var(--color-muted)]">
            <tr>
              <th className="px-3 py-2 font-medium">Contact</th>
              <th className="px-3 py-2 font-medium">Organization</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Category</th>
              <th className="px-3 py-2 font-medium">Last seen</th>
              <th className="px-3 py-2 font-medium">Equipment</th>
              <th className="px-3 py-2 font-medium">Subject / snippet</th>
              <th className="px-3 py-2 font-medium">Next action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {visibleRows.map((row, index) => (
              <tr
                key={row.case_id || `warm-${index}`}
                className="align-top cursor-pointer hover:bg-brand-50/50 focus-within:bg-brand-50/50"
                onClick={() => setSelectedCase(row)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelectedCase(row);
                  }
                }}
                tabIndex={0}
                role="button"
                aria-label={`Open case summary for ${row.contact_email}`}
              >
                <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                  <ContactEmailButton email={row.contact_email} onSelect={onContactSelect} />
                  <div className="mt-1">
                    <CopyTextButton label="Copy email" value={row.contact_email} />
                  </div>
                </td>
                <td className="px-3 py-2 text-slate-800">{row.account_name || "—"}</td>
                <td className="px-3 py-2">
                  <TokenLabel token={row.status} kind="warm_status" />
                </td>
                <td className="px-3 py-2">
                  <TokenLabel
                    token={row.category}
                    kind="warm_category"
                    className="text-xs text-slate-800"
                  />
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">
                  {row.last_seen_at ?? "—"}
                </td>
                <td className="px-3 py-2 text-xs text-slate-700">
                  {row.equipment_signal || "—"}
                </td>
                <td className="px-3 py-2 max-w-xs">
                  <div className="font-medium text-slate-800">
                    {row.subject ? truncate(row.subject, 80) : "—"}
                  </div>
                  {row.snippet ? (
                    <p className="mt-1 text-xs text-[var(--color-muted)]">
                      <span className="font-medium text-slate-600">Preview:</span>{" "}
                      {truncate(row.snippet, 120)}
                    </p>
                  ) : null}
                </td>
                <td className="px-3 py-2">
                  <TokenLabel
                    token={row.next_action}
                    kind="warm_next_action"
                    className="text-xs text-slate-800"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="border-t border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-muted)]">
          {formatTableCountLabel({
            visible: visibleRows.length,
            loaded: loadedCount,
            apiTotal: apiCount,
            filtered: filtersActive,
            noun: "cases",
            presetLabel,
          })}
        </p>
      </div>

      <CaseDetailDrawer
        item={selectedCase}
        open={selectedCase !== null}
        onClose={() => setSelectedCase(null)}
        onContactSelect={onContactSelect}
      />
    </TableSection>
  );
}
