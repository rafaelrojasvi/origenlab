/** Fixtures for catalog mirror API tests (nine seed products). */

import type {
  CatalogProductDetailResponseUi,
  CatalogProductsListUi,
} from "../../api/catalogTypes";

const BASE_ITEMS = [
  {
    product_key: "serva-blueslick-250ml",
    display_name: "BlueSlick™ 250 ml",
    brand: "SERVA",
    product_kind: "reagent",
    equipment_class: null,
    model_number: null,
    public_summary: "Reactivo SERVA para tratamiento de placas en electroforesis.",
    confidence: "website_editorial",
  },
  {
    product_key: "serva-temed-25ml",
    display_name: "TEMED 25 ml",
    brand: "SERVA",
    product_kind: "reagent",
    equipment_class: null,
    model_number: null,
    public_summary: "Reactivo SERVA TEMED 25 ml.",
    confidence: "website_editorial",
  },
  {
    product_key: "ika-rv10-70-vapor-tube",
    display_name: "Tubo de vapor IKA RV10.70",
    brand: "IKA",
    product_kind: "accessory",
    equipment_class: null,
    model_number: "RV10.70",
    public_summary:
      "Tubo de vapor IKA RV10.70 solicitado por cliente (RG Energía), cantidad 3.",
    confidence: "extracted_needs_review",
  },
  {
    product_key: "crtop-olt-hp-5l",
    display_name: "CRTOP Lab Reactor OLT-HP-5L",
    brand: "CRTOP",
    product_kind: "equipment",
    equipment_class: "reactor",
    model_number: "OLT-HP-5L",
    public_summary: "Reactor de laboratorio CRTOP OLT-HP-5L.",
    confidence: "operator_confirmed",
  },
  {
    product_key: "ollital-reactor-5l",
    display_name: "Ollital 5 L reactor",
    brand: "Ollital",
    product_kind: "equipment",
    equipment_class: "reactor",
    model_number: null,
    public_summary: "Reactor Ollital 5 L.",
    confidence: "extracted_needs_review",
  },
  {
    product_key: "hielscher-up100h",
    display_name: "Hielscher UP100H",
    brand: "Hielscher",
    product_kind: "equipment",
    equipment_class: "sonicator",
    model_number: "UP100H",
    public_summary: "Procesador ultrasónico Hielscher UP100H.",
    confidence: "extracted_needs_review",
  },
  {
    product_key: "ortoalresa-biocen-22",
    display_name: "Ortoalresa Biocen 22",
    brand: "Ortoalresa",
    product_kind: "equipment",
    equipment_class: "centrifuge",
    model_number: "Biocen 22",
    public_summary: "Microcentrífuga ventilada Ortoalresa Biocen 22.",
    confidence: "website_editorial",
  },
  {
    product_key: "ortoalresa-digicen-22-r",
    display_name: "Ortoalresa Digicen 22 R",
    brand: "Ortoalresa",
    product_kind: "equipment",
    equipment_class: "centrifuge",
    model_number: "Digicen 22 R",
    public_summary: "Centrífuga universal refrigerada Ortoalresa Digicen 22 R.",
    confidence: "website_editorial",
  },
  {
    product_key: "balance-analytical-generic",
    display_name: "Balanza analítica (genérico)",
    brand: null,
    product_kind: "equipment",
    equipment_class: "balance",
    model_number: null,
    public_summary: "Categoría genérica para balanza analítica.",
    confidence: "extracted_needs_review",
  },
] as const;

export function catalogListFixture(): CatalogProductsListUi {
  return {
    table_available: true,
    items: [...BASE_ITEMS],
    total: 9,
    limit: 100,
    data_source: "postgres_mirror",
    read_only: true,
    disclaimer: "Catálogo operador (espejo Postgres redactado).",
  };
}

export function crtopDetailFixture(): CatalogProductDetailResponseUi {
  return {
    table_available: true,
    read_only: true,
    data_source: "postgres_mirror",
    disclaimer: "Catálogo operador (espejo Postgres redactado).",
    product: {
      ...BASE_ITEMS[3],
      manufacturer_name: "CRTOP",
      default_unit: "ea",
      website_slug: null,
      website_product_id: null,
      is_active: true,
      aliases: [{ alias_source: "crtop", alias_code: "OLT-HP-5L", alias_kind: "model_number" }],
      categories: [
        {
          category_key: "lab_reactor",
          display_name: "Reactor de laboratorio",
          equipment_class: "reactor",
          is_primary: true,
        },
      ],
      specs: [
        { spec_group: "dimensions", spec_key: "volume_l", spec_value: "5 L", spec_value_numeric: 5, spec_unit: "L", source: "supplier_quote", confidence: "operator_confirmed" },
        { spec_group: "operation", spec_key: "operation_temp_c", spec_value: "170–190 °C", spec_value_numeric: null, spec_unit: null, source: "supplier_quote", confidence: "operator_confirmed" },
        { spec_group: "design", spec_key: "design_temp_c", spec_value: "200 °C", spec_value_numeric: 200, spec_unit: "°C", source: "supplier_quote", confidence: "operator_confirmed" },
        { spec_group: "operation", spec_key: "operation_pressure_mpa", spec_value: "0.8–1.6 MPa", spec_value_numeric: null, spec_unit: null, source: "supplier_quote", confidence: "operator_confirmed" },
        { spec_group: "design", spec_key: "design_pressure_mpa", spec_value: "6 MPa", spec_value_numeric: 6, spec_unit: "MPa", source: "supplier_quote", confidence: "operator_confirmed" },
        { spec_group: "material", spec_key: "material", spec_value: "316L stainless steel", spec_value_numeric: null, spec_unit: null, source: "supplier_quote", confidence: "operator_confirmed" },
        { spec_group: "electrical", spec_key: "power_w", spec_value: "1600 W", spec_value_numeric: 1600, spec_unit: "W", source: "supplier_quote", confidence: "operator_confirmed" },
        { spec_group: "electrical", spec_key: "supply_voltage", spec_value: "AC 108–240 V 50/60 Hz", spec_value_numeric: null, spec_unit: null, source: "supplier_quote", confidence: "operator_confirmed" },
      ],
      supplier_offers: [
        {
          offer_key: "crtop-olt-hp-5l-quote",
          supplier_org_name: "CRTOP",
          supplier_domain: "crtopmachine.com",
          offer_status: "valid",
          quoted_at: null,
          valid_until: "60 days from quote",
          incoterm: "EXW",
          payment_terms: "T/T 100% prepaid",
          delivery_terms: "25–30 working days after prepayment",
          currency: "USD",
          quantity_offered: "1",
          availability_note: null,
          confidence: "operator_confirmed",
        },
      ],
      price_snapshots: [
        {
          snapshot_key: "crtop-olt-hp-5l-exw-usd",
          snapshot_kind: "supplier_quote",
          offer_key: "crtop-olt-hp-5l-quote",
          currency: "USD",
          amount_decimal: "10600.00",
          amount_minor: 1060000,
          amount_clp_integer: null,
          quantity: "1",
          unit: "ea",
          incoterm: "EXW",
          price_notes: null,
          is_public_safe: false,
          confidence: "operator_confirmed",
          observed_at: "2026-05-27T00:00:00Z",
        },
      ],
      commercial_links: [
        { link_kind: "warm_case", link_ref: "warm_case:crtop-olt-hp-5l-reactor", confidence: "operator_confirmed" },
      ],
    },
  };
}

export function ikaDetailFixture(): CatalogProductDetailResponseUi {
  return {
    table_available: true,
    read_only: true,
    data_source: "postgres_mirror",
    disclaimer: "Catálogo operador (espejo Postgres redactado).",
    product: {
      ...BASE_ITEMS[2],
      manufacturer_name: "IKA",
      default_unit: "ea",
      website_slug: null,
      website_product_id: null,
      is_active: true,
      aliases: [
        { alias_source: "ika", alias_code: "3812200", alias_kind: "part_no" },
        { alias_source: "ika", alias_code: "RV10.70", alias_kind: "model_number" },
      ],
      categories: [
        {
          category_key: "heating_accessory",
          display_name: "Accesorio de calentamiento",
          equipment_class: null,
          is_primary: true,
        },
      ],
      specs: [],
      supplier_offers: [
        {
          offer_key: "ika-rv10-70-rg-energia-quote",
          supplier_org_name: "IKA",
          supplier_domain: "ika.net.br",
          offer_status: "needs_review",
          quoted_at: null,
          valid_until: null,
          incoterm: null,
          payment_terms: null,
          delivery_terms: null,
          currency: null,
          quantity_offered: "1",
          availability_note:
            "Stock disponible según proveedor; confirmar moneda y si el monto es precio unitario.",
          confidence: "extracted_needs_review",
        },
      ],
      price_snapshots: [
        {
          snapshot_key: "ika-rv10-70-price-ambiguous",
          snapshot_kind: "supplier_quote",
          offer_key: "ika-rv10-70-rg-energia-quote",
          currency: null,
          amount_decimal: "112.00",
          amount_minor: null,
          amount_clp_integer: null,
          quantity: "3",
          unit: "ea",
          incoterm: null,
          price_notes:
            "Cliente solicitó cantidad 3. Monto 112,00 del proveedor se registra como candidato a precio unitario; moneda ambigua — confirmar antes de cotizar.",
          is_public_safe: false,
          confidence: "extracted_needs_review",
          observed_at: "2026-05-27T00:00:00Z",
        },
      ],
      commercial_links: [
        {
          link_kind: "warm_case",
          link_ref: "warm_case:rg-energia-ika-rv10.70-3812200",
          confidence: "operator_confirmed",
        },
      ],
    },
  };
}

export function servaBlueslickDetailFixture(): CatalogProductDetailResponseUi {
  return {
    table_available: true,
    read_only: true,
    data_source: "postgres_mirror",
    disclaimer: "Catálogo operador.",
    product: {
      ...BASE_ITEMS[0],
      manufacturer_name: "SERVA Electrophoresis GmbH",
      default_unit: "ea",
      website_slug: "blueslick-42500",
      website_product_id: "serva-blueslick-42500",
      is_active: true,
      aliases: [{ alias_source: "serva", alias_code: "42500", alias_kind: "legacy_web_sku" }],
      categories: [
        {
          category_key: "electrophoresis_reagent",
          display_name: "Reactivo de electroforesis",
          equipment_class: null,
          is_primary: true,
        },
      ],
      specs: [],
      supplier_offers: [],
      price_snapshots: [],
      commercial_links: [
        { link_kind: "commercial_deal_line", link_ref: "deal:serva-ceaf-oc-26172-po-174-26:line:1", confidence: "operator_confirmed" },
        { link_kind: "website_product", link_ref: "web:blueslick-42500", confidence: "website_editorial" },
      ],
    },
  };
}
