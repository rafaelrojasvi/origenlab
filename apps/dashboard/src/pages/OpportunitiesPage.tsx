import { useDashboardData } from "../context/DashboardDataContext";
import { EquipmentOpportunitiesTable } from "../components/commercial/EquipmentOpportunitiesTable";

export function OpportunitiesPage() {
  const {
    backend,
    equipment,
    equipmentLoading,
    equipmentError,
    loadEquipment,
    setContactEmail,
  } = useDashboardData();

  return (
    <EquipmentOpportunitiesTable
      backend={backend}
      items={equipment?.items ?? []}
      meta={equipment?.meta ?? null}
      loading={equipmentLoading}
      error={equipmentError}
      onRetry={() => void loadEquipment()}
      onContactSelect={setContactEmail}
    />
  );
}
