"""Conexión a PostgreSQL (opcional: sin DATABASE_URL el servicio funciona sin historial)."""
import os
import threading
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
_pool: ConnectionPool | None = None
_lock = threading.Lock()


def enabled() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def pool() -> ConnectionPool:
    global _pool
    with _lock:
        if _pool is None:
            _pool = ConnectionPool(
                os.environ["DATABASE_URL"],
                min_size=1,
                max_size=int(os.environ.get("DB_POOL_MAX", "5")),
                kwargs={"row_factory": dict_row},
                open=True,
            )
        return _pool


def close() -> None:
    global _pool
    with _lock:
        if _pool is not None:
            _pool.close()
            _pool = None


def migrate() -> None:
    """Aplica migrations/*.sql una sola vez. El lock evita carreras entre workers de gunicorn."""
    with pool().connection() as c:
        c.execute("SELECT pg_advisory_xact_lock(727274)")
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                  "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        done = {r["name"] for r in c.execute("SELECT name FROM schema_migrations")}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name not in done:
                c.execute(f.read_text(encoding="utf-8"))
                c.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (f.name,))


def ping() -> bool:
    with pool().connection() as c:
        return c.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
