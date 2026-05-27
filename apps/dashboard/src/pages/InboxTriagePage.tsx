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
      title="Inbox triage"
      subtitle="All warm threads · use view presets and filters by role category."
      initialFilters={{ preset: "todo", hideInternalContacts: false }}
    />
  );
}
