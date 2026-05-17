import { brands, type Brand } from '../data/brands';
import { products, type Product } from '../data/products';
import { getProductFamilyBySlug, ortoalresaCentrifugeSlugs } from '../data/productFamilies';

export function getBrandById(id: string): Brand | undefined {
  return brands.find((brand) => brand.id === id);
}

export function getBrandBySlug(slug: string): Brand | undefined {
  return brands.find((brand) => brand.slug === slug);
}

export function getProductBySlug(slug: string): Product | undefined {
  return products.find((product) => product.slug === slug);
}

export function getProductsByBrandId(brandId: string): Product[] {
  return products
    .filter((product) => product.brandId === brandId)
    .sort((a, b) => (a.catalogSortOrder ?? 999) - (b.catalogSortOrder ?? 999));
}

export function getProductsByFamilySlug(familySlug: string): Product[] {
  if (familySlug === 'centrifugas') {
    return getOrtoalresaCentrifuges();
  }
  return products
    .filter((product) => product.productFamilySlug === familySlug)
    .sort((a, b) => (a.catalogSortOrder ?? 999) - (b.catalogSortOrder ?? 999));
}

function centrifugesFromSlugs(slugs: readonly string[]): Product[] {
  return slugs
    .map((slug) => getProductByFamilyAndSlug('centrifugas', slug))
    .filter((product): product is Product => product !== undefined);
}

export function getOrtoalresaCentrifuges(): Product[] {
  return centrifugesFromSlugs(ortoalresaCentrifugeSlugs);
}

/** Alias del orden canónico (mismo que familia/marca). */
export function getOrtoalresaCentrifugesForHome(): Product[] {
  return getOrtoalresaCentrifuges();
}

export function getHomeBrands() {
  return brands.filter((brand) => brand.showOnHomeBrandsSection);
}

export function getProductByFamilyAndSlug(familySlug: string, productSlug: string): Product | undefined {
  return products.find(
    (product) => product.productFamilySlug === familySlug && product.slug === productSlug,
  );
}

export function productPageHref(product: Product): string | undefined {
  if (!product.productFamilySlug) return undefined;
  return `/productos/${product.productFamilySlug}/${product.slug}`;
}

export function productsForCategory(categorySlug: string): Product[] {
  return products.filter(
    (product) => product.categorySlugs?.includes(categorySlug) && product.showOnProductsPage,
  );
}

/** Equipos relacionados por categoría (evita duplicar las mismas fichas en todas las categorías). */
export function getCategoryRelatedProducts(categorySlug: string): Product[] {
  if (categorySlug === 'laboratorio-clinico') {
    return [];
  }
  if (categorySlug === 'control-de-calidad') {
    return getOrtoalresaCentrifuges().filter((product) => product.showOnProductsPage);
  }
  return productsForCategory(categorySlug);
}

export function validateProductFamilySlugs(): void {
  for (const product of products) {
    if (product.productFamilySlug && !getProductFamilyBySlug(product.productFamilySlug)) {
      throw new Error(
        `Product "${product.id}" references unknown family "${product.productFamilySlug}"`,
      );
    }
  }
}
