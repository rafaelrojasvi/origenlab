import { useDashboardData } from "../context/DashboardDataContext";
import { CommercialDealsTable } from "../components/commercial/CommercialDealsTable";

export function DealsPage() {
  const { commercialDeals, commercialDealsLoading, commercialDealsError, loadCommercialDeals } =
    useDashboardData();

  return (
    <CommercialDealsTable
      data={commercialDeals}
      loading={commercialDealsLoading}
      error={commercialDealsError}
      onRetry={() => void loadCommercialDeals()}
    />
  );
}
