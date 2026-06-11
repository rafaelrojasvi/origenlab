/** Marca estática para sidebar (sin canvas). */
export function OrigenLabStaticLogo({ compact = false }: { compact?: boolean }) {
  return (
    <div data-testid="origenlab-logo-static" className="flex items-center gap-2.5">
      <img
        src="/logo/origenlab-mark-static.svg"
        alt=""
        className={`shrink-0 rounded-lg ring-1 ring-brand-700/40 ${
          compact ? "h-8 w-8" : "h-10 w-10"
        }`}
        width={compact ? 32 : 40}
        height={compact ? 32 : 40}
        aria-hidden
      />
      <div className="min-w-0">
        <p
          className={`truncate font-bold tracking-tight text-brand-50 ${
            compact ? "text-sm" : "text-base"
          }`}
        >
          OrigenLab
        </p>
        <p className={`text-teal-200/90 ${compact ? "text-[11px]" : "text-xs"}`}>Panel operador</p>
      </div>
    </div>
  );
}
