import type { ApiBackend } from "../../api/operatorTypes";
import type { WarmCaseItem } from "../../api/commercialTypes";
import { warmCasesSourceLabel } from "../../lib/dataSourceLabel";
import { CopyTextButton } from "./CopyTextButton";
import { TableSection } from "./TableSection";

function truncate(text: string, max: number): string {
  const t = text.trim();
  if (t.length <= max) {
    return t;
  }
  return `${t.slice(0, max)}…`;
}

function MailtoLink({ email }: { email: string }) {
  const trimmed = email.trim();
  if (!trimmed || !trimmed.includes("@")) {
    return null;
  }
  return (
    <a
      href={`mailto:${encodeURIComponent(trimmed)}`}
      className="text-xs text-brand-700 underline hover:text-brand-900"
      rel="noopener noreferrer"
    >
      mailto
    </a>
  );
}

export function WarmCasesTable({
  backend,
  items,
  meta,
  loading,
  error,
  onRetry,
}: {
  backend: ApiBackend;
  items: WarmCaseItem[];
  meta: {
    data_source: "sqlite" | "postgres_mirror";
    reduced_mode: boolean;
    note: string;
    count: number;
  } | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  const sourceLabel = meta
    ? warmCasesSourceLabel(backend, meta.data_source)
    : warmCasesSourceLabel(backend, "sqlite");

  return (
    <TableSection
      title="Casos tibios / Warm cases"
      subtitle="Read-only queue · subject/snippet previews only (no email bodies)."
      dataSourceLabel={sourceLabel}
      loading={loading}
      error={error}
      onRetry={onRetry}
      empty={!loading && !error && items.length === 0}
      emptyMessage="No warm cases returned for the current filters."
      reducedNote={
        meta?.reduced_mode && meta.note
          ? `Reduced mode: ${meta.note}`
          : meta?.reduced_mode
            ? "Reduced mode: enrichment or data unavailable."
            : undefined
      }
    >
      <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-[var(--color-muted)]">
            <tr>
              <th className="px-3 py-2 font-medium">Contact</th>
              <th className="px-3 py-2 font-medium">Organization</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Category</th>
              <th className="px-3 py-2 font-medium">Last seen</th>
              <th className="px-3 py-2 font-medium">Equipment</th>
              <th className="px-3 py-2 font-medium">Subject / snippet</th>
              <th className="px-3 py-2 font-medium">Next action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--color-border)]">
            {items.map((row) => (
              <tr key={row.case_id} className="align-top hover:bg-slate-50/80">
                <td className="px-3 py-2">
                  <div className="font-medium text-slate-900">{row.contact_email || "—"}</div>
                  <div className="mt-1 flex flex-wrap gap-2">
                    <CopyTextButton label="Copy email" value={row.contact_email} />
                    <MailtoLink email={row.contact_email} />
                  </div>
                </td>
                <td className="px-3 py-2 text-slate-800">{row.account_name || "—"}</td>
                <td className="px-3 py-2">
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium uppercase">
                    {row.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs text-slate-700">{row.category}</td>
                <td className="px-3 py-2 whitespace-nowrap text-xs text-slate-600">
                  {row.last_seen_at ?? "—"}
                </td>
                <td className="px-3 py-2 text-xs text-slate-700">
                  {row.equipment_signal || "—"}
                </td>
                <td className="px-3 py-2 max-w-xs">
                  <div className="font-medium text-slate-800">{truncate(row.subject, 80)}</div>
                  {row.snippet ? (
                    <p className="mt-1 text-xs text-[var(--color-muted)]">
                      {truncate(row.snippet, 120)}
                    </p>
                  ) : null}
                </td>
                <td className="px-3 py-2 text-xs text-slate-700">{row.next_action || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="border-t border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-muted)]">
          Showing {items.length} of {meta?.count ?? items.length} cases · read-only inspect only
        </p>
      </div>
    </TableSection>
  );
}
