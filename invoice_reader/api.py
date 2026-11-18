import base64
import binascii
import logging
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from .extractor import ExtractionError, extract_invoice
from .images import ALLOWED, sniff_media_type
from . import db
from .security import authenticated, require_api_key

bp = Blueprint("api", __name__)
log = logging.getLogger(__name__)


@bp.get("/health")
def health():
    return jsonify(ok=True, service="invoice-reader")


@bp.get("/health/ready")
def ready():
    """Readiness: comprueba la base de datos si está configurada."""
    if db.enabled():
        try:
            db.ping()
        except Exception:
            return jsonify(ok=False, service="invoice-reader", db="down"), 503
    return jsonify(ok=True, service="invoice-reader", db="up" if db.enabled() else "disabled")


@bp.post("/v1/invoices/extract")
@require_api_key
def extract():
    """Acepta multipart (campo `file`) o JSON `{ "image": "<base64>" }`."""
    if request.files.get("file"):
        image = request.files["file"].read()
    else:
        body = request.get_json(silent=True) or {}
        b64 = body.get("image", "")
        if not b64:
            return jsonify(ok=False, code="BAD_REQUEST",
                           error="Envía 'file' (multipart) o 'image' (base64)."), 400
        if "," in b64[:100]:  # tolera prefijo data:image/...;base64,
            b64 = b64.split(",", 1)[1]
        try:
            image = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            return jsonify(ok=False, code="BAD_REQUEST", error="'image' no es base64 válido."), 400

    media_type = sniff_media_type(image)
    if media_type not in ALLOWED:
        return jsonify(ok=False, code="INVALID_MEDIA_TYPE",
                       error="Solo se aceptan imágenes JPEG, PNG o WebP."), 415

    try:
        data = extract_invoice(image, media_type)
    except ExtractionError as e:
        return jsonify(ok=False, code="OCR_ERROR", error=str(e)), 503
    except Exception:
        log.exception("Fallo del proveedor LLM")  # detalle solo en el log, no al cliente
        return jsonify(ok=False, code="OCR_ERROR", error="Error procesando la imagen."), 502

    provider = data.pop("provider", "?")
    data.pop("usage", None)  # tokens: solo para métricas/comparativas, no se expone ni se guarda
    invoice_id = None
    if db.enabled():
        try:
            from . import store
            invoice_id = str(store.insert_invoice(g.owner, provider, data))
        except Exception:
            # La lectura ya se pagó: se devuelve igual, sin id, y se registra el fallo.
            log.exception("No se pudo guardar la lectura en la base de datos")
    return jsonify(ok=True, id=invoice_id, provider=provider, data=data, warnings=data.get("warnings", []))


def _need_db():
    if not db.enabled():
        return jsonify(ok=False, code="HISTORY_DISABLED",
                       error="Historial no habilitado (falta DATABASE_URL)."), 501
    return None


@bp.get("/v1/invoices")
@authenticated
def list_invoices():
    if (err := _need_db()):
        return err
    from . import store
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 100))
        before = datetime.fromisoformat(request.args["before"]) if request.args.get("before") else None
    except ValueError:
        return jsonify(ok=False, code="BAD_REQUEST", error="'limit' o 'before' inválido."), 400
    rows = store.list_invoices(g.owner, limit, before)
    items = [{**r, "id": str(r["id"]), "created_at": r["created_at"].isoformat()} for r in rows]
    return jsonify(ok=True, items=items, next_before=items[-1]["created_at"] if len(items) == limit else None)


@bp.get("/v1/invoices/<uuid:invoice_id>")
@authenticated
def get_invoice(invoice_id):
    if (err := _need_db()):
        return err
    from . import store
    row = store.get_invoice(g.owner, invoice_id)
    if not row:  # también cuando existe pero es de otro dueño: no se revela
        return jsonify(ok=False, code="NOT_FOUND", error="No encontrada."), 404
    return jsonify(ok=True, id=str(row["id"]), provider=row["provider"], data=row["data"],
                   created_at=row["created_at"].isoformat())


@bp.delete("/v1/invoices/<uuid:invoice_id>")
@authenticated
def delete_invoice(invoice_id):
    if (err := _need_db()):
        return err
    from . import store
    if not store.delete_invoice(g.owner, invoice_id):
        return jsonify(ok=False, code="NOT_FOUND", error="No encontrada."), 404
    return jsonify(ok=True)
