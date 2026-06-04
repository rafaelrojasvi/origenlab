# Salud de datos y vigencia (referencia histórica Streamlit)

Status: canonical (concepts); **Streamlit UI removed 2026-06-04**
Owner: email-pipeline-maintainers  
Last reviewed: 2026-06-04

> **Active operator UI:** [`apps/dashboard`](../../../dashboard/README.md) + [`apps/api`](../../../api/README.md) (:8001) over the Postgres mirror. This doc preserves the **Salud de datos** heuristics that lived in the removed Streamlit app. Launch inventory: [`audits/STREAMLIT_LAUNCH_SURFACE_REMOVAL_PLAN_20260604.md`](../audits/STREAMLIT_LAUNCH_SURFACE_REMOVAL_PLAN_20260604.md).

<a id="m-streamlit-freshness"></a>
## Propósito

La sección **Salud de datos** (antes en `apps/business_mart_app.py`, **eliminada**) ayudaba a comprobar si el **archivo SQLite** refleja operación reciente y si el **mart** está alineado con el archivo crudo, **sin ejecutar ingest ni rebuilds**.

Operadores hoy usan el dashboard + mirror para lectura; diagnósticos profundos siguen en SQLite vía CLIs y SQL directo ([`RUNBOOK.md`](../RUNBOOK.md)).

<a id="m-streamlit-nav"></a>
## Navegación (histórico)

El panel Streamlit usaba un menú lateral en español (**Inicio**, **Herramientas / Runbook**, etc.). Esa UI fue retirada; no hay `streamlit run` en este repo.

<a id="m-streamlit-freshness-what"></a>
## Qué muestra

| Bloque | Significado |
|--------|--------------|
| **Ruta SQLite** | Resuelta por `ORIGENLAB_SQLITE_PATH` / `ORIGENLAB_DATA_ROOT` (ver [DATA_LOCATIONS.md](../DATA_LOCATIONS.md)). |
| **Conteos** | `emails`, adjuntos, extracts y tablas del mart (si existen). |
| **min/max date_iso** | Cobertura del archivo crudo; **`max` absoluto** puede incluir fechas imposibles (p. ej. cabeceras mal parseadas → año 2033). |
| **max plausible** | `MAX(date_iso)` entre filas donde `date(date_iso)` en SQLite es **NULL** (no parseable) o **≤ hoy + 2 días**. Excluye fechas “futuras sospechosas” para vigencia. |
| **filas futuras sospechosas** | `COUNT` donde `date(date_iso) > date('now', '+2 days')`. Si es mayor que 0, la UI muestra aviso y **no** usa el máximo absoluto para comparar con el mart. |
| **Origen (`source_file`)** | Etiquetas de ingest (`gmail:...`, `imap:...`, rutas mbox, etc.). |
| **contacto@** | Conteos para prefijos `gmail:contacto@origenlab.cl` e `imap:contacto@origenlab.cl` (comparación en minúsculas). |
| **Mart vs crudo** | Compara el **prefijo de fecha YYYY-MM-DD** del último `date_iso` en `emails` con el **máximo** de las fechas disponibles en `contact_master.last_seen_at`, `organization_master.last_seen_at`, `document_master.sent_at` y `opportunity_signals.created_at`. |
| **pipeline_kv / pipeline_run** | Metadatos si las tablas existen (p. ej. claves recientes, últimas corridas de `build_business_mart.py`). |

<a id="m-streamlit-freshness-judgement"></a>
## Juicio «fresh / stale / unknown»

- **fresh**: el “pico” de fechas del mart (prefijos normalizados) es **≥** el prefijo del último `date_iso` **plausible** del archivo (no el absoluto si hay fechas futuras sospechosas).
- **stale**: el pico del mart es **anterior** a ese prefijo plausible. Suele indicar **ingest nuevo sin `build_business_mart`** (o mart obsoleto).
- **unknown**: faltan fechas en crudo o en mart, tablas vacías, o **no hay máximo plausible** (p. ej. todas las fechas parseables están en el futuro).

### Fechas futuras / corruptas

SQLite aplica **`date(date_iso)`** al campo. Valores que parsean a una fecha **posterior a hoy + 2 días** se cuentan como sospechosos. No se modifica la base: solo lectura y agregados en la UI.

**Límites:** filas con `date_iso` que SQLite **no** puede convertir con `date()` siguen pudiendo aparecer en el máximo plausible (`date(date_iso) IS NULL`); no se cuentan como “futuras” en ese contador. Para auditoría profunda usar SQL directo sobre el archivo.


No se infieren horas de ejecución de ingest: para eso hay que fiarse de procedimientos (`RUNBOOK.md`) o de `pipeline_run` cuando exista.

<a id="m-streamlit-freshness-warnings"></a>
## Advertencias mostradas

1. **Correo “viejo”:** si el último `date_iso` (prefijo de día) tiene **más de 90 días** respecto a hoy (fecha local del entorno que evalúa SQLite).
2. **Sin filas contacto:** si hay emails pero **ninguno** coincide con los prefijos `gmail:contacto@origenlab.cl*` ni `imap:contacto@origenlab.cl*` (si el buzón usa otra etiqueta, validar la tabla de orígenes).

<a id="m-streamlit-contacto-activity"></a>
## Actividad contacto Gmail (página relacionada)

La sección **Actividad contacto Gmail** en la misma app lista correos con `gmail:contacto@origenlab.cl/%` (equivalente SQL: `lower(source_file) LIKE 'gmail:contacto@origenlab.cl/%'`) y un resumen 7/30/90 días coherente con las mismas reglas de `date()` que la vigencia plausible. No reemplaza **Salud de datos** (sigue siendo la vista de todos los orígenes). Detalle: [`BUSINESS_MART.md`](BUSINESS_MART.md).

<a id="m-streamlit-freshness-run"></a>
## Cómo operar hoy (sin Streamlit)

1. **Dashboard:** `cd apps/dashboard && npm run dev` (lee [`apps/api`](../../../api/README.md) :8001 + mirror Postgres).
2. **SQLite truth / mart:** `cd apps/email-pipeline` → `uv run origenlab status`, `uv run python scripts/mart/build_business_mart.py` según [`RUNBOOK.md`](../RUNBOOK.md).
3. **Mismas agregaciones:** SQL directo sobre `ORIGENLAB_SQLITE_PATH` usando las tablas descritas arriba.

No existe `apps/business_mart_app.py` ni imagen Docker Streamlit en el repo (ver [`audits/ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md`](../audits/ACTIVE_STACK_AND_STREAMLIT_RETIREMENT_PLAN_20260604.md)).

<a id="m-streamlit-freshness-limits"></a>
## Límites

- **No** prueba conectividad IMAP/Gmail.
- **No** garantiza unicidad de `message_id`.
- Comparaciones por **día** (primeros 10 caracteres de ISO); zonas horarias mixtas pueden introducir pequeños desvíos.
- Si el mart no existe, **Salud de datos** igual funciona; el resto de secciones siguen exigiendo las cuatro tablas del mart.
