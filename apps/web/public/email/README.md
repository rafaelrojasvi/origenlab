# Firma de correo OrigenLab (Gmail)

## Imagen del atomo

| Archivo | Uso |
|---------|-----|
| **`origenlab-signature-mark-v3.png`** | **Usar en la firma** (balance: cuerpos r=4.5, orbitas finas) |
| `origenlab-signature-mark-v2.png` | Muy pequeno (referencia) |
| `origenlab-signature-mark-v1.png` | Muy grande (referencia) |
| `origenlab-signature-mark.svg` | Fuente |

## Regenerar y ver en Chrome

```bash
cd /home/rafael/dev/freelance/origenlab/apps/web
npm run export:email-signature

cd public/email
python3 -m http.server 8765
```

URLs (Chrome en Windows):

- http://localhost:8765/origenlab-signature-mark-compare.html
- http://localhost:8765/origenlab-contacto-signature-gmail-paste.html

Ctrl+F5 para recargar sin cache.

## Gmail

Pegar HTML de `origenlab-contacto-signature.html` o subir `origenlab-signature-mark-v3.png`.
