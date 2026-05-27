# Logo PNG chico para Gmail

## El archivo que necesitas

**`origenlab-signature-mark-SMALL.png`** — imagen **56 x 56 pixeles** (atomo v3, tamano Gmail).

`origenlab-signature-mark-v3.png` es **96 x 96** (mas grande si Gmail lo ignora el width).

## Generar el PNG chico

```bash
cd /home/rafael/dev/freelance/origenlab/apps/web
npm run export:email-signature
```

## Gmail — pegar firma con imagen

```bash
cd public/email
python3 -m http.server 8765
```

Chrome: **http://localhost:8765/origenlab-contacto-signature-SMALL-embedded.html**

Copia el recuadro blanco → Gmail → Firma → Guardar.

## Solo subir el logo

Gmail → Firma → Insertar imagen → sube:

`apps/web/public/email/origenlab-signature-mark-SMALL.png`

## Comparar tamanos de archivo

| PNG | Pixeles |
|-----|---------|
| origenlab-signature-mark-v3.png | 96 x 96 |
| **origenlab-signature-mark-SMALL.png** | **56 x 56** |
