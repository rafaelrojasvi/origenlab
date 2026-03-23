# OrigenLab — Auditoría de seguridad y arquitectura v1

Status: canonical  
Owner: web-maintainers  
Last reviewed: 2026-03-23

Auditoría enfocada para el sitio estático Astro desplegado en HostGator (sin backend).

**Nota de alineación con el código:** Las secciones 2–3 y el resumen final reflejan el estado **actual** del repositorio (recursos de terceros, meta tags, implicaciones para CSP). Las tablas históricas de hallazgos más abajo se conservan con el estado **Hecho / pendiente** actualizado donde correspondía.

---

## 1. Estructura del proyecto

**Estado: adecuada para un sitio brochure/catálogo de pequeña empresa.**

- **config**: `site.ts` centraliza nombre, dominio, email, navegación. Sin complejidad innecesaria.
- **data**: `categories.ts` y `brands.ts` son datos estáticos; fáciles de extender.
- **components**: Header, Footer, Hero, QuoteCTA, PageHeader, Card. Reutilización clara.
- **layouts**: Un solo layout (`Layout.astro`) con slot. Mantenible.
- **pages**: Rutas planas (index, nosotros, productos, marcas, contacto) + `categorias/[slug]`. Coherente con sitio estático.

No se detectó complejidad innecesaria en páginas, componentes ni datos.

---

## 2. Seguridad (despliegue estático)

### Revisado y correcto

- **Sin backend**: No hay API, formularios que envíen a servidor propio ni base de datos en el sitio público. Riesgo de inyección/autenticación en el propio sitio: nulo.
- **Sin secretos en código**: No hay `process.env` / `import.meta.env` en `src/`. `.env` y `.env.production` están en `.gitignore`.
- **Scripts de terceros en el sentido de tracking**: No hay `<script src="http(s)://...">` de analytics, chat ni pixels. No hay llamadas XHR/fetch a terceros en el bundle del sitio con ese fin.
- **Recursos de terceros (tipografía)**: `Layout.astro` enlaza hojas de estilo desde **Google Fonts** (`https://fonts.googleapis.com` y `https://fonts.gstatic.com`, `preconnect` + `stylesheet`) para **Plus Jakarta Sans**. Es una **dependencia operativa** de terceros (disponibilidad y política de privacidad del proveedor). Todo por **HTTPS**; no hay mixed content en esos enlaces.
- **Enlaces en contenido**: En el cuerpo del sitio, los `href` de navegación son relativos (`/`, `/contacto`, etc.) o `mailto:contacto@origenlab.cl`. No hay redirecciones en contenido a dominios ajenos con fines de navegación.
- **Redirect interno**: Solo `Astro.redirect('/productos')` cuando no existe la categoría; destino fijo y controlado.

### Observaciones

- **CSP (Content-Security-Policy)**: Si se añade CSP en `.htaccess`, debe **permitir explícitamente** los orígenes de Google Fonts (`style-src` / `font-src` para `fonts.googleapis.com` y `fonts.gstatic.com`). Un `default-src 'self'` **sin** esas excepciones **rompería** la carga de fuentes. Además, revisar si el build de Astro requiere `'unsafe-inline'` en `style-src` para estilos críticos (comprobar en entorno de prueba antes de producción).

---

## 3. Favicon y meta

- **Favicon**: Presente en `public/favicon.svg` y referenciado en `Layout.astro` como `/favicon.svg`. Consistente en todas las páginas.
- **Meta básica**: Cada página define `title` y `description` vía el layout. `charset` UTF-8 y `viewport` correctos.
- **Canonical**: Implementado en `Layout.astro` con `link rel="canonical"` derivado de `site.baseUrl` y el path actual.
- **Open Graph y Twitter Card**: Implementados en `Layout.astro`: `og:type`, `og:locale`, `og:site_name`, `og:title`, `og:description`, `og:url`; `twitter:card`, `twitter:title`, `twitter:description`.
- **Opcional pendiente**:
  - `og:image` (mejor vista previa al compartir en redes).
  - `theme-color` para la UI del navegador.

---

## 4. Cabeceras de seguridad y HTTPS

- **Antes de la auditoría inicial**: No había orientación en el proyecto para HTTPS ni cabeceras de seguridad en HostGator.
- **Cambios realizados**:
  - Añadido `public/.htaccess` con:
    - Redirección HTTP → HTTPS (301).
    - Cabeceras: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`.
  - Actualizado `docs/deployment.md` con instrucciones para subir `.htaccess` y uso de HTTPS/cabeceras.

El `.htaccess` se copia a la raíz de `dist/` en el build; debe incluirse al subir los archivos al hosting (algunos clientes FTP ocultan archivos que empiezan por punto).

---

## 5. Información expuesta en HTML

- **Generator**: `<meta name="generator" content="…">` (valor de `Astro.generator`) expone la herramienta de build. Riesgo bajo; opcional quitarlo o dejarlo genérico si se quiere reducir fingerprinting.

---

## 6. Enlaces y redirecciones

- Enlaces internos comprobados: `/`, `/nosotros`, `/productos`, `/marcas`, `/contacto`, `/categorias/:slug`. Todas las rutas existen en el build.
- Única redirección: categoría inexistente → `/productos`. Correcta y segura.

---

## Clasificación de hallazgos

### Debe corregirse antes del lanzamiento

| # | Hallazgo | Acción |
|---|----------|--------|
| 1 | No había refuerzo de HTTPS ni cabeceras de seguridad documentadas para HostGator. | **Hecho**: añadido `public/.htaccess` y sección en `docs/deployment.md`. Verificar al desplegar que `.htaccess` sube y que HTTPS está activo en el dominio. |

No quedan ítems obligatorios pendientes para un lanzamiento estático básico.

---

### Conviene corregir pronto

| # | Hallazgo | Recomendación |
|---|----------|----------------|
| 1 | Al subir por FTP/cPanel, `.htaccess` puede no subirse si el cliente oculta archivos que empiezan por punto. | Incluir en checklist de despliegue: “Confirmar que `.htaccess` está en la raíz del sitio y que las visitas por HTTP redirigen a HTTPS”. |
| 2 | Previews sociales sin imagen dedicada. | Añadir `og:image` (URL absoluta bajo `https://origenlab.cl/...`) cuando haya recurso acordado. |

---

### Mejoras posteriores (nice to have)

| # | Hallazgo | Sugerencia |
|---|----------|------------|
| 1 | El meta `generator` expone detalle del generador. | Quitar la etiqueta o usar un valor genérico si se quiere reducir fingerprinting. |
| 2 | Política de contenido (CSP). | Diseñar CSP en staging: incluir Google Fonts y comprobar estilos del build de Astro antes de activar en producción. |
| 3 | Favicon solo en SVG. | Añadir `favicon.ico` en `public/` y enlazarlo en el layout como fallback para navegadores antiguos. |

---

## Resumen

- **Arquitectura**: Adecuada y mantenible para un sitio brochure/catálogo estático; sin complejidad innecesaria.
- **Seguridad estática**: Sin secretos en código del sitio; sin scripts de analytics/chat de terceros; enlaces de navegación y `mailto` controlados; **Google Fonts** como dependencia declarada de tipografía (HTTPS).
- **Meta y SEO social**: Canonical y Open Graph / Twitter básicos implementados en `Layout.astro`; `og:image` opcional pendiente.
- **Mejoras aplicadas**: `.htaccess` con HTTPS y cabeceras básicas; documentación de despliegue actualizada.
- **Próximos pasos recomendados**: Validar en producción HTTPS y `.htaccess`; valorar `og:image` y CSP con pruebas reales del build.
