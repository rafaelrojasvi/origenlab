# OrigenLab — Panel comercial (React v1)

Panel **solo lectura** sobre el espejo Postgres servido por FastAPI. No envía correos, no escribe en bases de datos y no sustituye Streamlit.

**Flujo de datos (resumen):** Gmail → ingest → SQLite → mart/clasificación → sync → Postgres → FastAPI → este panel.

Documentación operador completa: [`../email-pipeline/docs/RUNBOOK.md#m-eprun-dashboard-gmail-to-react`](../email-pipeline/docs/RUNBOOK.md#m-eprun-dashboard-gmail-to-react) · [`../email-pipeline/docs/OPERATOR_CHEAT_SHEET.md`](../email-pipeline/docs/OPERATOR_CHEAT_SHEET.md)

## Qué actualiza solo y qué no

| Capa | ¿Se actualiza sola? |
|------|---------------------|
| Gmail | Sí (Google) |
| SQLite (correos, mart) | **No** — requiere ingest + rebuild mart |
| Postgres (espejo dashboard) | **No** — requiere `sync_dashboard_postgres_mirror.py` |
| FastAPI / React | **No** — solo leen el último sync |

**Correos nuevos en Gmail no aparecen aquí** hasta ejecutar ingest, rebuild del mart y sync del espejo (ver RUNBOOK).

## Requisitos

- Node.js 20+
- FastAPI en ejecución (`apps/email-pipeline`)
- Postgres con migraciones Alembic y sync reciente
- SQLite operativo con Gmail canónico ingestado

## Arranque rápido (dos terminales)

**Terminal 1 — API** (desde `apps/email-pipeline`):

```bash
uv sync --group gmail --group postgres --group api
export ORIGENLAB_POSTGRES_URL='postgresql+psycopg://user:pass@127.0.0.1:5432/origenlab_scratch'
export ORIGENLAB_SQLITE_PATH="$HOME/data/origenlab-email/sqlite/emails.sqlite"

uv run alembic -c alembic.ini upgrade head
uv run python scripts/sync/sync_dashboard_postgres_mirror.py   # tras mart rebuild / ingest

uv run uvicorn origenlab_api.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — React** (desde `apps/dashboard`):

```bash
npm install
npm run dev -- --host 127.0.0.1
```

Abrir [http://127.0.0.1:5173](http://127.0.0.1:5173). En dev, Vite hace proxy a FastAPI (mismo origen; ver `vite.config.ts`).

## Refresco de datos de hoy

Orden obligatorio (detalle en RUNBOOK):

1. Comprobar SQLite: `sqlite3 "$ORIGENLAB_SQLITE_PATH" "SELECT MAX(date_iso) FROM emails WHERE source_file LIKE 'gmail:contacto@origenlab.cl/%';"`
2. Ingest Gmail INBOX + Enviados
3. `build_business_mart.py --rebuild` + `refresh_outbound_safety_memory.py`
4. `sync_dashboard_postgres_mirror.py`
5. Recargar el panel (API ya debe estar arriba)

## Smoke API

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/dashboard/summary
curl -sS http://127.0.0.1:8000/meta/dashboard-sync
curl -sS http://127.0.0.1:8000/classification/summary
```

Comprobar: `scope` canónico por defecto; marca de sync en React ≈ `finished_at` del API; conteos canónicos mucho menores que archivo (`?scope=archive`).

## Ámbito y pestañas

- **Por defecto:** Gmail operativo `contacto@origenlab.cl` (canónico).
- **Archivo histórico:** pestaña separada / `?scope=archive` en API — no es el KPI principal.
- Pestañas: Resumen · Clasificación comercial · Compras/clientes · Contactos · Archivo.

Clasificación y compras son **heurísticas de QA**, no verdad CRM.

## Endpoints usados

| Endpoint | Uso |
|----------|-----|
| `GET /dashboard/summary` | KPIs canónicos |
| `GET /meta/dashboard-sync` | Última sync del espejo |
| `GET /classification/summary` | KPIs clasificación |
| `GET /classification/recent` | Tabla correos clasificados |
| `GET /classification/actions` | Acciones sugeridas |
| `GET /outbound/readiness` | Preparación espejo |
| `GET /contacts`, `/organizations` | Listados |

OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Variables de entorno

```bash
# Producción / preview build:
VITE_ORIGENLAB_API_BASE_URL=http://127.0.0.1:8000
```

En `npm run dev`, el proxy Vite usa `VITE_ORIGENLAB_API_BASE_URL` o `http://127.0.0.1:8000` por defecto.

## Pruebas

```bash
npm test
npm run build
npm run smoke   # requiere API levantada
```

## Problemas frecuentes

| Síntoma | Acción |
|---------|--------|
| Failed to fetch | Levantar FastAPI; usar proxy en dev |
| Conteos en cero | Migrar Alembic + sync Postgres |
| Datos viejos | Ingest + mart + sync (ver RUNBOOK) |
| KPIs de archivo en portada | Bug de scope — debe ser canónico |
