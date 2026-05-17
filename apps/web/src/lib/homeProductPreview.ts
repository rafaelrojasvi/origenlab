import type { Product } from '../data/products';

/** Slug destacado en panel del hero del inicio. */
export const HOME_HERO_FEATURED_SLUG = 'biocen-22';

/** Slug destacado en tarjeta comercial “Líneas disponibles”. */
export const HOME_FEATURED_CENTRIFUGE_SLUG = 'digicen-22-r';
const HOME_FEATURED_FALLBACK_SLUG = 'consul-22';

const HOME_PREVIEW_TYPE_LABELS: Record<string, string> = {
  'biocen-22': 'Ventilada',
  'biocen-22-r': 'Refrigerada',
  'digicen-22': 'Universal',
  'digicen-22-r': 'Universal refrigerada',
  'consul-22': 'Gran capacidad',
};

/** Etiqueta corta para tiles de vista previa en inicio (sin specs ni tabla). */
export function homePreviewTypeLabel(product: Product): string {
  return HOME_PREVIEW_TYPE_LABELS[product.slug] ?? product.equipmentType ?? '';
}

export function homePreviewFeaturedProduct(products: readonly Product[]): Product | undefined {
  return (
    products.find((p) => p.slug === HOME_FEATURED_CENTRIFUGE_SLUG) ??
    products.find((p) => p.slug === HOME_FEATURED_FALLBACK_SLUG) ??
    products[0]
  );
}

export function homePreviewSupportingProducts(
  products: readonly Product[],
  featured?: Product,
): Product[] {
  if (!featured) return [...products];
  return products.filter((p) => p.slug !== featured.slug);
}

export function homePreviewAccessibleLabel(product: Product, typeLabel: string): string {
  return `${product.name}, ${typeLabel}. Ver ficha del producto.`;
}

/** Verifica que imagePath coincida con slug (regresión en catálogo). */
export function homePreviewImageMatchesSlug(product: Product): boolean {
  if (!product.imagePath) return false;
  const expected = `/products/ortoalresa/${product.slug}.avif`;
  return product.imagePath === expected;
}
