# OrigenLab logo system

Status: canonical reference (recovered from Cursor logo work + Downloads, 2026-05-17)

**Important:** This work **is saved in the monorepo** under `apps/web/`. If you only edited in a Cursor session without committing, run `git status` in `origenlab` and commit `apps/web/` so nothing is lost on another machine.

---

## Production wiring (current)

| Surface | Implementation | Background |
|---------|----------------|------------|
| **Header (top left)** | `OrigenLogoLockupAnimated` — animated canvas + “OrigenLab” wordmark | `#042f2e` at ~95% (`brand-950/95`) |
| **Home hero** | Text eyebrow only (`{site.name}`) — **no** animated mark | Dark gradient `brand-950` → `brand-800` |
| **Footer** | `OrigenLogoLockup` static, `size="sm"`, `transparentBg` | `brand-950` → `brand-900` gradient |
| **Browser tab** | `public/favicon.svg` | Light mint `#f0fdfa` tile + dark teal atom |
| **Open Graph** | `public/og/origenlab-og.svg` | Unchanged (text on teal gradient) |
| **Partner logos** | SERVA / Ortoalresa under `public/brands/` | Not OrigenLab |

Header link: `src/components/Header.astro` → home `/`.

---

## Lab & experiments

- **URL:** `/logo-lab` (`src/pages/logo-lab.astro`) — not in main nav.
- Compares static marks, animated lockups, favicon preview, motion presets.

---

## Code map

### Components (`src/components/logo/`)

| File | Role |
|------|------|
| `OrigenLogoMarkStatic.astro` | Static SVG mark (premium / trace / minimal) |
| `OrigenLogoLockup.astro` | Mark + wordmark |
| `OrigenLogoLockupAnimated.astro` | Canvas animation + static wordmark (header) |
| `OrigenThreeBodyCanvas.astro` | Standalone animated mark |
| `OrigenLogoShowcase.astro` | Comparison grid for logo-lab |

### Library (`src/lib/logo/`)

| File | Role |
|------|------|
| `threeBodySim.ts` | Velocity-Verlet 3-body simulation |
| `canvasAnimator.ts` | Canvas draw loop, trails, reduced-motion |
| `composition.ts` | Ring radii, padding, header canvas sizes |
| `motionPresets.ts` | hero, header, footer, surface, favicon |
| `visualProfile.ts` | Colors per surface (header = light on dark, transparent) |
| `palette.ts` | Brand hex tokens |
| `variants.ts` | premium / trace / minimal |
| `markGeometry.ts` | Ellipse / nucleus layout |

### Public assets (`public/logo/`)

- `origenlab-mark-premium.svg`, `-trace.svg`, `-minimal.svg`
- `origenlab-lockup-dark.svg`, `origenlab-lockup-light.svg`
- `origenlab-mark-dark.svg`, `origenlab-mark-light.svg`, `origenlab-mark-static.svg`
- `origenlab-favicon-candidate.svg`

Regenerate (does **not** overwrite `public/favicon.svg`):

```bash
cd apps/web
npm run generate:logo-svgs
```

### Offline Python (`tools/logo/`)

Copied from Downloads for reproducibility:

- `three_body_atom_logo_generator.py` → `tools/logo/outputs/*.svg`
- `origenlab_three_body_animation.py` → video exports

See `tools/logo/README.md`.

---

## Brand colors (hex)

| Token | Hex | Use |
|-------|-----|-----|
| brand-50 | `#f0fdfa` | Favicon bg, light wordmark on dark |
| brand-100 | `#ccfbf1` | Electrons (header), OG subtext |
| brand-200 | `#99f6e4` | Trails, footer muted text |
| brand-500 | `#14b8a6` | Header rings |
| brand-600 | `#0d9488` | Favicon rings, buttons |
| brand-700 | `#0f766e` | Primary UI |
| brand-800 | `#115e59` | Hero gradient |
| brand-900 | `#134e4a` | Dark text on light |
| brand-950 | `#042f2e` | Header/footer, nucleus |
| slate-50 | `#f8fafc` | Page background |

WhatsApp buttons use Tailwind `emerald-600` (`#059669`) — not core logo color.

---

## Header logo design notes

- Canvas: **transparent** (no dark square); `clearRect` in animator.
- Palette on `#042f2e`: wordmark `brand-50`, rings `brand-500`, electrons `brand-100`–`300`.
- **44px** canvas, **~36px** display, tight gap to wordmark.
- ~18s calm loop; 3 ellipses; short trails.

---

## Favicon evolution (documented)

1. Replaced default Astro favicon with atom mark.
2. Dark tile → refined strokes → **light** `#f0fdfa` tile + dark teal atom (current `public/favicon.svg`).

`Layout.astro`: `rel="icon"` and `apple-touch-icon` → `/favicon.svg`.

---

## Validation

```bash
cd apps/web
npm run check
npm run validate:catalog
npm run build
```

Expect **17** pages (includes `/logo-lab`).

---

## Optional next steps

- Commit + push `apps/web` if not already on git remote.
- Add `favicon.ico` fallback for older browsers.
- Simpler 16px mark (2 rings) if tab icon feels busy.
- Align `origenlab-mark-dark.svg` exports with light favicon style.

---

## Where to put a new logo file

If you design in Figma/Illustrator:

1. Export SVG → `public/logo/origenlab-lockup-dark.svg` (or new name).
2. Wire in `Header.astro` only if replacing the animated system.
3. For a **static** header: use `OrigenLogoLockup` instead of `OrigenLogoLockupAnimated`.

Default recommendation: keep animated header + static footer unless performance or brand guidelines require all-static.
