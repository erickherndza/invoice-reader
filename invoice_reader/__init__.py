import os

from flask import Flask, jsonify

from .api import bp

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    app.register_blueprint(bp)

    @app.errorhandler(413)
    def too_big(_e):
        return jsonify(ok=False, code="PAYLOAD_TOO_LARGE",
                       error="La imagen supera el máximo de 8 MB."), 413

    return app
