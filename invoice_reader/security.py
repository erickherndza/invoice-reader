"""Autenticación por API key y rate limit por clave."""
import hashlib
import hmac
import os
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import g, jsonify, request

from . import db


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


def owner_id(key: str) -> str:
    """Identificador estable y no reversible del dueño (la clave nunca se guarda)."""
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def reset_rate_limits() -> None:
    with _lock:
        _hits.clear()


def _authenticate():
    """Devuelve (owner, None) o (None, respuesta_de_error)."""
    if not _valid_keys():
        # Falla cerrado: sin claves configuradas el servicio no atiende.
        return None, (jsonify(ok=False, code="NOT_CONFIGURED",
                              error="El servicio no tiene API_KEYS configuradas."), 503)
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else request.headers.get("X-API-Key", "")
    key = _match_key(token) if token else None
    if not key:
        return None, (jsonify(ok=False, code="UNAUTHORIZED", error="API key inválida o ausente."), 401)
    return owner_id(key), None


def _rate_ok(owner: str) -> bool:
    max_calls = int(os.environ.get("RATE_LIMIT_MAX", "10"))
    window = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))
    if db.enabled():
        from . import store
        return store.check_rate(owner, max_calls, window)
    return check_rate(owner, max_calls, window)


def authenticated(fn):
    """Solo autenticación (consultas baratas: historial)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        owner, err = _authenticate()
        if err:
            return err
        g.owner = owner
        return fn(*args, **kwargs)
    return wrapper


def require_api_key(fn):
    """Autenticación + rate limit (operaciones que gastan cuota del LLM)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        owner, err = _authenticate()
        if err:
            return err
        try:
            allowed = _rate_ok(owner)
        except Exception:
            return jsonify(ok=False, code="DB_UNAVAILABLE", error="Base de datos no disponible."), 503
        if not allowed:
            return jsonify(ok=False, code="RATE_LIMIT",
                           error="Demasiados escaneos seguidos. Espera un momento."), 429
        g.owner = owner
        return fn(*args, **kwargs)
    return wrapper
