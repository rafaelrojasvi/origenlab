import { useEffect, useMemo, useState } from "react";
import { fetchGmailInteractionAudit } from "../api/mirrorAuditClient";
import type { GmailInteractionAuditSnapshot } from "../api/gmailInteractionAuditTypes";
import { useDashboardData } from "../context/DashboardDataContext";
import { filterSupplierWarmCases } from "../lib/warmCaseSectionFilters";
import { SupplierEntityGroups } from "../components/commercial/SupplierEntityGroups";

export function SuppliersPage() {
  const { backend, warm, warmLoading, warmError, loadWarm, setContactEmail } = useDashboardData();
  const [auditSnapshot, setAuditSnapshot] = useState<GmailInteractionAuditSnapshot | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchGmailInteractionAudit()
      .then((response) => {
        if (!cancelled && response.status === "ok" && response.snapshot) {
          setAuditSnapshot(response.snapshot);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAuditSnapshot(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const supplierItems = useMemo(
    () => filterSupplierWarmCases(warm?.items ?? []),
    [warm?.items],
  );

  return (
    <SupplierEntityGroups
      backend={backend}
      allItems={supplierItems}
      auditSnapshot={auditSnapshot}
      meta={warm?.meta ?? null}
      loading={warmLoading}
      error={warmError}
      onRetry={() => void loadWarm()}
      onContactSelect={setContactEmail}
    />
  );
}
