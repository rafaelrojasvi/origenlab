import { useEffect, useState } from "react";
import {
  ApiError,
  fetchClassificationActions,
  fetchClassificationRecent,
  fetchClassificationSummary,
  fetchContacts,
  fetchDashboardSummary,
  fetchDashboardSyncMeta,
  fetchOrganizations,
  fetchOutboundReadiness,
  getApiBaseUrl,
} from "./api/client";
import type {
  ClassificationActions,
  ClassificationRecent,
  ClassificationSummary,
  DashboardSummary,
  DashboardSyncMeta,
  OutboundReadiness,
  PaginatedContacts,
  PaginatedOrganizations,
} from "./api/types";
import { ArchiveSection } from "./components/ArchiveSection";
import { ClassificationSection } from "./components/ClassificationSection";
import { DataTable } from "./components/DataTable";
import { Header } from "./components/Header";
import { HowToReadPanel } from "./components/HowToReadPanel";
import { KpiCards } from "./components/KpiCards";
import { OrganizationsSection } from "./components/OrganizationsSection";
import { PurchaseSignalsSection } from "./components/PurchaseSignalsSection";
import { ReadinessPanel } from "./components/ReadinessPanel";
import { SyncWatermark } from "./components/SyncWatermark";
import { TabNav, type DashboardTab } from "./components/TabNav";
import {
  filterContactsForDisplay,
  selectOrganizationsForDisplay,
} from "./lib/displayFilters";
import { formatDate } from "./lib/format";

const LIST_FETCH_LIMIT = 40;

interface DashboardData {
  summary: DashboardSummary;
  archive: DashboardSummary;
  readiness: OutboundReadiness;
  contacts: PaginatedContacts;
  organizations: PaginatedOrganizations;
  classificationSummary: ClassificationSummary | null;
  classificationRecent: ClassificationRecent | null;
  classificationActions: ClassificationActions | null;
  purchaseSignals: ClassificationRecent | null;
}

export default function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [syncMeta, setSyncMeta] = useState<DashboardSyncMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<DashboardTab>("resumen");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [
          summary,
          archive,
          readiness,
          contacts,
          organizations,
          sync,
          classSummary,
          classRecent,
          classActions,
          purchases,
        ] = await Promise.all([
          fetchDashboardSummary(),
          fetchDashboardSummary("archive"),
          fetchOutboundReadiness(),
          fetchContacts(LIST_FETCH_LIMIT),
          fetchOrganizations(LIST_FETCH_LIMIT),
          fetchDashboardSyncMeta().catch(() => null),
          fetchClassificationSummary().catch(() => null),
          fetchClassificationRecent(undefined, 20).catch(() => null),
          fetchClassificationActions().catch(() => null),
          fetchClassificationRecent("purchase_or_order_signal", 20).catch(() => null),
        ]);
        if (!cancelled) {
          setData({
            summary,
            archive,
            readiness,
            contacts,
            organizations,
            classificationSummary: classSummary,
            classificationRecent: classRecent,
            classificationActions: classActions,
            purchaseSignals: purchases,
          });
          setSyncMeta(sync);
        }
      } catch (e) {
        if (!cancelled) {
          const msg =
            e instanceof ApiError
              ? `API (${e.status}): ${e.message}`
              : e instanceof Error
                ? e.message
                : "Error desconocido";
          setError(msg);
          setData(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const displayContacts = data ? filterContactsForDisplay(data.contacts.items, 5) : [];
  const orgDisplay = data
    ? selectOrganizationsForDisplay(data.organizations.items, 5)
    : { primary: [], consumer: [] };

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-6">
        <HowToReadPanel />
        <SyncWatermark syncMeta={syncMeta} />
        <TabNav active={tab} onChange={setTab} />

        {loading ? (
          <p className="text-sm text-[var(--color-muted)]" role="status">
            Cargando datos del espejo Postgres…
          </p>
        ) : null}
        {error ? (
          <div
            className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
            role="alert"
          >
            <p className="font-medium">No se pudo cargar el panel</p>
            <p className="mt-1">{error}</p>
            <p className="mt-2 text-xs">
              API: <code>{getApiBaseUrl() || "(proxy Vite en dev)"}</code> — verifique que
              FastAPI esté en ejecución y que haya ejecutado la sincronización del espejo.
            </p>
          </div>
        ) : null}
        {data ? (
          <>
            {tab === "resumen" ? (
              <>
                <KpiCards summary={data.summary} />
                <ReadinessPanel readiness={data.readiness} />
              </>
            ) : null}
            {tab === "clasificacion" ? (
              <ClassificationSection
                summary={data.classificationSummary}
                recent={data.classificationRecent}
                actions={data.classificationActions}
              />
            ) : null}
            {tab === "compras" ? (
              <PurchaseSignalsSection purchases={data.purchaseSignals} />
            ) : null}
            {tab === "contactos" ? (
              <div className="grid gap-6 lg:grid-cols-2">
                <DataTable
                  title="Contactos recientes (operativos)"
                  caption={`Total canónico en espejo: ${data.contacts.total} · sin filas internas`}
                  rows={displayContacts}
                  emptyMessage="Sin contactos recientes tras excluir filas internas."
                  columns={[
                    { key: "email", header: "Email", render: (r) => r.email },
                    {
                      key: "name",
                      header: "Nombre",
                      render: (r) => r.contact_name_best ?? "—",
                    },
                    {
                      key: "org",
                      header: "Organización",
                      render: (r) => r.organization_name_guess ?? r.domain ?? "—",
                    },
                    {
                      key: "seen",
                      header: "Último",
                      render: (r) => formatDate(r.last_seen_at),
                    },
                  ]}
                />
                <OrganizationsSection
                  primary={orgDisplay.primary}
                  consumer={orgDisplay.consumer}
                  totalCanonical={data.organizations.total}
                />
              </div>
            ) : null}
            {tab === "archivo" ? <ArchiveSection archive={data.archive} /> : null}
          </>
        ) : null}
        <footer className="border-t border-[var(--color-border)] pt-6 text-xs text-[var(--color-muted)]">
          Panel v1 · solo lectura · Streamlit sigue siendo la herramienta interna principal.
        </footer>
      </main>
    </div>
  );
}
