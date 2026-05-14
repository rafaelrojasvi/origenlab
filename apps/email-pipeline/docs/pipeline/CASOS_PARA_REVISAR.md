# Casos para revisar (Streamlit v1)

Status: canonical  
Owner: email-pipeline-maintainers

## Qué es

Página en `apps/business_mart_app.py` que muestra una **cola operativa de mensajes** del buzón **Gmail `contacto@origenlab.cl`** (filtro `source_file` como en el resto de la app). Un fila = **`emails.id`**.

- **No** es una bandeja completa, **no** es CRM y **no** envía correos.
- La base SQLite se usa en **solo lectura** (mismo modo que el resto de exploración Streamlit).
- El **borrador comercial** se genera **solo** en la sección **Borrador comercial**; esta página solo **entrega** el `email_id` elegido.

## Alcance v1

- Solo correos con `lower(source_file) LIKE 'gmail:contacto@origenlab.cl/%'`.
- Sin agrupación por hilo.
- Sin usar `v_commercial_candidate_queue` como fuente principal de filas (la cola es a nivel mensaje).

## Fuentes de datos

- **Obligatorio:** tabla cruda `emails`.
- **Opcional:** `commercial_email_signal_fact` (inteligencia comercial v1). Si no existe, la página funciona en **modo reducido** (solo lista reciente + filtros básicos) y muestra un texto explicativo.
- **Detalle del caso:** misma prioridad de cuerpo que Borrador (`top_reply_clean` → `full_body_clean` → `body_text_clean` → `body`).
- **Conteo de documentos:** si existe `document_master`, se muestra cuántos documentos están ligados al `email_id`.

## Enriquecimiento comercial

Agregación por `email_id` sobre `commercial_email_signal_fact`:

- presencia de señal **positiva** y/o **supresión**
- intensidad máxima entre señales positivas (si aplica)

La UI muestra una **pista corta en español**; el detalle puede expandir filas de señal.

## Filtros v1

- Ventana: 7 / 30 / 90 días (por prefijo `YYYY-MM-DD` de `date_iso`).
- Excluir rebotes / DSN obvios (heurística determinista sobre remitente/asunto).
- Opcional: solo mensajes con señal positiva (solo si existe la tabla CI).

## Entrega a Borrador comercial

Se guarda `borrador_handoff_email_id` en `st.session_state`, se navega a **Borrador comercial**, y esa página:

1. Fija el origen en **Correo reciente (Gmail contacto)**.
2. Selecciona el mismo `id` en el desplegable (y asegura que aparezca en la lista vía `ensure_email_ids` en `load_contacto_gmail_email_choices_df`).
3. Elimina la clave de handoff para no repetir en bucle.

No se duplica `build_draft_package` ni la lógica de generación.

## Comandos

```bash
cd apps/email-pipeline
uv sync --group ui
uv run --group ui streamlit run apps/business_mart_app.py
```

Para enriquecimiento: `uv run python scripts/commercial/build_commercial_intel_v1.py` (ver `COMMERCIAL_INTEL_V1.md`).

## Limitaciones v1

- Mensajes sin `date_iso` parseable (menos de 10 caracteres o fuera del patrón) **no entran** en la ventana de fechas.
- La heurística de ruido no sustituye un clasificador completo.
- Titan IMAP (`imap:contacto@...`) **no** está en el alcance v1.
