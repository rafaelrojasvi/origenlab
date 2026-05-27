import { useMemo } from "react";
import { useDashboardData } from "../context/DashboardDataContext";
import { filterSupplierWarmCases } from "../lib/warmCaseSectionFilters";
import { WarmCasesTable } from "../components/commercial/WarmCasesTable";

export function SuppliersPage() {
  const { backend, warm, warmLoading, warmError, loadWarm, setContactEmail } = useDashboardData();

  const supplierItems = useMemo(
    () => filterSupplierWarmCases(warm?.items ?? []),
    [warm?.items],
  );

  return (
    <WarmCasesTable
      backend={backend}
      items={supplierItems}
      meta={warm?.meta ?? null}
      loading={warmLoading}
      error={warmError}
      onRetry={() => void loadWarm()}
      onContactSelect={setContactEmail}
      title="Suppliers"
      subtitle="Supplier quotes and follow-ups · excludes client opportunities."
      showViewPresets={false}
      initialFilters={{ preset: "todo", hideInternalContacts: false }}
    />
  );
}
