export interface Product {
  id: string;
  brandId: string;
  name: string;
  slug: string;
  sku?: string;
  summary: string;
  application: string;
  featured: boolean;
  showOnHome: boolean;
  showOnProductsPage: boolean;
  showOnBrandPage: boolean;
  commercialNote: string;
}

/**
 * Productos destacados para vitrina editorial.
 * Mantener copy comercial conservador y confirmar condiciones al cotizar.
 */
export const products: Product[] = [
  {
    id: 'serva-blueslick-42500',
    brandId: 'serva',
    name: 'BlueSlick™',
    slug: 'blueslick-42500',
    sku: '42500',
    summary: 'Reactivo para tratamiento de placas en procesos de electroforesis.',
    application: 'Laboratorio de electroforesis y preparación de muestras.',
    featured: true,
    showOnHome: true,
    showOnProductsPage: true,
    showOnBrandPage: true,
    commercialNote:
      'Disponibilidad, condiciones comerciales y documentación técnica se confirman durante la cotización.',
  },
  {
    id: 'serva-temed-25ml',
    brandId: 'serva',
    name: "TEMED (N,N,N',N'-Tetramethylethylenediamine), 25 ml",
    slug: 'temed-25ml',
    summary: 'Reactivo de uso frecuente en formulaciones y protocolos de laboratorio.',
    application: 'Preparación de soluciones y trabajo técnico en laboratorio.',
    featured: true,
    showOnHome: true,
    showOnProductsPage: true,
    showOnBrandPage: true,
    commercialNote:
      'La oferta final se emite por cotización, con revisión de disponibilidad y condiciones comerciales.',
  },
  {
    id: 'serva-repel-silane-ge17133201',
    brandId: 'serva',
    name: 'REPEL-SILANE',
    slug: 'repel-silane-ge17-1332-01',
    sku: 'GE17-1332-01',
    summary: 'Insumo para preparación y tratamiento de superficies en laboratorio.',
    application: 'Procesos de preparación técnica en líneas de electroforesis.',
    featured: true,
    showOnHome: true,
    showOnProductsPage: true,
    showOnBrandPage: true,
    commercialNote:
      'Consulta por disponibilidad y condiciones al cotizar; documentación según confirmación de línea.',
  },
];
