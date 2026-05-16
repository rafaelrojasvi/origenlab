import type { OrganizationRow } from "../api/types";
import { formatDate } from "../lib/format";
import { DataTable } from "./DataTable";

interface Props {
  primary: OrganizationRow[];
  consumer: OrganizationRow[];
  totalCanonical: number;
}

export function OrganizationsSection({ primary, consumer, totalCanonical }: Props) {
  return (
    <div className="space-y-4">
      <DataTable
        title="Organizaciones recientes (operativas)"
        caption={`Total canónico en espejo: ${totalCanonical} · sin dominios internos ni correo personal en esta tabla`}
        rows={primary}
        emptyMessage="Sin organizaciones recientes tras filtrar dominios internos y personales."
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
      {consumer.length > 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/80 px-4 py-3">
          <p className="text-sm font-medium text-slate-700">Correos personales agrupados</p>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            Dominios de correo genérico (Gmail, Outlook, etc.) no se muestran en la tabla principal.
          </p>
          <ul className="mt-2 flex flex-wrap gap-2 text-xs text-slate-600">
            {consumer.map((o) => (
              <li
                key={o.domain}
                className="rounded-md border border-slate-200 bg-white px-2 py-1"
              >
                {o.domain}
                {o.total_contacts != null ? ` (${o.total_contacts})` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
