"""Autenticación por API key y rate limit por clave."""
import hmac
import os
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import g, jsonify, request


def _valid_keys() -> list[str]:
    return [k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()]


def _match_key(candidate: str) -> str | None:
    # Recorre todas las claves (sin cortar en la primera) y compara en tiempo constante.
    found = None
    for key in _valid_keys():
        if hmac.compare_digest(candidate.encode(), key.encode()):
            found = key
    return found


_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def check_rate(key: str, max_calls: int, window: int) -> bool:
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= max_calls:
            return False
        q.append(now)
        return True


def reset_rate_limits() -> None:
    with _lock:
        _hits.clear()


def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _valid_keys():
            # Falla cerrado: sin claves configuradas el servicio no atiende.
            return jsonify(ok=False, code="NOT_CONFIGURED",
                           error="El servicio no tiene API_KEYS configuradas."), 503
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else request.headers.get("X-API-Key", "")
        key = _match_key(token) if token else None
        if not key:
            return jsonify(ok=False, code="UNAUTHORIZED", error="API key inválida o ausente."), 401

        max_calls = int(os.environ.get("RATE_LIMIT_MAX", "10"))
        window = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))
        if not check_rate(key, max_calls, window):
            return jsonify(ok=False, code="RATE_LIMIT",
                           error=f"Máximo {max_calls} escaneos cada {window} s."), 429
        g.api_key = key
        return fn(*args, **kwargs)
    return wrapper
