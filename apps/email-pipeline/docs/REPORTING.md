# Reporting — correo (HTML/JSON) y paquete leads

Status: canonical  
Owner: email-pipeline-maintainers  
Last reviewed: 2026-03-23

Un solo lugar para **cómo generar informes** y **dónde quedan**. El alcance legal/comercial del informe de correo sigue en **[REPORT_SCOPE_CLIENT.md](REPORT_SCOPE_CLIENT.md)** ([`generate_client_report.py`](../scripts/reports/generate_client_report.py) lo copia tal cual a cada carpeta como `ALCANCE_INFORME.md`).

---

<a id="m-eprep-mail"></a>
## Informe del archivo de correo (HTML + JSON)

Cada ejecución genera una **carpeta con fecha** bajo `ORIGENLAB_REPORTS_DIR` (por defecto `~/data/origenlab-email/reports/` — ver [`DATA_LOCATIONS.md`](DATA_LOCATIONS.md#m-epdata-root)).

### Qué incluye

| Artefacto | Contenido |
|-----------|-----------|
| `index.html` | Dashboard con gráficos (año, clasificación, equipos) y tablas |
| `summary.json` | Mismos datos en JSON (para Excel / BI) |
| `clusters.json` | (opcional) clusters de una muestra con embeddings |

### Clasificaciones (heurística sobre asunto + cuerpo)

- **Cotización** — `cotiz`
- **Proveedor** — palabra proveedor
- **Factura / invoice**
- **Pedido / OC** — pedido, purchase order, orden de compra
- **Universidad** — universidad, uchile, puc, utfsm, udec, .edu., etc.
- **Rebote / NDR** — mailer-daemon, delivery status, etc. (para contextualizar volumen)

### Equipamiento (menciones)

Microscopio, centrífuga, espectrofotómetro, pHmetro, autoclave, balanza, HPLC/cromatografía, incubadora, titulador, liofilizador, horno/mufla, pipetas, medidor humedad granos.

### Dominios / “quién más escribe”

- **Dominios que más envían** — dominio del `From` (proveedores / newsletters que entran).
- **Dominios en Para/Cc** — con quién se corresponde más (clientes, universidades, etc.).

En bases **muy grandes**, un barrido completo de todos los `From` tarda mucho. Use muestreo.

**Alcance y límites (ventas vs menciones):** **[REPORT_SCOPE_CLIENT.md](REPORT_SCOPE_CLIENT.md)** — copia en cada carpeta de informe como `ALCANCE_INFORME.md`.

**GPU:** Solo la fase **embeddings** usa CUDA. El escaneo SQL y el muestreo de dominios son CPU/SQLite. Si pide `--embeddings-sample`, esa fase corre **antes** del barrido de dominios para que la GPU no quede ociosa detrás de 400k filas en Python. Si sale `cuda available: False`, use `uv sync --group ml` y el índice CUDA de PyTorch ([`README.md`](../README.md)); comprobar GPU con [`check_torch_cuda.py`](../scripts/tools/check_torch_cuda.py).

### Comandos (informe correo)

```bash
# Rápido: solo totales, año, clasificación y equipos (sin tablas de dominios)
uv run python scripts/reports/generate_client_report.py --fast --name resumen_2025

# Dominios sobre muestra de 400k mensajes (recomendado en DB grande)
uv run python scripts/reports/generate_client_report.py --domain-sample 400000 --name full_mar2025

# Todo el archivo para dominios (puede ser lento)
uv run python scripts/reports/generate_client_report.py --name dominios_completos

# + muestra embeddings (requiere uv sync --group ml)
uv run python scripts/reports/generate_client_report.py --domain-sample 300000 \
  --embeddings-sample 1200 --embeddings-clusters 12 --name con_clusters
```

### Embeddings aparte (más clusters / otro filtro)

```bash
RUN=~/data/origenlab-email/reports/20250314_120000_mi_run
uv run python scripts/ml/explore_email_clusters.py --limit 2000 --filter-any --n-clusters 14 --report-dir "$RUN"
# → escribe explore_clusters.json en esa carpeta
```

### Variable de entorno

`ORIGENLAB_REPORTS_DIR` — carpeta raíz de informes (compartir con el cliente vía zip o enlace).

---

<a id="m-eprep-leads"></a>
## Leads: `active/`, paquete cliente, comandos

### Fuente de verdad

- **SQLite** (`ORIGENLAB_SQLITE_PATH`, p. ej. `~/data/origenlab-email/sqlite/emails.sqlite`) es el registro maestro: `lead_master`, `external_leads_raw`, `lead_matches_existing_orgs`, `lead_outreach_enrichment`, y el mart de correo (`organization_master`, `contact_master`, …). Mapa DDL/propiedad: [`pipeline/SCHEMA_OWNERSHIP.md`](pipeline/SCHEMA_OWNERSHIP.md#m-schema-orchestrated) (p. ej. [capa Leads](pipeline/SCHEMA_OWNERSHIP.md#m-schema-leads), [Mart](pipeline/SCHEMA_OWNERSHIP.md#m-schema-mart)).
- Ningún CSV sustituye a la base; los CSV son **vistas exportadas** o **hojas de trabajo** que pueden quedar desalineadas si no se regeneran.

### Carpetas bajo `reports/out/`

| Ubicación | Propósito |
|-----------|-----------|
| **`reports/out/active/`** | Archivos operativos **mínimos**: foco semanal, resumen MD, hoja de hunting actual, opcional `for_deepsearch`. Al ejecutar [`prepare_active_workspace.py`](../scripts/leads/prepare_active_workspace.py), otros CSV en esta carpeta se mueven a `archive/`. |
| **`reports/out/client_pack_latest/`** | **Entregable cliente**: informe estático (HTML + MD + anexo CSV). Regenerar con [`build_leads_client_pack.py`](../scripts/reports/build_leads_client_pack.py); puede sobrescribirse en cada ejecución. |
| **`reports/out/archive/`** | Históricos, limpiezas, dumps grandes (`leads_export*.csv`, etc.). |
| **`reports/out/reference/`** | Experimentos y recortes (p. ej. Deep Research de prueba). |

### Hojas de cálculo vs informe principal

- El **informe principal** para el cliente debe ser el **paquete** (`index.html` + `resumen_ejecutivo_es.md`), no una carpeta de Excel sueltos.
- **`anexo_leads.csv`** es un anexo **técnico legible** con `id_lead` para trazabilidad con la base.
- La hoja **`leads_contact_hunt_current.csv`** es para **operaciones internas** (hunting); no es el entregable narrativo.

### Comandos (leads)

```bash
# Paquete cliente (desde la raíz del repo)
uv run python scripts/reports/build_leads_client_pack.py

# Validar que merged y current comparten los mismos id_lead antes de importar
uv run python scripts/leads/validate_contact_hunt_alignment.py

# Limpiar active/ (archivar CSV que no son del núcleo)
uv run python scripts/leads/prepare_active_workspace.py
```

Más detalle del pipeline de leads: **[leads/LEAD_PIPELINE.md](leads/LEAD_PIPELINE.md)**. Vista de arquitectura: **[ARCHITECTURE.md](ARCHITECTURE.md)**, contexto de negocio: **[BUSINESS_CONTEXT.md](BUSINESS_CONTEXT.md)**.
