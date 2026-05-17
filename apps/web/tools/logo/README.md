# OrigenLab logo — offline Python tools

These scripts were recovered from local Downloads and live **beside** the production site code. The live site uses the TypeScript simulation in `src/lib/logo/` and Astro components in `src/components/logo/`.

## Scripts

| File | Purpose |
|------|---------|
| `three_body_atom_logo_generator.py` | Figure-eight 3-body sim → static SVG/PNG (light + dark) |
| `origenlab_three_body_animation.py` | Same physics → MP4/WebM motion exports |

## Setup

```bash
cd apps/web/tools/logo
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install numpy matplotlib imageio imageio-ffmpeg
```

## Run

```bash
# Static logo candidates (writes ./outputs/)
python three_body_atom_logo_generator.py

# Video previews
python origenlab_three_body_animation.py
```

## Outputs

- `outputs/` — SVG exports from the generator (reference; not wired to the site directly).
- Production SVGs: `public/logo/*.svg` via `npm run generate:logo-svgs` (Node, matches site palette).

## Site integration

See [`../../docs/logo-system.md`](../../docs/logo-system.md) for where logos appear (header, footer, favicon, `/logo-lab`).
