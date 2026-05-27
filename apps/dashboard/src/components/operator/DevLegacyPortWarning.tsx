import { LEGACY_DEV_PORT_WARNING } from "../../lib/devApiConfig";

export function DevLegacyPortWarning({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg border border-orange-300 bg-orange-50 px-4 py-3 text-sm text-orange-950"
      role="alert"
    >
      <p className="font-medium">Configuración local incorrecta</p>
      <p className="mt-1">{message || LEGACY_DEV_PORT_WARNING}</p>
      <p className="mt-2 text-xs text-orange-900">
        Quite o comente <code className="text-orange-950">VITE_ORIGENLAB_API_BASE_URL</code> en{" "}
        <code className="text-orange-950">apps/dashboard/.env</code> y reinicie{" "}
        <code className="text-orange-950">npm run dev</code>. Vite enviará las llamadas API al puerto{" "}
        <strong>8001</strong>.
      </p>
    </div>
  );
}
