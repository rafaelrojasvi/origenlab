# Partner logos — Gmail signature strip

Official sources (downloaded to `*-source.*` for regeneration):

| Brand | Source |
|-------|--------|
| SERVA | https://www.serva.de/lib/images/serva-logo.png |
| Ortoalresa | https://ortoalresa.com/static/images/logo-header-normal-1c27f117243d1215a0b668f0ee824e57.svg |
| IKA | https://www.ika.com/ika/images/Logo-IKA-without-Claim.png |
| CRTOP | https://www.crtopmachine.com/uploadfile/userimg/f00993a6a3fa4cec3aae84af3d87d9da.jpg |
| Ollital | https://www.ollital.com/uploadfile/userimg/9f6fd3332271a26b56dbc789cec01c68.jpeg |
| Hielscher | https://www.hielscher.com/wp-content/uploads/hielscher-logo2.svg |

## Outputs

- `*-logo.png` — normalized grayscale (~36px tall)
- `../origenlab-brand-strip.png` — combined strip (export 820×68, display **410×34**)

## Regenerate

```bash
cd apps/web
npm run build:email-brands
npm run build:email-signature-embedded
```

Wording in signature: **Marcas con las que trabajamos** (not “distribuidor oficial”).
