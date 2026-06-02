import { useMemo } from "react";
import { useDashboardData } from "../context/DashboardDataContext";
import {
  filterLogisticsAdminWarmCases,
  filterPaymentAdminWarmCases,
  filterPaymentsLogisticsWarmCases,
} from "../lib/warmCaseSectionFilters";
import { WarmCasesTable } from "../components/commercial/WarmCasesTable";

export function PaymentsLogisticsPage() {
  const { backend, warm, warmLoading, warmError, loadWarm, setContactEmail } = useDashboardData();

  const allAdmin = useMemo(
    () => filterPaymentsLogisticsWarmCases(warm?.items ?? []),
    [warm?.items],
  );
  const paymentItems = useMemo(() => filterPaymentAdminWarmCases(allAdmin), [allAdmin]);
  const logisticsItems = useMemo(() => filterLogisticsAdminWarmCases(allAdmin), [allAdmin]);

  const meta = warm?.meta ?? null;
  const globalQueueTotal = warm?.items?.length ?? meta?.count ?? 0;

  if (warmLoading || warmError) {
    return (
      <WarmCasesTable
        backend={backend}
        items={allAdmin}
        meta={meta}
        loading={warmLoading}
        error={warmError}
        onRetry={() => void loadWarm()}
        onContactSelect={setContactEmail}
        title="Pagos y logística"
        subtitle="Cargando hilos administrativos…"
        showViewPresets={false}
        initialFilters={{ preset: "todo", hideInternalContacts: false }}
      />
    );
  }

  return (
    <div className="space-y-8">
      <WarmCasesTable
        backend={backend}
        items={paymentItems}
        meta={meta}
        loading={false}
        error={null}
        onRetry={() => void loadWarm()}
        onContactSelect={setContactEmail}
        title="Pagos"
        subtitle="Transferencias, facturas y confirmación de pago · no son cotizaciones a clientes."
        showViewPresets={false}
        initialFilters={{ preset: "todo", hideInternalContacts: false }}
        sectionName="Pagos"
        globalQueueTotal={globalQueueTotal}
      />
      <WarmCasesTable
        backend={backend}
        items={logisticsItems}
        meta={meta}
        loading={false}
        error={null}
        onRetry={() => void loadWarm()}
        onContactSelect={setContactEmail}
        title="Logística"
        subtitle="DHL, cuentas de importación y flete."
        showViewPresets={false}
        initialFilters={{ preset: "todo", hideInternalContacts: false }}
        sectionName="Logística"
        globalQueueTotal={globalQueueTotal}
      />
    </div>
  );
}
