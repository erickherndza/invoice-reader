"""Consultas SQL. Todas con parámetros (%s) y acotadas al dueño (owner)."""
from psycopg.types.json import Jsonb

from . import db


def check_rate(owner: str, max_calls: int, window: int) -> bool:
    with db.pool().connection() as c:
        # Serializa por dueño: dos peticiones simultáneas no pueden pasarse del límite.
        c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (owner,))
        c.execute("DELETE FROM rate_hits WHERE owner = %s AND ts < now() - make_interval(secs => %s)",
                  (owner, window))
        n = c.execute("SELECT count(*) AS n FROM rate_hits WHERE owner = %s", (owner,)).fetchone()["n"]
        if n >= max_calls:
            return False
        c.execute("INSERT INTO rate_hits (owner) VALUES (%s)", (owner,))
        return True


def insert_invoice(owner: str, provider: str, data: dict):
    with db.pool().connection() as c:
        return c.execute(
            "INSERT INTO invoices (owner, provider, data) VALUES (%s, %s, %s) RETURNING id",
            (owner, provider, Jsonb(data)),
        ).fetchone()["id"]


def list_invoices(owner: str, limit: int, before=None):
    with db.pool().connection() as c:
        return c.execute(
            """SELECT id, provider, created_at,
                      data->'emisor'->>'valor'  AS emisor,
                      data->'ncf'->>'valor'     AS ncf,
                      data->'totales'->>'total' AS total
                 FROM invoices
                WHERE owner = %s AND (%s::timestamptz IS NULL OR created_at < %s::timestamptz)
                ORDER BY created_at DESC LIMIT %s""",
            (owner, before, before, limit),
        ).fetchall()


def get_invoice(owner: str, invoice_id):
    with db.pool().connection() as c:
        return c.execute(
            "SELECT id, provider, data, created_at FROM invoices WHERE id = %s AND owner = %s",
            (invoice_id, owner),
        ).fetchone()


def delete_invoice(owner: str, invoice_id) -> bool:
    with db.pool().connection() as c:
        return c.execute("DELETE FROM invoices WHERE id = %s AND owner = %s",
                         (invoice_id, owner)).rowcount > 0
