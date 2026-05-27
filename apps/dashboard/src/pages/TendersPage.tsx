import { useDashboardData } from "../context/DashboardDataContext";
import { EquipmentOpportunitiesTable } from "../components/commercial/EquipmentOpportunitiesTable";

/** Public procurement / tender queue (reuses equipment opportunities mirror). */
export function TendersPage() {
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
