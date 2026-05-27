import { useDashboardData } from "../context/DashboardDataContext";
import { WarmCasesTable } from "../components/commercial/WarmCasesTable";

export function InboxTriagePage() {
  const { backend, warm, warmLoading, warmError, loadWarm, setContactEmail } = useDashboardData();

  return (
    <WarmCasesTable
      backend={backend}
      items={warm?.items ?? []}
      meta={warm?.meta ?? null}
      loading={warmLoading}
      error={warmError}
      onRetry={() => void loadWarm()}
      onContactSelect={setContactEmail}
      title="Bandeja de revisión"
      subtitle="Todos los hilos tibios · use las vistas y filtros por rol."
      initialFilters={{ preset: "todo", hideInternalContacts: false }}
    />
  );
}
