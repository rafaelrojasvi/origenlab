import type { CommercialDealUiRow, CommercialDealsListUi } from "../../api/commercialDealsTypes";
import {
  formatBlockersPreview,
  formatClp,
  formatEurDecimal,
  formatMarginPct,
  formatUpdatedAt,
} from "../../lib/commercialDealFormat";
import { TableSection } from "./TableSection";

function DealRow({ row }: { row: CommercialDealUiRow }) {
  return (
    <tr className="border-t border-[var(--color-border)] hover:bg-slate-50/80">
      <td className="px-3 py-2 align-top">
        <p className="font-medium text-slate-900">{row.client_org_name || "—"}</p>
      </td>
      <td className="px-3 py-2 align-top">
        <p className="text-slate-800">{row.supplier_org_name || "—"}</p>
      </td>
      <td className="px-3 py-2 align-top text-xs font-medium text-slate-800">
        {row.deal_status || "—"}
      </td>
      <td className="px-3 py-2 align-top text-xs font-medium text-slate-800">
        {row.margin_status || "—"}
      </td>
      <td className="px-3 py-2 align-top text-xs text-slate-700">
        <p>{row.reconciliation_status || "—"}</p>
        <p className="mt-1 text-[var(--color-muted)]">{row.freight_status || "—"}</p>
      </td>
      <td className="px-3 py-2 align-top text-right tabular-nums">{formatClp(row.client_sale_net_clp)}</td>
      <td className="px-3 py-2 align-top text-right tabular-nums">{formatClp(row.client_sale_gross_clp)}</td>
      <td className="px-3 py-2 align-top text-right tabular-nums">
        {formatClp(row.client_payment_received_clp)}
      </td>
      <td className="px-3 py-2 align-top text-right tabular-nums">
        {formatEurDecimal(row.supplier_invoice_total_decimal)}
      </td>
      <td className="px-3 py-2 align-top text-right tabular-nums">
        {formatEurDecimal(row.supplier_amount_paid_decimal)}
      </td>
      <td className="px-3 py-2 align-top text-right tabular-nums">{formatClp(row.margin_net_clp)}</td>
      <td className="px-3 py-2 align-top text-right tabular-nums">{formatMarginPct(row.margin_pct)}</td>
      <td className="max-w-[14rem] px-3 py-2 align-top text-xs text-slate-700">
        {formatBlockersPreview(row.margin_blockers)}
      </td>
      <td className="whitespace-nowrap px-3 py-2 align-top text-xs text-[var(--color-muted)]">
        {formatUpdatedAt(row.updated_at)}
      </td>
    </tr>
  );
}

export function CommercialDealsTable({
  data,
  loading,
  error,
  onRetry,
}: {
  data: CommercialDealsListUi | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  const tableAvailable = data?.table_available ?? false;
  const items = data?.items ?? [];
  const showEmpty = !loading && !error && (!tableAvailable || items.length === 0);
  const showTable = !loading && !error && tableAvailable && items.length > 0;

  return (
    <TableSection
      title="Commercial deals"
      subtitle="Redacted commercial view · Postgres mirror only."
      dataSourceLabel="Postgres mirror · Read-only · Redacted commercial view"
      loading={loading}
      error={error}
      onRetry={onRetry}
      empty={showEmpty}
      emptyMessage="Commercial deals mirror not synced yet."
      reducedNote={
        data?.read_only
          ? "Summary amounts only. No payment IDs, contact emails, PO numbers, evidence, or local paths."
          : undefined
      }
    >
      {showTable ? (
        <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] shadow-sm">
          <p className="border-b border-[var(--color-border)] px-3 py-2 text-xs text-sky-900">
            Postgres mirror · Read-only · Redacted commercial view
            {data && data.total > items.length
              ? ` · showing ${items.length} of ${data.total}`
              : data
                ? ` · ${data.total} deal(s)`
                : null}
          </p>
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <tr>
                <th className="px-3 py-2 font-medium">Client</th>
                <th className="px-3 py-2 font-medium">Supplier</th>
                <th className="px-3 py-2 font-medium">Deal</th>
                <th className="px-3 py-2 font-medium">Margin</th>
                <th className="px-3 py-2 font-medium">Recon / freight</th>
                <th className="px-3 py-2 text-right font-medium">Net CLP</th>
                <th className="px-3 py-2 text-right font-medium">Gross CLP</th>
                <th className="px-3 py-2 text-right font-medium">Received CLP</th>
                <th className="px-3 py-2 text-right font-medium">Supplier inv.</th>
                <th className="px-3 py-2 text-right font-medium">Paid EUR</th>
                <th className="px-3 py-2 text-right font-medium">Margin net</th>
                <th className="px-3 py-2 text-right font-medium">Margin %</th>
                <th className="px-3 py-2 font-medium">Blockers</th>
                <th className="px-3 py-2 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row, index) => (
                <DealRow key={`${row.client_org_name}-${row.supplier_org_name}-${index}`} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </TableSection>
  );
}
