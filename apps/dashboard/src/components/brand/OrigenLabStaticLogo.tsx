/** Marca estática para sidebar (sin canvas). */
export function OrigenLabStaticLogo() {
  return (
    <div data-testid="origenlab-logo-static" className="flex items-center gap-3">
      <img
        src="/logo/origenlab-mark-static.svg"
        alt=""
        className="h-10 w-10 shrink-0 rounded-lg ring-1 ring-brand-700/40"
        width={40}
        height={40}
        aria-hidden
      />
      <div className="min-w-0">
        <p className="truncate text-base font-bold tracking-tight text-brand-50">OrigenLab</p>
        <p className="text-xs text-teal-200/90">Panel operador</p>
      </div>
    </div>
  );
}
