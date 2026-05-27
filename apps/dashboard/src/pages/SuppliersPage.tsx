import { useMemo } from "react";
import { useDashboardData } from "../context/DashboardDataContext";
import { filterSupplierWarmCases } from "../lib/warmCaseSectionFilters";
import { SupplierEntityGroups } from "../components/commercial/SupplierEntityGroups";

export function SuppliersPage() {
  const { backend, warm, warmLoading, warmError, loadWarm, setContactEmail } = useDashboardData();

  const supplierItems = useMemo(
    () => filterSupplierWarmCases(warm?.items ?? []),
    [warm?.items],
  );

  return (
    <SupplierEntityGroups
      backend={backend}
      allItems={supplierItems}
      meta={warm?.meta ?? null}
      loading={warmLoading}
      error={warmError}
      onRetry={() => void loadWarm()}
      onContactSelect={setContactEmail}
    />
  );
}
