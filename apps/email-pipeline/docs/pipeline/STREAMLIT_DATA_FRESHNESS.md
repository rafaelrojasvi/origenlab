# Streamlit: salud de datos y vigencia

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-29

<a id="m-streamlit-freshness"></a>
## Propósito

La sección **Salud de datos** en `apps/business_mart_app.py` ayuda a comprobar si el **archivo SQLite montado** en la app refleja operación reciente y si el **mart** está alineado con el archivo crudo, **sin ejecutar ingest ni rebuilds**.

La app sigue siendo **solo lectura** sobre SQLite (salvo la página opcional de revisión comercial con variable de entorno explícita).

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

1. **Correo “viejo”:** si el último `date_iso` (prefijo de día) tiene **más de 90 días** respecto a hoy (fecha local del servidor que ejecuta Streamlit).
2. **Sin filas contacto:** si hay emails pero **ninguno** coincide con los prefijos `gmail:contacto@origenlab.cl*` ni `imap:contacto@origenlab.cl*` (si el buzón usa otra etiqueta, validar la tabla de orígenes).

<a id="m-streamlit-contacto-activity"></a>
## Actividad contacto Gmail (página relacionada)

La sección **Actividad contacto Gmail** en la misma app lista correos con `gmail:contacto@origenlab.cl%` y un resumen 7/30/90 días coherente con las mismas reglas de `date()` que la vigencia plausible. No reemplaza **Salud de datos** (sigue siendo la vista de todos los orígenes). Detalle: [`BUSINESS_MART.md`](BUSINESS_MART.md) (Streamlit UI).

<a id="m-streamlit-freshness-run"></a>
## Cómo abrir la app

Desde `apps/email-pipeline` (grupo de dependencias **`ui`**: `streamlit` + `pandas`):

```bash
uv sync --group ui   # si aún no lo tiene
uv run --group ui streamlit run apps/business_mart_app.py
```

Docker: ver [README.md](../../README.md) y `Dockerfile` (montaje de datos en `/data/origenlab-email`).

<a id="m-streamlit-freshness-limits"></a>
## Límites

- **No** prueba conectividad IMAP/Gmail.
- **No** garantiza unicidad de `message_id`.
- Comparaciones por **día** (primeros 10 caracteres de ISO); zonas horarias mixtas pueden introducir pequeños desvíos.
- Si el mart no existe, **Salud de datos** igual funciona; el resto de secciones siguen exigiendo las cuatro tablas del mart.
