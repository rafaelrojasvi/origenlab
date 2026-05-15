# OrigenLab — Panel comercial (React v0)

Prueba de concepto de panel **solo lectura** sobre el espejo Postgres expuesto por FastAPI Slice 1.

- **No** envía correos ni escribe en bases de datos.
- **No** sustituye Streamlit (herramienta interna principal).
- **Ámbito por defecto:** Gmail operativo canónico (`contacto@origenlab.cl`).
- **Archivo completo:** sección colapsable con `?scope=archive`.

## Requisitos

- Node.js 20+
- API FastAPI en ejecución
- Espejo Postgres sincronizado desde SQLite

## 1. Postgres + API (terminal 1)

```bash
cd apps/email-pipeline
uv sync --group postgres --group api

export ORIGENLAB_POSTGRES_URL='postgresql+psycopg://user:pass@127.0.0.1:5432/origenlab_scratch'
export ORIGENLAB_SQLITE_PATH="$HOME/data/origenlab-email/sqlite/emails.sqlite"

# Una vez por base scratch:
uv run alembic -c alembic.ini upgrade head

# Tras rebuild de mart o refresh Gmail:
uv run python scripts/sync/sync_dashboard_postgres_mirror.py

uv run uvicorn origenlab_api.main:app --host 127.0.0.1 --port 8000
```

La API es **eventualmente consistente** con SQLite hasta ejecutar el sync.

## 2. Panel React (terminal 2)

```bash
cd apps/dashboard
cp .env.example .env   # opcional
npm install
npm run dev
```

Abrir [http://127.0.0.1:5173](http://127.0.0.1:5173)

### Variable de entorno

```bash
VITE_ORIGENLAB_API_BASE_URL=http://127.0.0.1:8000
```

## Pruebas y smoke

```bash
npm test
npm run smoke   # requiere API levantada
```

## Endpoints usados

| Endpoint | Uso |
|----------|-----|
| `GET /dashboard/summary` | KPIs canónicos (default) |
| `GET /dashboard/summary?scope=archive` | Comparación archivo |
| `GET /outbound/readiness` | Veredicto y advertencias |
| `GET /contacts?limit=5` | Tabla contactos |
| `GET /organizations?limit=5` | Tabla organizaciones |

OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
