# Alcance y datos de OrigenLab (brief / cotizaciones)

Status: canonical  
Owner: web-maintainers  
Last reviewed: 2026-03-24

Documento de referencia para copy, IA y redacción de cotizaciones. **Fuente de verdad en código:** `src/data/company.ts`, `src/data/contact.ts`, `src/data/services.ts`, `src/data/categories.ts`. Este doc resume y centraliza para humanos y prompts externos (p. ej. ChatGPT).

**Reglas comerciales formales del monorepo** (cotizaciones, proveedores, datos maestros vs campaña, qué no afirmar sin confirmación): [`docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md`](../../../docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md).

---

## Datos confirmados de la empresa

| Campo | Valor |
|-------|--------|
| **Empresa** | OrigenLab |
| **País / cobertura** | Chile (atención en todo Chile) |
| **Base** | Valdivia, Chile |
| **Oferta principal** | Venta de equipos para laboratorios de servicio e investigación |
| **Líneas de producto** | Alimentos · Control de calidad · Laboratorio clínico |
| **Familia editorial (equipos)** | Centrífugas Ortoalresa: Biocen 22, Biocen 22 R, Consul 22, Digicen 22, Digicen 22 R — cotización vía OrigenLab |
| **Audiencia típica** | Laboratorios de servicios e investigación, universidades, clínicas, hospitales, industrias de I+D |
| **Catálogos / fichas** | Catálogos y fichas técnicas disponibles según línea de producto. Contáctenos para evaluar la alternativa adecuada para su laboratorio. |

---

## Contacto (uso en sitio y en cotizaciones)

| Campo | Valor |
|-------|--------|
| **Email** | contacto@origenlab.cl |
| **Teléfono / WhatsApp** | +56 9 6256 7816 |
| **Horario** | 09:00–18:00 |
| **Ubicación pública** | Valdivia, Chile *(no incluir calle en material público)* |

---

## Servicios / postventa (sin prometer de más)

- **Soporte:** Respuesta a dudas de uso y coordinación cuando el equipo lo requiere.
- **Asesorías:** Ayuda para acotar opciones antes de comprar; sin compromiso de compra.
- **Garantía:** Según fabricante y condiciones del equipo; detalle en cotización.
- **Instalación:** Cuando el equipo lo exige; alcance acordado por escrito.
- **Puesta en marcha:** Equipos más complejos; según equipo y acuerdo comercial.

---

## Ortoalresa (centrífugas)

- **Marca:** Ortoalresa (Álvarez Redondo S.A.) — fabricante europeo de centrífugas; datos según ficha del fabricante.
- **Catálogo activo:** Biocen 22, Biocen 22 R, Consul 22, Digicen 22, Digicen 22 R (`/productos/centrifugas/...`). **Bioprocen 22 R** retirado del catálogo público.
- **Inicio:** SERVA y Ortoalresa al mismo nivel en «Marcas y líneas disponibles» (sin jerarquía «marca destacada»).
- **WhatsApp:** botón «Cotizar por WhatsApp» con mensaje prefilled (`src/lib/whatsapp.ts`).
- **Copy:** cotización y disponibilidad sujetas a confirmación comercial; **no** afirmar representación exclusiva.
- **Activos:** [`product-assets.md`](product-assets.md).

---

## Restricciones (crítico para copy y cotizaciones)

**No inventar:** marcas, certificaciones, alianzas, plazos, stock, SLA, garantías específicas, especificaciones técnicas no entregadas en la fuente. Si falta un dato, usar placeholder claro o preguntar. La regla maestra del proyecto (incl. plantillas y futuras herramientas) está en [`BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md`](../../../docs/business/BUSINESS_RULES_QUOTES_AND_SUPPLIERS.md#1-project-wide-truth-rule-non-negotiable).

---

## Datos a solicitar (operativo)

Listas de verificación para **completar** una cotización o una consulta a fabricante/proveedor. No son promesas comerciales: son lo mínimo que conviene **preguntar** para evitar retrabajo. **Alinear** con las plantillas internas (ficha cliente, cotización vacía, ejemplos ya usados en Word).

### Cuando el cliente pide cotización

- **Quién compra:** razón social o nombre, RUT, contacto (nombre, cargo, email, teléfono).
- **Entrega / facturación:** ciudad, dirección o al menos región; si requiere despacho distinto a facturación.
- **Qué necesita:** tipo de equipo o línea (ej. balanza, microscopio, incubadora), uso o aplicación (qué van a hacer en el laboratorio).
- **Requisitos técnicos** (si el cliente los conoce): capacidad, rango de medición, resolución, norma o método asociado, accesorios o consumibles incluidos deseados.
- **Cantidad** y, si aplica, si hay **varias líneas** o alternativas a comparar.
- **Plazo:** cuándo lo necesitan operativo (fecha límite o urgencia relativa).
- **Condiciones comerciales deseadas** (solo para entender expectativas; lo acordado va por escrito): moneda, forma de pago aproximada; **no** comprometer plazos ni garantías que no estén confirmados con proveedor/fabricante.

### Cuando se consulta a proveedor o fabricante

- **Identificación del producto:** código / part number / modelo exacto; si es alternativa, describir equivalencia requerida.
- **Precio:** moneda, vigencia de la oferta, si incluye flete nacional o es EXW/otro (según corresponda).
- **Plazo de entrega:** stock disponible vs fabricación bajo pedido; ventana razonable.
- **Documentación:** manual, certificados si aplican, requisitos de importación si el equipo viene del extranjero.
- **Garantía** según fabricante y **alcance** (quién atiende en Chile si aplica).
- **Logística:** peso/volumen embalado si sirve para cotizar flete; requisitos especiales (instalación, voltage, consumibles obligatorios).

---

## Tono y estilo

- Español (Chile), profesional, técnico-creíble, sin hype.
- Corto y claro. CTAs: «Solicitar cotización», «Contactar por WhatsApp».
- Evitar: «líder», «mejor del mercado», «garantizado», etc.

---

## Identidad visual (documentos / PDF)

- **Tipografía:** Plus Jakarta Sans (sans-serif).
- **Paleta teal:** Brand 700 `#0f766e` (principal), 800 `#115e59`, 900 `#134e4a`, 600 `#0d9488`, 500 `#14b8a6`, 50 `#f0fdfa` (fondos).
- Estilo: limpio B2B, fondos blancos + acentos teal; botones/CTA en brand-700.

---

## Prompt para reescribir cotizaciones (ChatGPT / otra IA)

Copiar el bloque siguiente y pegar debajo el texto original de la cotización.

```text
Actúa como redactor/a comercial B2B para OrigenLab (Chile). Reescribe la cotización que pego abajo para alinearla a la marca y restricciones de OrigenLab, sin inventar información.

Usa estos datos tal cual:
- Empresa: OrigenLab. Base: Valdivia, Chile. Cobertura: todo Chile.
- Oferta: venta de equipos para laboratorios de servicio e investigación. Líneas: alimentos, control de calidad, laboratorio clínico.
- Audiencia: laboratorios de servicios e investigación, universidades, clínicas, hospitales, industrias de I+D.
- Catálogos/fichas: disponibles según línea; contactar para evaluar la alternativa adecuada.
- Servicios: soporte, asesorías, garantía según fabricante (detalle en cotización), instalación y puesta en marcha cuando el equipo lo requiera (alcance por escrito).
- NO inventes: marcas, certificaciones, plazos, stock, SLA, garantías específicas ni especificaciones no dadas. Si falta algo, usa placeholder o pregunta.
- Si el borrador omite datos del cliente o del equipo, sugiere en un apartado breve «Datos pendientes de confirmar» usando la lista «Datos a solicitar (operativo)» de este mismo documento (sección para cliente y, si aplica, lo que faltaría pedir al proveedor).
- Contacto en la cotización: contacto@origenlab.cl, +56 9 6256 7816, 09:00–18:00, Valdivia Chile (sin calle).
- Tono: español Chile, profesional, sin hype. Estilo visual: Plus Jakarta Sans; colores teal (#0f766e principal, fondos #f0fdfa).

Entrega: (1) versión para PDF/Word con encabezado OrigenLab + contacto, ítems en tabla, condiciones si existen, CTA final; (2) versión email corta.

Cotización original:
[PEGAR AQUÍ]
```

---

*Actualizar este doc cuando cambien `src/data/company.ts`, `contact.ts` o `services.ts`.*
