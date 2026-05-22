import { useCallback, useEffect, useState } from "react";
import type { ContactProfileUi } from "../../api/contactTypes";
import {
  OperatorApiError,
  fetchContactProfile,
} from "../../api/operatorClient";
import type { ApiBackend } from "../../api/operatorTypes";
import { contactDataSourceLabel } from "../../lib/dataSourceLabel";

function formatContactError(e: unknown): string {
  if (e instanceof OperatorApiError) {
    if (e.status === 404) {
      return "Contact not found.";
    }
    if (e.status === 422) {
      return "Invalid email address.";
    }
    return `API ${e.status}: ${e.message}`;
  }
  if (e instanceof Error) {
    return e.message;
  }
  return "Could not load contact profile.";
}

function OutreachTruthGuide({ profile }: { profile: ContactProfileUi }) {
  const { outreach, sent_history } = profile;
  const hasState = Boolean(outreach.state?.trim());
  const hasSent = sent_history.sent_count > 0;
  const showGuide =
    outreach.do_not_repeat ||
    outreach.suppressed_email ||
    outreach.suppressed_domain ||
    (hasSent && !hasState);

  if (!showGuide) {
    return null;
  }

  return (
    <div
      className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-xs text-slate-800 space-y-2"
      role="note"
    >
      <p className="font-semibold text-slate-900">How to read outreach fields (read-only)</p>
      <ul className="list-disc pl-4 space-y-1">
        <li>
          <strong>Do not repeat / suppression</strong> — safety memory flag in SQLite; not approval
          to send from this dashboard.
        </li>
        <li>
          <strong>Sent history</strong> — summary from Gmail Sent backfill; evidence only, does not
          write outreach sidecar state.
        </li>
        <li>
          <strong>Outreach state</strong> — manual sidecar when present; empty means no row or not
          set in the pipeline (not the same as “never contacted”).
        </li>
      </ul>
      {outreach.do_not_repeat && !hasState ? (
        <p className="text-slate-700">
          {hasSent
            ? "Do not repeat is set but outreach state is empty — Sent history shows prior outbound; update sidecar truth only via pipeline scripts."
            : "Do not repeat is set but outreach state is empty — treat the flag as a safety memory; confirm in pipeline before outreach."}
        </p>
      ) : null}
    </div>
  );
}

function SuppressionBanner({ profile }: { profile: ContactProfileUi }) {
  const { outreach } = profile;
  const flags: string[] = [];
  if (outreach.do_not_repeat) {
    flags.push("Do not repeat");
  }
  if (outreach.suppressed_email) {
    flags.push("Email suppressed");
  }
  if (outreach.suppressed_domain) {
    flags.push("Domain suppressed");
  }
  if (flags.length === 0) {
    return null;
  }
  return (
    <div
      className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-950"
      role="alert"
    >
      <p className="font-semibold">Outreach restriction — read-only</p>
      <ul className="mt-1 list-disc pl-5">
        {flags.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-red-900">
        No write actions from this dashboard. Update send/outreach truth in the SQLite pipeline
        and operator scripts.
      </p>
    </div>
  );
}

export function ContactProfilePanel({
  email,
  open,
  onClose,
  backend,
  mirrorBackend,
}: {
  email: string | null;
  open: boolean;
  onClose: () => void;
  backend: ApiBackend;
  mirrorBackend: boolean;
}) {
  const [profile, setProfile] = useState<ContactProfileUi | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (targetEmail: string) => {
    setLoading(true);
    setError(null);
    setProfile(null);
    try {
      setProfile(await fetchContactProfile(targetEmail));
    } catch (e) {
      setError(formatContactError(e));
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open || !email) {
      return;
    }
    void load(email);
  }, [open, email, load]);

  if (!open || !email) {
    return null;
  }

  const showMirrorNote =
    mirrorBackend || profile?.meta.data_source === "postgres_mirror";

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="presentation">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/30"
        aria-label="Close contact profile"
        onClick={onClose}
      />
      <aside
        className="relative z-10 flex h-full w-full max-w-md flex-col border-l border-[var(--color-border)] bg-[var(--color-card)] shadow-xl"
        role="dialog"
        aria-labelledby="contact-profile-heading"
        aria-modal="true"
      >
        <header className="flex items-start justify-between gap-3 border-b border-[var(--color-border)] px-4 py-4">
          <div>
            <h2 id="contact-profile-heading" className="text-lg font-semibold text-brand-900">
              Read-only contact profile
            </h2>
            <p className="mt-1 text-xs text-[var(--color-muted)] break-all">{email}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-[var(--color-border)] px-2 py-1 text-sm text-slate-700 hover:bg-slate-50"
          >
            Close
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {showMirrorNote ? (
            <p className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
              Postgres mirror is not send/outreach truth.
            </p>
          ) : null}

          {loading ? (
            <div className="space-y-3" role="status" aria-live="polite">
              <div className="h-20 animate-pulse rounded-lg bg-slate-200/80" />
              <div className="h-32 animate-pulse rounded-lg bg-slate-100" />
            </div>
          ) : null}

          {error ? (
            <div
              className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900"
              role="alert"
            >
              <p className="font-medium">Could not load contact profile</p>
              <p className="mt-1">{error}</p>
              <button
                type="button"
                onClick={() => void load(email)}
                className="mt-3 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-50"
              >
                Retry
              </button>
            </div>
          ) : null}

          {!loading && !error && profile ? (
            <>
              <p className="text-xs text-[var(--color-muted)]">
                Data: {contactDataSourceLabel(backend, profile.meta.data_source)}
                {profile.meta.reduced_mode ? " · reduced mode" : ""}
              </p>

              <SuppressionBanner profile={profile} />

              <OutreachTruthGuide profile={profile} />

              {profile.meta.reduced_mode && profile.meta.note ? (
                <p className="text-sm text-amber-900 rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
                  {profile.meta.note}
                </p>
              ) : null}

              <section className="space-y-2">
                <h3 className="text-sm font-semibold text-slate-800">Identity</h3>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  <dt className="text-[var(--color-muted)]">Email</dt>
                  <dd className="break-all">{profile.contact.normalized_email || profile.contact.email}</dd>
                  {profile.contact.name ? (
                    <>
                      <dt className="text-[var(--color-muted)]">Name</dt>
                      <dd>{profile.contact.name}</dd>
                    </>
                  ) : null}
                  {profile.contact.organization_name ? (
                    <>
                      <dt className="text-[var(--color-muted)]">Organization</dt>
                      <dd>{profile.contact.organization_name}</dd>
                    </>
                  ) : null}
                  {profile.contact.domain || profile.contact.organization_domain ? (
                    <>
                      <dt className="text-[var(--color-muted)]">Domain</dt>
                      <dd>
                        {profile.contact.organization_domain || profile.contact.domain}
                      </dd>
                    </>
                  ) : null}
                  <dt className="text-[var(--color-muted)]">Messages</dt>
                  <dd>{profile.contact.message_count}</dd>
                  {profile.contact.first_seen_at ? (
                    <>
                      <dt className="text-[var(--color-muted)]">First seen</dt>
                      <dd>{profile.contact.first_seen_at}</dd>
                    </>
                  ) : null}
                  {profile.contact.last_seen_at ? (
                    <>
                      <dt className="text-[var(--color-muted)]">Last seen</dt>
                      <dd>{profile.contact.last_seen_at}</dd>
                    </>
                  ) : null}
                </dl>
              </section>

              <section className="space-y-2">
                <h3 className="text-sm font-semibold text-slate-800">Outreach state</h3>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  <dt className="text-[var(--color-muted)]">State</dt>
                  <dd>
                    {profile.outreach.state?.trim() ? profile.outreach.state : "— (no sidecar row)"}
                  </dd>
                  {profile.outreach.last_contacted_at ? (
                    <>
                      <dt className="text-[var(--color-muted)]">Last contacted</dt>
                      <dd>{profile.outreach.last_contacted_at}</dd>
                    </>
                  ) : null}
                  {profile.outreach.source ? (
                    <>
                      <dt className="text-[var(--color-muted)]">Source</dt>
                      <dd>{profile.outreach.source}</dd>
                    </>
                  ) : null}
                  {profile.outreach.notes ? (
                    <>
                      <dt className="text-[var(--color-muted)]">Notes</dt>
                      <dd className="text-slate-800">{profile.outreach.notes}</dd>
                    </>
                  ) : null}
                </dl>
              </section>

              <section className="space-y-2">
                <h3 className="text-sm font-semibold text-slate-800">Sent history (summary)</h3>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  <dt className="text-[var(--color-muted)]">Sent count</dt>
                  <dd>{profile.sent_history.sent_count}</dd>
                  {profile.sent_history.latest_sent_at ? (
                    <>
                      <dt className="text-[var(--color-muted)]">Latest sent</dt>
                      <dd>{profile.sent_history.latest_sent_at}</dd>
                    </>
                  ) : null}
                  {profile.sent_history.latest_subject ? (
                    <>
                      <dt className="text-[var(--color-muted)]">Latest subject</dt>
                      <dd>{profile.sent_history.latest_subject}</dd>
                    </>
                  ) : null}
                </dl>
              </section>

              {profile.warnings.length > 0 ? (
                <section className="rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-3">
                  <h3 className="text-sm font-semibold text-amber-950">Warnings</h3>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-950">
                    {profile.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </section>
              ) : null}

              {profile.contact.message_count === 0 &&
              !profile.outreach.state &&
              profile.sent_history.sent_count === 0 ? (
                <p className="text-sm text-[var(--color-muted)]" role="status">
                  Limited profile data for this address (valid email, minimal intelligence).
                </p>
              ) : null}
            </>
          ) : null}
        </div>

        <footer className="border-t border-[var(--color-border)] px-4 py-3 text-xs text-[var(--color-muted)]">
          GET /contacts/… only · no send/draft/archive actions
        </footer>
      </aside>
    </div>
  );
}
