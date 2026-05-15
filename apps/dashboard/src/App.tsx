import { useEffect, useState } from "react";
import {
  ApiError,
  fetchContacts,
  fetchDashboardSummary,
  fetchOrganizations,
  fetchOutboundReadiness,
  getApiBaseUrl,
} from "./api/client";
import type {
  DashboardSummary,
  OutboundReadiness,
  PaginatedContacts,
  PaginatedOrganizations,
} from "./api/types";
import { ArchiveSection } from "./components/ArchiveSection";
import { DataTable } from "./components/DataTable";
import { Header } from "./components/Header";
import { KpiCards } from "./components/KpiCards";
import { ReadinessPanel } from "./components/ReadinessPanel";
import { formatDate } from "./lib/format";

interface DashboardData {
  summary: DashboardSummary;
  archive: DashboardSummary;
  readiness: OutboundReadiness;
  contacts: PaginatedContacts;
  organizations: PaginatedOrganizations;
}

export default function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [summary, archive, readiness, contacts, organizations] = await Promise.all([
          fetchDashboardSummary(),
          fetchDashboardSummary("archive"),
          fetchOutboundReadiness(),
          fetchContacts(5),
          fetchOrganizations(5),
        ]);
        if (!cancelled) {
          setData({ summary, archive, readiness, contacts, organizations });
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

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-6">
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
              API: <code>{getApiBaseUrl()}</code> — verifique que FastAPI esté en ejecución y que
              haya ejecutado la sincronización del espejo.
            </p>
          </div>
        ) : null}
        {data ? (
          <>
            <KpiCards summary={data.summary} />
            <ReadinessPanel readiness={data.readiness} />
            <div className="grid gap-6 lg:grid-cols-2">
              <DataTable
                title="Contactos recientes (operativos)"
                caption={`Total canónico: ${data.contacts.total}`}
                rows={data.contacts.items}
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
              <DataTable
                title="Organizaciones recientes (operativas)"
                caption={`Total canónico: ${data.organizations.total}`}
                rows={data.organizations.items}
                columns={[
                  { key: "domain", header: "Dominio", render: (r) => r.domain },
                  {
                    key: "name",
                    header: "Nombre",
                    render: (r) => r.organization_name_guess ?? "—",
                  },
                  {
                    key: "contacts",
                    header: "Contactos",
                    render: (r) => r.total_contacts ?? "—",
                  },
                  {
                    key: "seen",
                    header: "Último",
                    render: (r) => formatDate(r.last_seen_at),
                  },
                ]}
              />
            </div>
            <ArchiveSection archive={data.archive} />
          </>
        ) : null}
        <footer className="border-t border-[var(--color-border)] pt-6 text-xs text-[var(--color-muted)]">
          Panel v0 · solo lectura · Streamlit sigue siendo la herramienta interna principal.
        </footer>
      </main>
    </div>
  );
}
