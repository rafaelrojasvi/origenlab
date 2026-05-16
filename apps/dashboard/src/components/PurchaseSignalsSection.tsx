import type { ClassificationEmailRow, ClassificationRecent } from "../api/types";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { DataTable } from "./DataTable";

interface Props {
  purchases: ClassificationRecent | null;
}

export function PurchaseSignalsSection({ purchases }: Props) {
  const items = purchases?.items ?? [];

  if (!purchases?.table_available) {
    return (
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-6 text-sm text-[var(--color-muted)]">
        Señales de compra no disponibles en el espejo (tabla de clasificación ausente).
      </section>
    );
  }

  if (items.length === 0) {
    return (
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-6">
        <h2 className="text-lg font-semibold text-brand-900">Compras / clientes recientes</h2>
        <p className="mt-3 text-sm text-[var(--color-muted)]">
          No hay señales de compra reciente detectadas en el espejo actual.
        </p>
        <p className="mt-2 text-xs text-[var(--color-muted)]">
          La detección es heurística (orden de compra, OC, factura, etc.) y no confirma que la
          empresa haya comprado sin revisar el correo.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-brand-900">Compras / clientes recientes</h2>
        <p className="text-sm text-[var(--color-muted)]">
          Posibles señales de compra u orden en Gmail canónico. Requiere revisión humana antes de
          tratarlo como cliente activo.
        </p>
      </div>
      <DataTable<ClassificationEmailRow>
        title="Señales detectadas"
        caption="Etiqueta heurística: posible compra / orden"
        rows={items}
        emptyMessage="No hay señales de compra reciente detectadas en el espejo actual."
        columns={[
          {
            key: "domain",
            header: "Empresa / dominio",
            render: (r) => r.contact_domain ?? "—",
          },
          {
            key: "email",
            header: "Contacto",
            render: (r) => r.contact_email ?? "—",
          },
          {
            key: "date",
            header: "Fecha",
            render: (r) => (r.date_iso ? r.date_iso.slice(0, 16) : "—"),
          },
          { key: "subject", header: "Asunto", render: (r) => r.subject ?? "—" },
          {
            key: "evidence",
            header: "Evidencia",
            render: (r) => r.evidence ?? "—",
          },
          {
            key: "conf",
            header: "Confianza",
            render: (r) => <ConfidenceBadge confidence={r.confidence} />,
          },
          {
            key: "action",
            header: "Acción sugerida",
            render: () => "Revisar cliente activo",
          },
        ]}
      />
    </section>
  );
}
