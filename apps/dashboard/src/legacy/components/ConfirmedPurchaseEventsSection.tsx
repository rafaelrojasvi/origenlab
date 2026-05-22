import type { CommercialPurchaseEventsList } from "../api/types";
import { formatClp } from "../lib/format";
import { DataTable } from "./DataTable";

export type ConfirmedLoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: CommercialPurchaseEventsList };

interface Props {
  confirmed: ConfirmedLoadState;
}

type LineRow = CommercialPurchaseEventsList["items"][number]["line_items"][number] & {
  _org: string;
  _oc: string;
};

function displayOrgName(name: string): string {
  if (name.length > 48) return `${name.slice(0, 45)}…`;
  return name;
}

export function ConfirmedPurchaseEventsSection({ confirmed }: Props) {
  return (
    <section className="space-y-4" aria-labelledby="confirmed-purchase-heading">
      <div>
        <h3 id="confirmed-purchase-heading" className="text-base font-semibold text-brand-900">
          Órdenes de compra confirmadas
        </h3>
        <p className="text-sm text-[var(--color-muted)]">
          Eventos promovidos desde Gmail/SQLite (no heurística). Requieren seguimiento operativo.
        </p>
      </div>

      {confirmed.status === "loading" ? (
        <p className="text-sm text-[var(--color-muted)]" role="status">
          Cargando órdenes de compra confirmadas…
        </p>
      ) : null}

      {confirmed.status === "error" ? (
        <div
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
          role="alert"
        >
          <p className="font-medium">No se pudieron cargar las OC confirmadas</p>
          <p className="mt-1">{confirmed.message}</p>
          <p className="mt-2 text-xs">
            En desarrollo, Vite debe hacer proxy de <code>/commercial</code> hacia FastAPI. Compruebe
            que el API expone <code>GET /commercial/purchase-events</code>.
          </p>
        </div>
      ) : null}

      {confirmed.status === "ready" ? (
        <ConfirmedPurchaseList data={confirmed.data} />
      ) : null}
    </section>
  );
}

function ConfirmedPurchaseList({ data }: { data: CommercialPurchaseEventsList }) {
  const items = data.items ?? [];

  if (!data.table_available) {
    return (
      <p className="text-sm text-[var(--color-muted)]">
        Tabla de OC confirmadas no disponible en el espejo Postgres (ejecute migración Alembic y
        sync del dashboard).
      </p>
    );
  }

  if (items.length === 0) {
    return (
      <p className="text-sm text-[var(--color-muted)]">
        No hay órdenes de compra confirmadas en el espejo. Promueva un correo con{" "}
        <code>promote_purchase_order_event.py --apply</code> y vuelva a sincronizar Postgres.
      </p>
    );
  }

  const lineRows: LineRow[] = items.flatMap((ev) =>
    ev.line_items.map((li) => ({
      ...li,
      _org: displayOrgName(ev.buyer_org_name),
      _oc: ev.oc_number,
    })),
  );

  return (
    <>
      <div className="space-y-4">
        {items.map((ev) => (
          <article
            key={ev.id}
            className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-5 shadow-sm"
          >
            <header className="flex flex-wrap items-baseline justify-between gap-2">
              <h4 className="text-base font-semibold text-brand-900">
                {displayOrgName(ev.buyer_org_name)} — OC {ev.oc_number}
              </h4>
              <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-900">
                Estado: {ev.purchase_status_label_es || ev.purchase_status}
              </span>
            </header>
            <p className="mt-1 text-xs text-[var(--color-muted)]">{ev.buyer_org_name}</p>
            {ev.buyer_contact_name || ev.buyer_contact_email ? (
              <p className="text-xs text-[var(--color-muted)]">
                {[ev.buyer_contact_name, ev.buyer_contact_email].filter(Boolean).join(" · ")}
              </p>
            ) : null}
            <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <dt className="text-xs text-[var(--color-muted)]">Neto</dt>
                <dd className="font-medium text-brand-900">{formatClp(ev.net_amount_clp)}</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-muted)]">Total bruto</dt>
                <dd className="font-medium text-brand-900">{formatClp(ev.gross_amount_clp)}</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-muted)]">Cotización</dt>
                <dd className="font-medium text-brand-900">{ev.quote_number ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-[var(--color-muted)]">Proyecto</dt>
                <dd className="font-medium text-brand-900">
                  {ev.project_code
                    ? `${ev.project_name ?? ""} ${ev.project_code}`.trim()
                    : "—"}
                </dd>
              </div>
              <div className="sm:col-span-2 lg:col-span-3">
                <dt className="text-xs text-[var(--color-muted)]">Productos</dt>
                <dd className="font-medium text-brand-900">{ev.product_summary || "—"}</dd>
              </div>
            </dl>
            {ev.suggested_action_es ? (
              <p className="mt-3 text-sm text-brand-800">
                <span className="font-medium">Acción sugerida:</span> {ev.suggested_action_es}
              </p>
            ) : null}
          </article>
        ))}
      </div>
      {lineRows.length > 0 ? (
        <DataTable<LineRow>
          title="Detalle de líneas (OC confirmadas)"
          caption={data.disclaimer}
          rows={lineRows}
          emptyMessage="Sin líneas."
          columns={[
            { key: "org", header: "Cliente", render: (r) => r._org },
            { key: "oc", header: "OC", render: (r) => r._oc },
            { key: "product", header: "Producto", render: (r) => r.product_name },
            { key: "brand", header: "Marca", render: (r) => r.brand ?? "—" },
            {
              key: "net",
              header: "Neto",
              render: (r) => formatClp(r.net_amount_clp),
            },
          ]}
        />
      ) : null}
    </>
  );
}
