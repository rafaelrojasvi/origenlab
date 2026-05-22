import type { ApiBackend } from "../api/operatorTypes";
import type { ContactDataSource } from "../api/contactTypes";
import type { EquipmentDataSource } from "../api/commercialTypes";

export function operatorBackendSourceLabel(backend: ApiBackend): string {
  if (backend === "postgres") {
    return "Postgres mirror (read-only) — not send/outreach truth";
  }
  return "SQLite live operator read model (via API)";
}

export function warmCasesSourceLabel(
  backend: ApiBackend,
  metaSource: "sqlite" | "postgres_mirror",
): string {
  if (backend === "postgres" || metaSource === "postgres_mirror") {
    return "Postgres mirror — previews only, not send/outreach truth";
  }
  return "SQLite live read model via API";
}

export function contactDataSourceLabel(
  backend: ApiBackend,
  metaSource: ContactDataSource,
): string {
  if (backend === "postgres" || metaSource === "postgres_mirror") {
    return "Postgres mirror contact intelligence — not send/outreach truth";
  }
  return "SQLite contact intelligence via API";
}

export function equipmentSourceLabel(
  backend: ApiBackend,
  metaSource: EquipmentDataSource,
): string {
  if (backend === "postgres" || metaSource === "postgres_mirror") {
    return "Postgres mirror queue — read-only, not send/outreach truth";
  }
  return "Active workspace queue via API (canonical CSV manifest)";
}
