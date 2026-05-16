export function HowToReadPanel() {
  return (
    <section
      aria-labelledby="howto-heading"
      className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-700"
    >
      <h2 id="howto-heading" className="font-semibold text-brand-900">
        Cómo leer este panel
      </h2>
      <ul className="mt-3 list-disc space-y-2 pl-5">
        <li>
          <strong>Canónico (por defecto):</strong> correo operativo{" "}
          <span className="font-medium">contacto@origenlab.cl</span> en Gmail Workspace —
          indicadores y tablas de esta vista.
        </li>
        <li>
          <strong>Archivo histórico:</strong> mart completo (PST, IMAP, legado Labdelivery, etc.);
          sección colapsable al final.
        </li>
        <li>
          <strong>Autoridad:</strong> SQLite y Gmail siguen siendo la fuente operativa;
          Streamlit es la herramienta interna principal.
        </li>
        <li>
          <strong>Postgres:</strong> espejo de solo lectura para este panel; sincronice tras
          rebuild del mart o refresh de Gmail.
        </li>
      </ul>
    </section>
  );
}
