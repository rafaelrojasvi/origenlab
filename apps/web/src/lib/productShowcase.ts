import type { Product } from '../data/products';

/** Línea de aplicación breve para vitrina del inicio (copy editorial conservador). */
export const showcaseApplicationBySlug: Record<string, string> = {
  'biocen-22': 'Microtubos y microhematocrito',
  'biocen-22-r': 'Microtubos y tubos cónicos',
  'digicen-22': 'Microplacas, criotubos y tubos hasta 100 ml',
  'digicen-22-r': 'Control de temperatura y rotores versátiles',
  'consul-22': 'Volúmenes mayores hasta 4 × 400 ml',
};

/** Etiqueta “Tipo” en la franja comparativa (alineada con ficha del fabricante). */
const comparisonTipoBySlug: Record<string, string> = {
  'biocen-22': 'Microcentrífuga ventilada',
  'biocen-22-r': 'Microcentrífuga refrigerada',
  'digicen-22': 'Universal ventilada',
  'digicen-22-r': 'Universal refrigerada',
  'consul-22': 'Gran capacidad ventilada',
};

const comparisonTemperatureBySlug: Record<string, string> = {
  'biocen-22-r': '-20 °C a 40 °C',
  'digicen-22-r': '-20 °C a 40 °C',
};

export interface ShowcaseSpecChips {
  rpm: string;
  capacity: string;
  cooling: string;
}

export function getShowcaseApplication(product: Product): string {
  return showcaseApplicationBySlug[product.slug] ?? product.application;
}

export function getShowcaseSpecChips(product: Product): ShowcaseSpecChips {
  const specs = product.keySpecs ?? [];
  const rpmRaw = specs.find((s) => s.label.toLowerCase().includes('velocidad máxima'))?.value;
  const rpm = rpmRaw?.split('/')[0]?.trim() ?? '—';
  const capacity = specs.find((s) => s.label === 'Capacidad máxima')?.value ?? '—';
  const cooling = specs.find((s) => s.label === 'Versión')?.value ?? '—';
  return { rpm, capacity, cooling };
}

export interface ComparisonRow {
  model: string;
  tipo: string;
  capacity: string;
  speed: string;
  temperature: string;
}

export function getComparisonRows(products: Product[]): ComparisonRow[] {
  return products.map((product) => {
    const specs = product.keySpecs ?? [];
    const speedRaw = specs.find((s) => s.label.toLowerCase().includes('velocidad máxima'))?.value;
    return {
      model: product.name,
      tipo: comparisonTipoBySlug[product.slug] ?? product.equipmentType ?? '—',
      capacity: specs.find((s) => s.label === 'Capacidad máxima')?.value ?? '—',
      speed: speedRaw?.split('/')[0]?.trim() ?? '—',
      temperature: comparisonTemperatureBySlug[product.slug] ?? '—',
    };
  });
}
