/**
 * Marcas representadas — lista formal pendiente.
 * No inventar marcas; al confirmar, añadir entradas con name, slug y opcional url.
 */
export interface Brand {
  id: string;
  name: string;
  slug: string;
  websiteUrl?: string;
  logoPath?: string;
  logoAlt?: string;
  summary?: string;
  featuredOnHome?: boolean;
  featuredIntro?: string;
  applicationAreas?: readonly string[];
  commercialNote?: string;
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
    featuredOnHome: true,
    featuredIntro:
      'Línea disponible para consulta y cotización en aplicaciones de electroforesis.',
    applicationAreas: [
      'Electroforesis',
      'Preparación y tratamiento de muestras',
      'Flujos técnicos de laboratorio',
    ],
    commercialNote:
      'OrigenLab puede gestionar pedidos directos con SERVA según confirmación comercial. La modalidad de prepago aplica y la disponibilidad, documentación técnica y condiciones se confirman al cotizar.',
  },
];
