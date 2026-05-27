import { useMemo } from "react";
import { useDashboardData } from "../context/DashboardDataContext";
import { filterPaymentsLogisticsWarmCases } from "../lib/warmCaseSectionFilters";
import { WarmCasesTable } from "../components/commercial/WarmCasesTable";

export function PaymentsLogisticsPage() {
  const { backend, warm, warmLoading, warmError, loadWarm, setContactEmail } = useDashboardData();

  const adminItems = useMemo(
    () => filterPaymentsLogisticsWarmCases(warm?.items ?? []),
    [warm?.items],
  );

  return (
    <WarmCasesTable
      backend={backend}
      items={adminItems}
      meta={warm?.meta ?? null}
      loading={warmLoading}
      error={warmError}
      onRetry={() => void loadWarm()}
      onContactSelect={setContactEmail}
      title="Payments & logistics"
      subtitle="Bank, Wise, DHL, and import-account admin threads."
      showViewPresets={false}
      initialFilters={{ preset: "todo", hideInternalContacts: false }}
    />
  );
}
