import base64
import binascii

from flask import Blueprint, jsonify, request

from .extractor import ExtractionError, extract_invoice
from .images import ALLOWED, sniff_media_type
from .security import require_api_key

bp = Blueprint("api", __name__)


@bp.get("/health")
def health():
    return jsonify(ok=True, service="invoice-reader")


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
        return jsonify(ok=False, code="OCR_ERROR", error="Error procesando la imagen."), 502

    provider = data.pop("provider", "?")
    return jsonify(ok=True, provider=provider, data=data, warnings=data.get("warnings", []))
