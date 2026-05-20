import type { ApiBackend } from "../../api/operatorTypes";
import type { EquipmentOpportunityItem } from "../../api/commercialTypes";
import { equipmentSourceLabel } from "../../lib/dataSourceLabel";
import { TableSection } from "./TableSection";

function truncate(text: string, max: number): string {
  const t = text.trim();
  if (t.length <= max) {
    return t;
  }
  return `${t.slice(0, max)}…`;
}

export function EquipmentOpportunitiesTable({
  backend,
  items,
  meta,
  loading,
  error,
  onRetry,
}: {
  backend: ApiBackend;
  items: EquipmentOpportunityItem[];
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
  const sourceLabel = meta
    ? equipmentSourceLabel(backend, meta.data_source)
    : equipmentSourceLabel(backend, "active_current_csv");

  return (
    <TableSection
      title="Oportunidades de equipos"
      subtitle="Equipment-first operator queue · manifest-driven read model."
      dataSourceLabel={sourceLabel}
      loading={loading}
      error={error}
      onRetry={onRetry}
      empty={!loading && !error && items.length === 0}
      emptyMessage="No equipment opportunities returned."
      reducedNote={
        meta?.reduced_mode && meta.note
          ? `Reduced mode: ${meta.note}`
          : meta?.reduced_mode
            ? "Reduced mode: canonical queue file missing or empty."
            : undefined
      }
    >
      <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-[var(--color-muted)]">
            <tr>
              <th className="px-3 py-2 font-medium">Rank</th>
              <th className="px-3 py-2 font-medium">Buyer / institution</th>
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
            {items.map((row) => (
              <tr
                key={`${row.priority_rank}-${row.codigo_licitacion}`}
                className="align-top hover:bg-slate-50/80"
              >
                <td className="px-3 py-2 font-semibold text-slate-900">{row.priority_rank}</td>
                <td className="px-3 py-2">
                  <div className="font-medium text-slate-900">{row.buyer || "—"}</div>
                  <div className="text-xs text-[var(--color-muted)]">{row.codigo_licitacion}</div>
                </td>
                <td className="px-3 py-2 text-slate-700">{row.region || "—"}</td>
                <td className="px-3 py-2 text-slate-700">{row.equipment_category || "—"}</td>
                <td className="px-3 py-2 text-xs text-slate-700">{row.contact_status || "—"}</td>
                <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">
                  {row.close_date || "—"}
                </td>
                <td className="px-3 py-2 text-xs text-slate-700">{row.safe_channel || "—"}</td>
                <td className="px-3 py-2 max-w-sm">
                  <p className="text-slate-800">{truncate(row.item_description, 100)}</p>
                  {row.operator_note ? (
                    <p className="mt-1 text-xs text-[var(--color-muted)]">
                      Note: {truncate(row.operator_note, 80)}
                    </p>
                  ) : null}
                  {row.supplier_needed ? (
                    <p className="mt-1 text-xs text-slate-600">Supplier: {row.supplier_needed}</p>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-xs text-slate-700">{row.next_action || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="border-t border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-muted)]">
          Showing {items.length} of {meta?.count ?? items.length} opportunities
          {meta?.campaign_mode ? ` · campaign ${meta.campaign_mode}` : ""}
        </p>
      </div>
    </TableSection>
  );
}
