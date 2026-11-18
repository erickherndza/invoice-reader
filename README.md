# invoice-reader

Web service que lee una foto de factura dominicana y devuelve JSON estructurado
(emisor, RNC, NCF, fecha, líneas con ITBIS, totales) con un score de confianza por campo.
Extraído de Facturar.do. Proveedores de visión: Groq (Llama 4 Scout) o Claude.

## Uso con Docker (recomendado: app Python + PostgreSQL)

```bash
cp .env.example .env
# edita .env: API_KEYS, POSTGRES_PASSWORD (openssl rand -hex 24) y la clave del proveedor LLM
docker compose up -d --build
open http://localhost:8080
```

Servicios: `web` (Flask + gunicorn, usuario no-root) y `db` (PostgreSQL 16, volumen `pgdata`).
La base **no se publica** al exterior; la web escucha en `127.0.0.1` salvo que cambies `WEB_BIND`.
El esquema se crea solo al arrancar (`migrations/*.sql`, idempotente).

```bash
docker compose logs -f web                                   # logs
docker compose exec db psql -U invoice invoice_reader        # consola SQL
docker compose down                # para (los datos se conservan)   |  down -v  = borra también los datos
```

Consultas SQL de ejemplo:
```sql
SELECT created_at, data->'emisor'->>'valor' AS emisor, data->'totales'->>'total' AS total
  FROM invoices ORDER BY created_at DESC LIMIT 10;
SELECT count(*) FROM invoices WHERE created_at > now() - interval '1 day';
```

Sin Docker: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, exporta las variables de `.env.example`
y `gunicorn wsgi:app`. Sin `DATABASE_URL` funciona igual, pero sin historial y con rate limit en memoria (1 worker).

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

`GET /health` → vivo · `GET /health/ready` → comprueba la base de datos (503 si cae)

`POST /v1/invoices/extract` — requiere `Authorization: Bearer <API_KEY>` (o `X-API-Key`).

```bash
curl -H "Authorization: Bearer $KEY" -F file=@factura.jpg localhost:8080/v1/invoices/extract
# o JSON: -d '{"image":"<base64>"}' -H 'Content-Type: application/json'
```

Historial (requiere `DATABASE_URL`; cada API key solo ve lo suyo):
`GET /v1/invoices?limit=20&before=<ISO>` · `GET /v1/invoices/<id>` · `DELETE /v1/invoices/<id>`.
Solo se guarda el JSON extraído, **nunca la imagen**; la API key se guarda como hash.

Respuesta de `extract` (incluye `id` del historial si hay base de datos):
```json
{ "ok": true, "id": "…", "provider": "groq",
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
| 429 | Rate limit de escaneos (10/min por clave; consultar el historial no cuenta) |
| 503 | Servicio o proveedor sin configurar |

`warnings` avisa de incoherencias (base + ITBIS ≠ total con tolerancia 0,02; ITBIS distinto de 0/16/18).
**Los datos extraídos por IA deben revisarse antes de usarse contablemente.**

## Seguridad y límites conocidos
- Sin `API_KEYS` el servicio responde 503 (falla cerrado). Las imágenes no se guardan en ningún sitio.
- El rate limit vive en PostgreSQL: se comparte entre workers y réplicas y sobrevive a reinicios.
- Si la base cae, `extract` responde 503 (no deja pasar sin límite).
  Si cae justo al guardar, la lectura se devuelve igual con `id: null` y se registra el error.
- El historial contiene datos fiscales de terceros (RNC, NCF, totales): protege el volumen/backups,
  y usa `DELETE /v1/invoices/<id>` para borrar bajo petición.
- Cada llamada consume cuota del proveedor LLM: mantén el rate limit y rota las claves si se filtran.
- Los datos extraídos por IA deben revisarse antes de usarse contablemente.

## Tests
`.venv/bin/python -m pytest -q` (unitarios, sin base de datos).
Integración con PostgreSQL real (usa una base cuyo nombre contenga `test`; los tests vacían tablas):
`TEST_DATABASE_URL=postgresql://invoice:<pw>@db:5432/invoice_reader_test docker compose run --rm --no-deps -e TEST_DATABASE_URL web python -m pytest -q`
