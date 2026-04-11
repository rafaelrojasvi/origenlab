# Catálogo OrigenLab: entrega dual (PDF prioritario + web)

## Fuentes HTML

| Archivo | Uso |
|---------|-----|
| **`catalog-pdf.html`** | **Única fuente del PDF oficial A4.** Layout y tipografía compactas, sin barra de navegación; portada y secciones densas para evitar hojas huérfanas. |
| **`OrigenLab_Catalogo_Tecnico_Editorial_Imagenes_Premium.html`** | **Web / enlace compartible:** responsive, índice sticky, secciones “continuación” donde ayuda a la lectura en pantalla. |

El contenido comercial en español es el mismo; cambia la **estructura de bloques** y el **CSS** entre ambos. Tras editar textos o datos, conviene actualizar **ambos** archivos (o mantener una lista de cambios y aplicarla en los dos).

## Cuándo enviar PDF

- Compras, licitaciones o archivo donde se espere un **documento fijo**.
- Quien prefiere **adjunto** o **impresión** sin depender del navegador.

**Salida:** `catalog-multipage.pdf` (modo Playwright **`multipage`**).

## Cuándo compartir el enlace (HTML web)

- Vista en **móvil** o pantalla sin descargar un archivo pesado.
- Iteraciones frecuentes publicando la última versión del **Premium** HTML.

El botón **Descargar PDF** del HTML web apunta a `catalog-multipage.pdf` en la misma carpeta; al publicar, sube también ese PDF generado desde `catalog-pdf.html`.

## Cómo generar el PDF oficial (A4 multipágina)

Desde `docs/origenlab-brochures/catalog-premium/`:

```bash
npm install
npx playwright install chromium
npm run pdf
```

Por defecto se usa **`catalog-pdf.html`** → **`catalog-multipage.pdf`**.

Explícito:

```bash
node export-catalog-pdf.mjs catalog-pdf.html catalog-multipage.pdf multipage
```

Desde la raíz del repositorio (asegúrate de que `catalog-pdf.html` exista en el cwd o usa ruta absoluta al HTML):

```bash
node docs/origenlab-brochures/catalog-premium/export-catalog-pdf.mjs docs/origenlab-brochures/catalog-premium/catalog-pdf.html docs/origenlab-brochures/catalog-premium/catalog-multipage.pdf multipage
```

## Vista previa local

- **PDF (HTML):** abre `catalog-pdf.html` en el navegador (misma carpeta que los assets).
- **Web:** `npm run preview` y abre `OrigenLab_Catalogo_Tecnico_Editorial_Imagenes_Premium.html`.

## Modo continuo (solo respaldo interno)

```bash
npm run pdf:continuous
```

Usa `catalog-pdf.html` y oculta la barra de navegación si existiera. No sustituye al PDF multipágina para clientes.

## Qué hace `catalog-pdf.html` frente al Premium (resumen)

- Portada en **una sola hoja:** texto “Enfoque del documento” integrado en la tarjeta de contacto; menos padding en portada; chips y lede más compactos.
- **Menos saltos forzados:** SERVA intro + productos en la **misma** `<section class="page">`; rotores BIOCEN 22 / 22 R y nota de accesorios **dentro** del mismo bloque que la ficha principal; nota regulatoria KNAUER en la **misma rejilla** que las dos tarjetas inferiores (tercera fila a ancho completo).
- **Densidad PDF:** márgenes de página, héroes, mini-stats, rejillas y `note-band` ligeramente más ajustados; listas BIOCEN pueden partir entre páginas en impresión para no generar una tercera hoja solo por `break-inside: avoid`.

## Más detalle técnico

- Notas históricas sobre tablas y paginación: **`catalog-export-notes.md`** (el HTML **web** puede seguir usando páginas de continuación; el PDF usa **`catalog-pdf.html`**).
