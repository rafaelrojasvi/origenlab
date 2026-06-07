import { useDashboardData } from "../context/DashboardDataContext";
import { CommercialDealHighlightCards } from "../components/commercial/CommercialDealHighlightCards";
import { CommercialDealsTable } from "../components/commercial/CommercialDealsTable";

export function DealsPage() {
  const {
    commercialDeals,
    commercialDealsLoading,
    commercialDealsError,
    commercialDealsErrorDetail,
    loadCommercialDeals,
  } = useDashboardData();

  return (
    <div className="space-y-8">
      <CommercialDealHighlightCards data={commercialDeals} />
      <CommercialDealsTable
        data={commercialDeals}
        loading={commercialDealsLoading}
        error={commercialDealsError}
        errorDetail={commercialDealsErrorDetail}
        onRetry={() => void loadCommercialDeals()}
      />
    </div>
  );
}
