/**
 * Marcas representadas — confirmar alcance comercial antes de ampliar claims públicos.
 */
export interface Brand {
  id: string;
  name: string;
  slug: string;
  /** Razón social u otro nombre legal cuando aplique */
  legalName?: string;
  websiteUrl?: string;
  logoPath?: string;
  logoAlt?: string;
  logoSourceUrl?: string;
  summary?: string;
  /** Tarjeta en sección “Marcas y líneas disponibles” del inicio (mismo nivel visual) */
  showOnHomeBrandsSection?: boolean;
  homeCardTitle?: string;
  homeCardDescription?: string;
  homeCardCtaLabel?: string;
  /** Párrafo introductorio en página de marca */
  brandIntro?: string;
  applicationAreas?: readonly string[];
  commercialNote?: string;
  /** Subtítulo para página de marca */
  pageSubtitle?: string;
  manufacturerAttribution?: string;
}

export const brands: Brand[] = [
  {
    id: 'serva',
    name: 'SERVA Electrophoresis GmbH',
    slug: 'serva-electrophoresis',
    websiteUrl: 'https://www.serva.de/deDE/index.html',
    logoPath: '/brands/serva-logo.png',
    logoAlt: 'Logo SERVA Electrophoresis GmbH',
    summary:
      'Proveedor internacional de reactivos e insumos para aplicaciones de electroforesis y laboratorio.',
    showOnHomeBrandsSection: true,
    homeCardTitle: 'SERVA Electrophoresis',
    homeCardDescription:
      'Reactivos e insumos para electroforesis y preparación de muestras en laboratorio.',
    homeCardCtaLabel: 'Ver SERVA',
    brandIntro:
      'Línea disponible para consulta y cotización en aplicaciones de electroforesis.',
    applicationAreas: [
      'Electroforesis',
      'Preparación y tratamiento de muestras',
      'Flujos técnicos de laboratorio',
    ],
    commercialNote:
      'OrigenLab puede gestionar pedidos directos con SERVA según confirmación comercial. La modalidad de prepago aplica y la disponibilidad, documentación técnica y condiciones se confirman al cotizar.',
  },
  {
    id: 'ortoalresa',
    name: 'Ortoalresa',
    legalName: 'Álvarez Redondo S.A.',
    slug: 'ortoalresa',
    websiteUrl: 'https://ortoalresa.com/',
    logoPath: '/brands/ortoalresa-logo.svg',
    logoAlt: 'Logo Ortoalresa',
    logoSourceUrl:
      'https://ortoalresa.com/static/images/logo-header-normal-1c27f117243d1215a0b668f0ee824e57.svg',
    summary:
      'Ortoalresa, fabricante europeo de centrífugas de laboratorio, ofrece equipos para aplicaciones generales y necesidades específicas de laboratorio.',
    manufacturerAttribution:
      'Información de producto según documentación pública del fabricante. OrigenLab no fabrica estos equipos.',
    pageSubtitle: 'Centrífugas de laboratorio para aplicaciones generales y especializadas',
    showOnHomeBrandsSection: true,
    homeCardTitle: 'Ortoalresa',
    homeCardDescription:
      'Centrífugas, microcentrífugas y equipos refrigerados para preparación de muestras y análisis.',
    homeCardCtaLabel: 'Ver Ortoalresa',
    applicationAreas: [
      'Preparación de muestras',
      'Microtubos y tubos cónicos',
      'Bioprocesos',
      'Laboratorio clínico y control de calidad',
    ],
    commercialNote:
      'Equipos Ortoalresa disponibles para evaluación técnica y cotización a través de OrigenLab. Disponible bajo cotización; configuración, accesorios y condiciones comerciales se confirman al cotizar.',
  },
];
