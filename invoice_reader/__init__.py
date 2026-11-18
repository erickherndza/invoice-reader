import os

from flask import Flask, jsonify, send_from_directory

from . import db
from .api import bp

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB

# La UI es 100 % propia (sin CDN ni scripts inline): CSP estricta.
# El contenido extraído por el modelo es no confiable; la UI lo inserta con textContent,
# y esta política es la segunda barrera.
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; "
       "img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    app.register_blueprint(bp)
    if db.enabled():
        db.migrate()  # si falla, el arranque falla: mejor que servir sin esquema

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html", max_age=0)

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        if resp.mimetype == "application/json":
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.errorhandler(413)
    def too_big(_e):
        return jsonify(ok=False, code="PAYLOAD_TOO_LARGE",
                       error="La imagen supera el máximo de 8 MB."), 413

    return app
