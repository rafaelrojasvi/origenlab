import { useMemo, useState } from "react";
import type { ApiBackend } from "../../api/operatorTypes";
import type { EquipmentOpportunityItem } from "../../api/commercialTypes";
import { formatTableCountLabel } from "../../lib/clientTableView";
import {
  DEFAULT_EQUIPMENT_FILTERS,
  applyEquipmentTableView,
  equipmentFiltersActive,
  type EquipmentSortKey,
  type EquipmentTableFilters,
} from "../../lib/equipmentTableView";
import { equipmentSourceLabel } from "../../lib/dataSourceLabel";
import {
  EQUIPMENT_FEED_UNAVAILABLE_LINES,
  EQUIPMENT_FEED_UNAVAILABLE_TITLE,
  isEquipmentFeedUnavailable,
} from "../../lib/equipmentFeedStatus";
import { truncate } from "../../lib/safeText";
import { TokenLabel } from "../operator/TokenLabel";
import { ContactEmailButton } from "./ContactEmailButton";
import { TableListToolbar, ToolbarField, toolbarInputClass, toolbarSelectClass } from "./TableListToolbar";
import { TableSection } from "./TableSection";

export function EquipmentOpportunitiesTable({
  backend,
  items,
  meta,
  loading,
  error,
  onRetry,
  onContactSelect,
}: {
  backend: ApiBackend;
  items: EquipmentOpportunityItem[];
  onContactSelect: (email: string) => void;
  meta: {
    data_source: "active_current_csv" | "postgres_mirror";
    reduced_mode: boolean;
    note: string;
    count: number;
    campaign_mode: string | null;
  } | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  const [filters, setFilters] = useState<EquipmentTableFilters>(DEFAULT_EQUIPMENT_FILTERS);

  const sourceLabel = meta
    ? equipmentSourceLabel(backend, meta.data_source)
    : equipmentSourceLabel(backend, "active_current_csv");

  const visibleRows = useMemo(() => applyEquipmentTableView(items, filters), [items, filters]);
  const filtersActive = equipmentFiltersActive(filters);
  const loadedCount = items.length;
  const apiCount = meta?.count ?? loadedCount;
  const campaignExtra = meta?.campaign_mode ? `campaign ${meta.campaign_mode}` : undefined;
  const feedUnavailable = isEquipmentFeedUnavailable(meta);
  const showUnavailableEmpty = !loading && !error && feedUnavailable;
  const showZeroEmpty = !loading && !error && !feedUnavailable && loadedCount === 0;

  const toolbar = (
    <TableListToolbar>
      <ToolbarField label="Search" className="min-w-[12rem] flex-1">
        <input
          type="search"
          className={toolbarInputClass()}
          placeholder="Buyer, region, category, item, note…"
          value={filters.search}
          onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          aria-label="Search equipment opportunities"
        />
      </ToolbarField>
      <ToolbarField label="Sort">
        <select
          className={toolbarSelectClass()}
          value={filters.sort}
          onChange={(e) =>
            setFilters((f) => ({ ...f, sort: e.target.value as EquipmentSortKey }))
          }
          aria-label="Sort equipment opportunities"
        >
          <option value="rank_asc">Priority rank (low first)</option>
          <option value="rank_desc">Priority rank (high first)</option>
          <option value="close_date_asc">Close date (soonest)</option>
          <option value="close_date_desc">Close date (latest)</option>
          <option value="category">Equipment category</option>
          <option value="buyer">Buyer</option>
        </select>
      </ToolbarField>
      {filtersActive ? (
        <button
          type="button"
          className="rounded-md border border-[var(--color-border)] bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          onClick={() => setFilters(DEFAULT_EQUIPMENT_FILTERS)}
        >
          Clear filters
        </button>
      ) : null}
    </TableListToolbar>
  );

  return (
    <TableSection
      title="Oportunidades de equipos"
      subtitle="Cola de licitaciones y equipos · solo lectura desde manifiesto."
      dataSourceLabel={sourceLabel}
      loading={loading}
      error={error}
      onRetry={onRetry}
      empty={showZeroEmpty}
      emptyMessage="No hay oportunidades de equipos en la cola actual."
      filterEmpty={!loading && !error && loadedCount > 0 && visibleRows.length === 0}
      filterEmptyMessage="Ninguna oportunidad coincide con la búsqueda actual."
      reducedNote={!feedUnavailable && meta?.note ? meta.note : undefined}
      toolbar={loadedCount > 0 && !feedUnavailable ? toolbar : undefined}
    >
      {showUnavailableEmpty ? (
        <div
          className="rounded-xl border border-amber-200 bg-amber-50/90 px-5 py-5 text-sm text-amber-950"
          role="status"
          data-testid="equipment-feed-unavailable"
        >
          <p className="font-semibold">{EQUIPMENT_FEED_UNAVAILABLE_TITLE}</p>
          <ul className="mt-3 list-disc space-y-1 pl-5">
            {EQUIPMENT_FEED_UNAVAILABLE_LINES.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {!showUnavailableEmpty ? (
      <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-[var(--color-muted)]">
            <tr>
              <th className="px-3 py-2 font-medium">Rank</th>
              <th className="px-3 py-2 font-medium">Buyer / institution</th>
              <th className="px-3 py-2 font-medium">Contact</th>
              <th className="px-3 py-2 font-medium">Region</th>
              <th className="px-3 py-2 font-medium">Category</th>
              <th className="px-3 py-2 font-medium">Contact status</th>
              <th className="px-3 py-2 font-medium">Close date</th>
              <th className="px-3 py-2 font-medium">Channel</th>
              <th className="px-3 py-2 font-medium">Item / evidence</th>
              <th className="px-3 py-2 font-medium">Next action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {visibleRows.map((row, index) => (
              <tr
                key={`eq-${row.priority_rank}-${row.codigo_licitacion || index}`}
                className="align-top hover:bg-slate-50/80"
              >
                <td className="px-3 py-2 font-semibold text-slate-900">{row.priority_rank ?? index + 1}</td>
                <td className="px-3 py-2">
                  <div className="font-medium text-slate-900">{row.buyer || "—"}</div>
                  <div className="text-xs text-[var(--color-muted)]">{row.codigo_licitacion}</div>
                </td>
                <td className="px-3 py-2">
                  <ContactEmailButton email={row.contact_email} onSelect={onContactSelect} />
                </td>
                <td className="px-3 py-2 text-slate-700">{row.region || "—"}</td>
                <td className="px-3 py-2">
                  <TokenLabel
                    token={row.equipment_category}
                    kind="equipment_category"
                    className="text-slate-800"
                  />
                </td>
                <td className="px-3 py-2">
                  <TokenLabel
                    token={row.contact_status}
                    kind="equipment_contact_status"
                    className="text-xs text-slate-800"
                  />
                </td>
                <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">
                  {row.close_date || "—"}
                </td>
                <td className="px-3 py-2">
                  <TokenLabel
                    token={row.safe_channel}
                    kind="equipment_safe_channel"
                    className="text-xs text-slate-800"
                  />
                </td>
                <td className="px-3 py-2 max-w-sm">
                  <p className="text-slate-800">
                    {row.item_description ? truncate(row.item_description, 100) : "—"}
                  </p>
                  {row.operator_note ? (
                    <p className="mt-1 text-xs text-[var(--color-muted)]">
                      Note: {truncate(row.operator_note, 80)}
                    </p>
                  ) : null}
                  {row.supplier_needed ? (
                    <p className="mt-1 text-xs text-slate-600">Supplier: {row.supplier_needed}</p>
                  ) : null}
                </td>
                <td className="px-3 py-2">
                  <TokenLabel
                    token={row.next_action}
                    kind="equipment_next_action"
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
            noun: "opportunities",
            extra: campaignExtra,
          })}
        </p>
      </div>
      ) : null}
    </TableSection>
  );
}
