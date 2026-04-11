# Catálogo HTML → PDF (Playwright)

**Entrega dual (PDF prioritario + web):** **`CATALOG_DELIVERY.md`**.

## Dos HTML

- **`catalog-pdf.html`** — entrada por defecto de `export-catalog-pdf.mjs` para **`catalog-multipage.pdf`**. Estructura compacta (portada en una hoja, menos continuaciones forzadas).
- **`OrigenLab_Catalogo_Tecnico_Editorial_Imagenes_Premium.html`** — variante **web** (nav, responsive); puede seguir usando páginas “continuación” para lectura en pantalla.

## Enfoque (PDF)

Los spreads largos **no fragmentan bien** solo con CSS si los bloques tienen `break-inside: avoid` en exceso: el motor deja huecos o páginas casi vacías.

En **`catalog-pdf.html`** se combina:

- **Estructura:** menos `<section class="page">` de continuación; bloques relacionados (p. ej. ficha BIOCEN + tabla de rotores) en la misma sección para que el flujo natural ocupe mejor cada hoja.
- **CSS:** `.page` a ancho A4, márgenes y tipografía algo más densos; en impresión, tablas con `break-inside: auto` en el contenedor y control en filas; ajustes puntuales (p. ej. tarjetas de listas BIOCEN pueden partir en impresión).

El script Playwright **no inyecta CSS en modo `multipage`**: `page.pdf({ format: 'A4', printBackground: true, preferCSSPageSize: true })`.

Referencias: [overflow (MDN)](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/overflow), [Playwright Page.pdf](https://playwright.dev/docs/api/class-page#page-pdf).

## Spreads en el HTML **web** (Premium)

| Bloque | Página 1 | Página 2 |
|--------|----------|----------|
| **02 · SERVA** | Título + `two-pane` | `02 · SERVA · continuación` + **Productos destacados** |
| **04 · BIOCEN 22** | `two-pane` + tarjetas | continuación + **rotores** |
| **05 · BIOCEN 22 R** | `two-pane` + tarjetas | continuación + rotores + nota accesorios |

En **`catalog-pdf.html`** estos bloques suelen ir **fusionados** en menos secciones para el PDF (ver **`CATALOG_DELIVERY.md`**).

## Requisitos

- Node.js 18+
- Una sola vez en `catalog-premium/`:

```bash
cd docs/origenlab-brochures/catalog-premium
npm install
npx playwright install chromium
```

**Nota:** Si el prompt ya muestra `catalog-premium`, no hagas otro `cd docs/origenlab-brochures/catalog-premium` (esa ruta no existe dentro de la carpeta actual).

## Uso (multi‑página A4)

```bash
cd docs/origenlab-brochures/catalog-premium
node export-catalog-pdf.mjs catalog-pdf.html catalog-multipage.pdf multipage
```

Desde la raíz del repo (rutas explícitas recomendadas):

```bash
node docs/origenlab-brochures/catalog-premium/export-catalog-pdf.mjs docs/origenlab-brochures/catalog-premium/catalog-pdf.html docs/origenlab-brochures/catalog-premium/catalog-multipage.pdf multipage
```

Atajo: `npm run pdf`

Vista previa web (HTML + assets en `http://localhost:5501`, abrir el `.html` desde el listado): `npm run preview` (ver **`CATALOG_DELIVERY.md`**).

## Modo continuo (una sola página PDF larga)

Sin paginación A4; usa **media screen** + alto total del documento:

```bash
node export-catalog-pdf.mjs OrigenLab_Catalogo_Tecnico_Editorial_Imagenes_Premium.html catalog-continuous.pdf continuous
```

## Qué hace el script

1. Sirve la carpeta del HTML por HTTP (assets relativos OK).
2. Carga la página, espera red e imágenes.
3. **`multipage`:** PDF A4, fondos activos, sin inyección de estilos.
4. **`continuous`:** `emulateMedia('screen')`, viewport ancho, mide `scrollWidth` / `scrollHeight`, PDF con esas dimensiones en px.

## Salida en git

`node_modules/` suele ignorarse. Añade `*.pdf` si no quieres commitear exports.
