import { useMemo } from "react";
import { useDashboardData } from "../context/DashboardDataContext";
import { ContactEmailButton } from "../components/commercial/ContactEmailButton";

export function ContactsPage() {
  const { warm, equipment, setContactEmail } = useDashboardData();

  const contactEmails = useMemo(() => {
    const emails = new Set<string>();
    for (const row of warm?.items ?? []) {
      if (row.contact_email?.trim()) {
        emails.add(row.contact_email.trim().toLowerCase());
      }
    }
    for (const row of equipment?.items ?? []) {
      if (row.contact_email?.trim()) {
        emails.add(row.contact_email.trim().toLowerCase());
      }
    }
    return [...emails].sort();
  }, [warm?.items, equipment?.items]);

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-5 py-5 shadow-sm">
      <h2 className="text-lg font-semibold text-brand-900">Contacts</h2>
      <p className="mt-1 text-sm text-[var(--color-muted)]">
        Read-only profiles from loaded warm cases and equipment rows. No compose or send actions.
      </p>
      {contactEmails.length === 0 ? (
        <p className="mt-4 text-sm text-[var(--color-muted)]" role="status">
          No contact emails in the current load. Refresh after mirror sync.
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-[var(--color-border)] rounded-lg border border-[var(--color-border)]">
          {contactEmails.map((email) => (
            <li key={email} className="px-4 py-3">
              <ContactEmailButton email={email} onSelect={setContactEmail} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
