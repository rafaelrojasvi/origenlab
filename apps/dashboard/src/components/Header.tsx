export function Header() {
  return (
    <header className="border-b border-[var(--color-border)] bg-[var(--color-card)]">
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <p className="text-sm font-medium uppercase tracking-wide text-brand-600">
          OrigenLab
        </p>
        <h1 className="mt-1 text-2xl font-semibold text-brand-900 sm:text-3xl">
          Panel comercial
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-[var(--color-muted)]">
          Fuente operativa:{" "}
          <span className="font-medium text-slate-800">contacto@origenlab.cl</span>
          {" · "}
          Gmail Workspace
        </p>
        <p className="mt-1 text-xs text-[var(--color-muted)]">
          Vista de solo lectura (v0) · ámbito operativo canónico por defecto
        </p>
      </div>
    </header>
  );
}
