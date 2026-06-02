import type { CommercialDealUiRow, CommercialDealsListUi } from "../../api/commercialDealsTypes";
import {
  dealStatusLabel,
  formatBlockersPreview,
  formatClp,
  formatEurDecimal,
  formatMarginPct,
  formatUpdatedAt,
  freightStatusLabel,
  marginStatusLabel,
  reconciliationStatusLabel,
} from "../../lib/commercialDealFormat";
import { formatPagedFooterLabel } from "../../lib/clientTablePagination";
import { useClientTablePagination } from "../../lib/useClientTablePagination";
import { TableSection } from "./TableSection";
import { TablePaginationBar } from "./TablePaginationBar";

function StatusCell({ raw, label }: { raw: string; label: string }) {
  if (!raw || label === "—") {
    return <>—</>;
  }
  return (
    <span title={raw} className="cursor-help border-b border-dotted border-slate-300">
      {label}
    </span>
  );
}

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
        <StatusCell raw={row.deal_status} label={dealStatusLabel(row.deal_status)} />
      </td>
      <td className="px-3 py-2 align-top text-xs font-medium text-slate-800">
        <StatusCell raw={row.margin_status} label={marginStatusLabel(row.margin_status)} />
      </td>
      <td className="px-3 py-2 align-top text-xs text-slate-700">
        <p>
          <StatusCell
            raw={row.reconciliation_status ?? ""}
            label={reconciliationStatusLabel(row.reconciliation_status)}
          />
        </p>
        <p className="mt-1 text-[var(--color-muted)]">
          <StatusCell
            raw={row.freight_status ?? ""}
            label={freightStatusLabel(row.freight_status)}
          />
        </p>
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
  const apiTotal = data?.total ?? items.length;
  const { pageSize, setPage, setPageSize, pagination } = useClientTablePagination(items, [
    items.length,
    apiTotal,
  ]);
  const pagedItems = pagination.slice;
  const dealsFooter = formatPagedFooterLabel({
    from: pagination.from,
    to: pagination.to,
    visibleTotal: pagination.visibleTotal,
    page: pagination.page,
    totalPages: pagination.totalPages,
    extraParts: apiTotal > items.length ? [`API total ${apiTotal} negocios`] : undefined,
  });
  const showEmpty = !loading && !error && (!tableAvailable || items.length === 0);
  const showTable = !loading && !error && tableAvailable && items.length > 0;

  return (
    <TableSection
      title="Negocios comerciales"
      subtitle="Vista comercial redactada · solo espejo Postgres."
      dataSourceLabel="Espejo Postgres · solo lectura · vista redactada"
      loading={loading}
      error={error}
      onRetry={onRetry}
      empty={showEmpty}
      emptyMessage="El espejo de negocios aún no está sincronizado."
      reducedNote={
        data?.read_only
          ? "Solo montos resumidos. Sin IDs de pago, correos, órdenes de compra, evidencia ni rutas locales."
          : undefined
      }
    >
      {showTable ? (
        <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] shadow-sm">
          <p className="border-b border-[var(--color-border)] px-3 py-2 text-xs text-sky-900">
            Espejo Postgres · solo lectura · vista redactada
            {data && data.total > items.length
              ? ` · mostrando ${items.length} de ${data.total}`
              : data
                ? ` · ${data.total} negocio(s)`
                : null}
          </p>
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <tr>
                <th className="px-3 py-2 font-medium">Cliente</th>
                <th className="px-3 py-2 font-medium">Proveedor</th>
                <th className="px-3 py-2 font-medium">Negocio</th>
                <th className="px-3 py-2 font-medium">Margen</th>
                <th className="px-3 py-2 font-medium">Concil. / flete</th>
                <th className="px-3 py-2 text-right font-medium">Net CLP</th>
                <th className="px-3 py-2 text-right font-medium">Gross CLP</th>
                <th className="px-3 py-2 text-right font-medium">Received CLP</th>
                <th className="px-3 py-2 text-right font-medium">Supplier inv.</th>
                <th className="px-3 py-2 text-right font-medium">Paid EUR</th>
                <th className="px-3 py-2 text-right font-medium">Margin net</th>
                <th className="px-3 py-2 text-right font-medium">Margin %</th>
                <th className="px-3 py-2 font-medium">Bloqueos</th>
                <th className="px-3 py-2 font-medium">Actualizado</th>
              </tr>
            </thead>
            <tbody>
              {pagedItems.map((row, index) => (
                <DealRow key={`${row.client_org_name}-${row.supplier_org_name}-${index}`} row={row} />
              ))}
            </tbody>
          </table>
          {items.length > 0 ? (
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
            data-testid="commercial-deals-table-footer"
          >
            {dealsFooter}
          </p>
        </div>
      ) : null}
    </TableSection>
  );
}
