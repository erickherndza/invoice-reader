# invoice-reader

Web service que lee una foto de factura dominicana y devuelve JSON estructurado
(emisor, RNC, NCF, fecha, líneas con ITBIS, totales) con un score de confianza por campo.
Extraído de Facturar.do. Proveedores de visión: Groq (Llama 4 Scout) o Claude.

## Uso

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # completa API_KEYS y la clave del proveedor
set -a; . ./.env; set +a
.venv/bin/gunicorn -w 1 --threads 8 -b 0.0.0.0:8080 wsgi:app
```

Docker: `docker build -t invoice-reader . && docker run -p 8080:8080 --env-file .env invoice-reader`

## Interfaz móvil
Al abrir `/` el servicio muestra una app web móvil (sin build, HTML/CSS/JS puros) con el flujo
**escanear → revisar → guardar**: cámara o galería, lectura con avisos de confianza por campo,
corrección de datos y descarga a Excel (CSV). Diseño en `invoice_reader/static/`.
- Pide la API key una vez y la guarda solo en el navegador del dispositivo (`localStorage`).
- "Recientes" se guarda solo en el dispositivo (nombre, fecha, total, estado); el servidor no guarda nada.
- La cámara del navegador exige **HTTPS** (o `localhost`); sin ella queda la galería.
- La CSP es estricta (sin scripts ni estilos inline, sin CDN) y el texto del modelo se inserta como texto, nunca como HTML.
- Las fuentes (Inter y Space Grotesk, licencia OFL) van incluidas en `static/fonts/`.

## API

`GET /health` → `{ "ok": true }`

`POST /v1/invoices/extract` — requiere `Authorization: Bearer <API_KEY>` (o `X-API-Key`).

```bash
curl -H "Authorization: Bearer $KEY" -F file=@factura.jpg localhost:8080/v1/invoices/extract
# o JSON: -d '{"image":"<base64>"}' -H 'Content-Type: application/json'
```

Respuesta:
```json
{ "ok": true, "provider": "groq",
  "data": { "emisor": {"valor": "...", "score": 0.95}, "rnc": {}, "ncf": {}, "fecha": {},
            "lineas": [{"descripcion": "...", "cantidad": 1, "precio_unitario": 1000.0, "itbis_pct": 18.0, "score": 0.85}],
            "totales": {"base_imponible": 0, "itbis": 0, "total": 0}, "warnings": [] },
  "warnings": [] }
```

| Código | Causa |
|---|---|
| 400 | Falta imagen o base64 inválido |
| 401 | API key ausente o inválida |
| 413 | Más de 8 MB |
| 415 | No es JPEG/PNG/WebP (se valida por contenido real, no por el tipo declarado) |
| 429 | Rate limit (por defecto 10/min por clave) |
| 503 | Servicio o proveedor sin configurar |

`warnings` avisa de incoherencias (base + ITBIS ≠ total con tolerancia 0,02; ITBIS distinto de 0/16/18).
**Los datos extraídos por IA deben revisarse antes de usarse contablemente.**

## Seguridad y límites conocidos
- Sin `API_KEYS` el servicio responde 503 (falla cerrado). Las imágenes no se guardan en disco.
- El rate limit es **en memoria por proceso**: por eso el Dockerfile usa 1 worker con hilos. Para escalar a varias réplicas hay que moverlo a Redis.
- Cada llamada consume cuota del proveedor LLM: mantén el rate limit y rota las claves si se filtran.

## Tests
`.venv/bin/python -m pytest -q`
