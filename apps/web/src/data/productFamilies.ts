/**
 * Familias de equipo (vitrina editorial) distintas de las tres líneas comerciales principales.
 */
export interface ProductFamily {
  id: string;
  name: string;
  slug: string;
  description: string;
  /** Slugs de categorías donde conviene enlazar esta familia */
  categorySlugs: readonly string[];
}

export const productFamilies: ProductFamily[] = [
  {
    id: 'centrifugas',
    name: 'Centrífugas',
    slug: 'centrifugas',
    description:
      'Equipos de centrifugación para preparación de muestras, bioprocesos y análisis en laboratorio.',
    categorySlugs: ['control-de-calidad', 'laboratorio-clinico'],
  },
];

export function getProductFamilyBySlug(slug: string): ProductFamily | undefined {
  return productFamilies.find((family) => family.slug === slug);
}

/** Orden canónico Ortoalresa en familia, marca, inicio y comparativa. */
export const ortoalresaCentrifugeSlugs = [
  'biocen-22',
  'biocen-22-r',
  'digicen-22',
  'digicen-22-r',
  'consul-22',
] as const;
