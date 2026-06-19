import { useEffect, useMemo, useState } from "react";
import type { ApiBackend } from "../../api/operatorTypes";
import type { EquipmentOpportunityItem } from "../../api/commercialTypes";
import { formatPagedFooterLabel } from "../../lib/clientTablePagination";
import { useClientTablePagination } from "../../lib/useClientTablePagination";
import { TablePaginationBar } from "./TablePaginationBar";
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
import {
  formatEquipmentCloseDate,
  formatEquipmentPublicationDate,
} from "../../lib/dashboardDateFormat";
import { getEquipmentFilterEmptyMessage } from "../../lib/equipmentEmptyState";
import { useEquipmentWatchlist } from "../../lib/equipmentWatchlist";
import { truncate } from "../../lib/safeText";
import { TokenLabel } from "../operator/TokenLabel";
import { ContactEmailButton } from "./ContactEmailButton";
import { EquipmentTriageBadges } from "./EquipmentTriageBadges";
import { EquipmentWatchlistButton } from "./EquipmentWatchlistButton";
import {
  EquipmentOpportunityDetailDrawer,
  MercadoPublicoLink,
  equipmentOpportunityRowKey,
} from "./EquipmentOpportunityDetailDrawer";
import { TableListToolbar, ToolbarField, toolbarInputClass, toolbarSelectClass } from "./TableListToolbar";
import { TableSection } from "./TableSection";

function EquipmentItemMetadata({ row }: { row: EquipmentOpportunityItem }) {
  const lines: string[] = [];
  if (row.cantidad) lines.push(`Cantidad: ${row.cantidad}`);
  if (row.unidad) lines.push(`Unidad: ${row.unidad}`);
  if (row.producto) lines.push(`Producto: ${truncate(row.producto, 60)}`);
  if (row.unspsc_code) lines.push(`UNSPSC: ${row.unspsc_code}`);
  if (row.nivel_1) lines.push(`Nivel 1: ${truncate(row.nivel_1, 50)}`);
  if (row.nivel_2) lines.push(`Nivel 2: ${truncate(row.nivel_2, 50)}`);
  if (row.nivel_3) lines.push(`Nivel 3: ${truncate(row.nivel_3, 50)}`);
  const statusParts = [
    row.chilecompra_status,
    row.validity_status ? `validez: ${row.validity_status}` : "",
  ].filter(Boolean);
  if (statusParts.length) lines.push(statusParts.join(" · "));
  if (!lines.length) return null;
  return (
    <div className="mt-1 space-y-0.5 text-xs text-slate-600">
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  );
}

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
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const { savedKeys, isSaved, toggleSaved } = useEquipmentWatchlist();

  const sourceLabel = meta
    ? equipmentSourceLabel(backend, meta.data_source)
    : equipmentSourceLabel(backend, "active_current_csv");

  const visibleRows = useMemo(
    () => applyEquipmentTableView(items, filters, { savedKeys }),
    [items, filters, savedKeys],
  );
  const { pageSize, setPage, setPageSize, pagination } = useClientTablePagination(visibleRows, [
    filters.search,
    filters.sort,
    filters.triage,
    filters.watchlist,
    savedKeys.size,
    items.length,
  ]);
  const pagedRows = pagination.slice;
  const filtersActive = equipmentFiltersActive(filters);
  const loadedCount = items.length;
  const apiCount = meta?.count ?? loadedCount;
  const campaignExtra = meta?.campaign_mode ? `campaign ${meta.campaign_mode}` : undefined;
  const feedUnavailable = isEquipmentFeedUnavailable(meta);
  const showUnavailableEmpty = !loading && !error && feedUnavailable;
  const showZeroEmpty = !loading && !error && !feedUnavailable && loadedCount === 0;

  const selectedRow = useMemo(() => {
    if (!selectedKey) return null;
    return visibleRows.find((row) => equipmentOpportunityRowKey(row) === selectedKey) ?? null;
  }, [selectedKey, visibleRows]);

  useEffect(() => {
    if (!selectedKey) return;
    const stillVisible = visibleRows.some((row) => equipmentOpportunityRowKey(row) === selectedKey);
    if (!stillVisible) setSelectedKey(null);
  }, [selectedKey, visibleRows]);

  const openRow = (row: EquipmentOpportunityItem) => {
    setSelectedKey(equipmentOpportunityRowKey(row));
  };

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
      <ToolbarField label="Triage">
        <select
          className={toolbarSelectClass()}
          value={filters.triage}
          onChange={(e) =>
            setFilters((f) => ({
              ...f,
              triage: e.target.value as EquipmentTableFilters["triage"],
            }))
          }
          aria-label="Filter equipment opportunities by triage"
        >
          <option value="all">Todas</option>
          <option value="quote_now">Cotizar ahora</option>
          <option value="closing_soon">Cierre pronto</option>
          <option value="missing_contact">Sin contacto</option>
          <option value="supplier_needed">Requiere proveedor</option>
          <option value="mercado_publico_only">Solo Mercado Público</option>
        </select>
      </ToolbarField>
      <ToolbarField label="Guardadas">
        <select
          className={toolbarSelectClass()}
          value={filters.watchlist}
          onChange={(e) =>
            setFilters((f) => ({
              ...f,
              watchlist: e.target.value as EquipmentTableFilters["watchlist"],
            }))
          }
          aria-label="Filter equipment opportunities by watchlist"
        >
          <option value="all">Todas</option>
          <option value="saved">Solo guardadas</option>
        </select>
      </ToolbarField>
      {savedKeys.size > 0 ? (
        <p className="self-center text-xs text-[var(--color-muted)]" data-testid="equipment-watchlist-count">
          {savedKeys.size} guardada{savedKeys.size === 1 ? "" : "s"} en este navegador
        </p>
      ) : null}
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
      filterEmptyMessage={getEquipmentFilterEmptyMessage(filters)}
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
            {pagedRows.map((row, index) => {
              const rowKey = equipmentOpportunityRowKey(row);
              const isSelected = selectedKey === rowKey;
              const licitationLabel = row.codigo_licitacion
                ? `Ver detalle de licitación ${row.codigo_licitacion}`
                : `Ver detalle de oportunidad ${row.buyer || row.priority_rank}`;

              return (
              <tr
                key={rowKey}
                className={`align-top cursor-pointer transition-colors hover:bg-slate-50/80 ${
                  isSelected ? "bg-sky-50/90 ring-1 ring-inset ring-sky-200" : ""
                }`}
                onClick={() => openRow(row)}
                aria-selected={isSelected}
              >
                <td className="px-3 py-2 font-semibold text-slate-900">{row.priority_rank ?? index + 1}</td>
                <td className="px-3 py-2">
                  <button
                    type="button"
                    className="w-full text-left"
                    aria-expanded={isSelected}
                    aria-controls="equipment-opportunity-detail-panel"
                    aria-label={licitationLabel}
                    onClick={(event) => {
                      event.stopPropagation();
                      openRow(row);
                    }}
                  >
                    <div className="font-medium text-slate-900 hover:text-brand-800">
                      {row.buyer || "—"}
                    </div>
                    <div className="text-xs text-[var(--color-muted)]">{row.codigo_licitacion}</div>
                    <EquipmentTriageBadges item={row} />
                  </button>
                  <EquipmentWatchlistButton
                    item={row}
                    saved={isSaved(row)}
                    onToggle={() => toggleSaved(row)}
                  />
                  {row.fecha_publicacion ? (
                    <div className="mt-0.5 text-xs text-slate-600">
                      Publicado: {formatEquipmentPublicationDate(row.fecha_publicacion)}
                    </div>
                  ) : null}
                  {row.mercado_publico_url ? (
                    <div onClick={(event) => event.stopPropagation()}>
                      <MercadoPublicoLink
                        url={row.mercado_publico_url}
                        className="mt-1 inline-block text-xs text-sky-700 hover:underline"
                      />
                    </div>
                  ) : null}
                </td>
                <td className="px-3 py-2" onClick={(event) => event.stopPropagation()}>
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
                  {formatEquipmentCloseDate(row.close_date, row.close_at)}
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
                  <EquipmentItemMetadata row={row} />
                </td>
                <td className="px-3 py-2">
                  <TokenLabel
                    token={row.next_action}
                    kind="equipment_next_action"
                    className="text-xs text-slate-800"
                  />
                </td>
              </tr>
            );
            })}
          </tbody>
        </table>
        {visibleRows.length > 0 ? (
          <TablePaginationBar
            page={pagination.page}
            totalPages={pagination.totalPages}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        ) : null}
        <p
          className="border-t border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-muted)]"
          data-testid="equipment-table-footer"
        >
          {formatPagedFooterLabel({
            from: pagination.from,
            to: pagination.to,
            visibleTotal: pagination.visibleTotal,
            page: pagination.page,
            totalPages: pagination.totalPages,
            extraParts: [
              ...(filtersActive && visibleRows.length < loadedCount ? ["filtros activos"] : []),
              ...(apiCount !== loadedCount ? [`API reportó ${apiCount}`] : []),
              ...(campaignExtra ? [campaignExtra] : []),
            ],
          })}
        </p>
      </div>
      ) : null}
      {selectedRow ? (
        <EquipmentOpportunityDetailDrawer
          item={selectedRow}
          open
          onClose={() => setSelectedKey(null)}
          watchlistSaved={isSaved(selectedRow)}
          onToggleWatchlist={() => toggleSaved(selectedRow)}
        />
      ) : null}
    </TableSection>
  );
}
