export function ReadOnlyBanner({ mirrorBackend }: { mirrorBackend: boolean }) {
  return (
    <div
      className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"
      role="note"
    >
      <p className="font-medium">
        Read-only dashboard. Send/outreach decisions remain in the SQLite pipeline and operator
        scripts.
      </p>
      {mirrorBackend ? (
        <p className="mt-2 text-xs text-amber-900/90">
          Postgres mirror is not send/outreach truth.
        </p>
      ) : null}
    </div>
  );
}
