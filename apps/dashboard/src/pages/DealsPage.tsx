import { useDashboardData } from "../context/DashboardDataContext";
import { CommercialDealHighlightCards } from "../components/commercial/CommercialDealHighlightCards";
import { CommercialDealsTable } from "../components/commercial/CommercialDealsTable";

export function DealsPage() {
  const { commercialDeals, commercialDealsLoading, commercialDealsError, loadCommercialDeals } =
    useDashboardData();

  return (
    <div className="space-y-8">
      <CommercialDealHighlightCards data={commercialDeals} />
      <CommercialDealsTable
        data={commercialDeals}
        loading={commercialDealsLoading}
        error={commercialDealsError}
        onRetry={() => void loadCommercialDeals()}
      />
    </div>
  );
}
