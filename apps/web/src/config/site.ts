import { contact } from '../data/contact';
import { company } from '../data/company';

/**
 * Configuración central del sitio OrigenLab.
 * Descripción corta SEO: derivada de company (evita duplicar narrativa).
 */
export const site = {
  name: 'OrigenLab',
  domain: 'origenlab.cl',
  baseUrl: 'https://origenlab.cl',
  email: contact.email,
  location: contact.locationPublic,
  hours: contact.hours,
  tagline: 'Equipos para laboratorio en todo Chile',
  description: `${company.name}: equipos de laboratorio en ${company.geography}. Alimentos, control de calidad, laboratorio clínico. Cotización ${contact.email} · WhatsApp ${contact.phoneDisplay}.`,
  ogImagePath: '/og/origenlab-og.svg',
  ogImageAlt: 'OrigenLab — Equipos para laboratorio',
  phone: contact.phoneDisplay,
  whatsapp: contact.phoneDisplay,
  nav: [
    { href: '/nosotros', label: 'Nosotros' },
    { href: '/productos', label: 'Productos' },
    { href: '/marcas', label: 'Marcas' },
    { href: '/contacto', label: 'Contacto' },
  ] as const,
} as const;
