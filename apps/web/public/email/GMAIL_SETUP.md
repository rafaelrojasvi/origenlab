# Como poner la firma en Gmail (con imagen)

Firma actual con franja de marcas: pegar desde `origenlab-contacto-signature-SMALL-embedded.html` (atomo + `origenlab-brand-strip.png` embebidos).

Regenerar: `npm run build:email-brands && npm run build:email-signature-embedded` en `apps/web`.

## Por que no se ve la imagen al pegar

Gmail **no puede** cargar:

- `http://localhost:8765/...`
- rutas locales como `origenlab-signature-mark-v3.png`
- `https://www.origenlab.cl/email/...` **hasta** que subas el PNG al sitio publicado

Por eso ves un icono roto o nada.

## Opcion A — Subir la imagen en Gmail (mas fiable)

1. Abre el archivo en tu PC:
   - WSL: `/home/rafael/dev/freelance/origenlab/apps/web/public/email/origenlab-signature-mark-v3.png`
   - Windows: `\\wsl.localhost\Ubuntu\home\rafael\dev\freelance\origenlab\apps\web\public\email\origenlab-signature-mark-v3.png`
2. Gmail → **Configuracion** (engranaje) → **Ver toda la configuracion** → **General**
3. En **Firma**, crea o edita la firma de `contacto@origenlab.cl`
4. Pega el texto/HTML de la firma (recuadro blanco de la preview) **o** escribela a mano
5. Donde va el atomo (cuadro roto), haz clic → **Insertar imagen** → **Subir** → elige `origenlab-signature-mark-v3.png`
6. Ajusta tamano a ~48px si Gmail la agranda
7. **Guardar cambios** al final de la pagina

## Opcion B — Pegar con imagen embebida

1. Con el servidor local: `python3 -m http.server 8765` en esta carpeta
2. Abre en Chrome:  
   `http://localhost:8765/origenlab-contacto-signature-gmail-embedded.html`
3. Copia **solo el recuadro blanco** → pega en la firma de Gmail
4. Guardar cambios

Si Gmail quita la imagen, usa la **Opcion A**.

## Opcion C — URL publica (despues del deploy)

Cuando `origenlab-signature-mark-v3.png` este en  
`https://www.origenlab.cl/email/origenlab-signature-mark-v3.png`,  
la firma en `origenlab-contacto-signature.html` funcionara sola al pegar.

## Vista previa local

```bash
cd /home/rafael/dev/freelance/origenlab/apps/web/public/email
python3 -m http.server 8765
```

- Firma: http://localhost:8765/origenlab-contacto-signature-gmail-paste.html
- Comparar atomos: http://localhost:8765/origenlab-signature-mark-compare.html
