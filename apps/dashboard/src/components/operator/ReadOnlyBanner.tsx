export function ReadOnlyBanner({ mirrorBackend }: { mirrorBackend: boolean }) {
  return (
    <div
      className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"
      role="note"
    >
      <p className="font-medium">
        Panel de solo lectura. Las decisiones de envío y contacto se toman en el pipeline SQLite y
        con scripts del operador.
      </p>
      {mirrorBackend ? (
        <p className="mt-2 text-xs text-amber-900/90">
          El espejo Postgres no autoriza envíos ni define el estado de contacto.
        </p>
      ) : null}
    </div>
  );
}
