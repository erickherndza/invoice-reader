"""Integración con PostgreSQL real. Se omite sin TEST_DATABASE_URL.

Vacía tablas: por eso exige que el nombre de la base contenga 'test'.
"""
import base64
import os

import pytest

URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL no definida")

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
A, B = {"Authorization": "Bearer key-a"}, {"Authorization": "Bearer key-b"}
BODY = {"image": base64.b64encode(PNG).decode()}


@pytest.fixture
def client(monkeypatch):
    assert URL.rsplit("/", 1)[-1].split("?")[0].find("test") >= 0, "TEST_DATABASE_URL debe apuntar a una base *test*"
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("API_KEYS", "key-a,key-b")
    monkeypatch.setenv("RATE_LIMIT_MAX", "3")
    from invoice_reader import create_app, api, db
    monkeypatch.setattr(api, "extract_invoice", lambda b, m: {
        "provider": "t", "emisor": {"valor": "ACME SRL", "score": .9}, "ncf": {"valor": "B0100000001", "score": .9},
        "totales": {"base_imponible": 100, "itbis": 18, "total": 118}, "warnings": []})
    app = create_app()
    with db.pool().connection() as c:
        c.execute("TRUNCATE invoices, rate_hits")
    yield app.test_client()
    db.close()


def extract(c, h=A):
    return c.post("/v1/invoices/extract", json=BODY, headers=h)


def test_ready_con_db(client):
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json["db"] == "up"


def test_guarda_lista_y_obtiene(client):
    r = extract(client)
    assert r.status_code == 200 and r.json["id"]
    lst = client.get("/v1/invoices", headers=A).json
    assert lst["items"][0]["emisor"] == "ACME SRL" and lst["items"][0]["total"] == "118"
    one = client.get(f"/v1/invoices/{r.json['id']}", headers=A)
    assert one.status_code == 200 and one.json["data"]["ncf"]["valor"] == "B0100000001"


def test_aislamiento_entre_claves(client):
    inv = extract(client, A).json["id"]
    assert client.get("/v1/invoices", headers=B).json["items"] == []
    assert client.get(f"/v1/invoices/{inv}", headers=B).status_code == 404
    assert client.delete(f"/v1/invoices/{inv}", headers=B).status_code == 404
    assert client.get(f"/v1/invoices/{inv}", headers=A).status_code == 200  # sigue intacta


def test_borrar(client):
    inv = extract(client).json["id"]
    assert client.delete(f"/v1/invoices/{inv}", headers=A).status_code == 200
    assert client.get(f"/v1/invoices/{inv}", headers=A).status_code == 404


def test_rate_limit_en_sql_no_cuenta_historial(client):
    assert [extract(client).status_code for _ in range(4)] == [200, 200, 200, 429]
    assert client.get("/v1/invoices", headers=A).status_code == 200  # consultar no gasta cupo
    assert extract(client, B).status_code == 200  # otra clave, otro cupo


def test_no_se_guarda_la_clave_en_claro(client):
    extract(client)
    from invoice_reader import db
    with db.pool().connection() as c:
        owners = [r["owner"] for r in c.execute("SELECT owner FROM invoices UNION SELECT owner FROM rate_hits")]
    assert owners and all("key-a" not in o and len(o) == 32 for o in owners)


def test_id_invalido_404_y_paginacion(client):
    assert client.get("/v1/invoices/no-es-uuid", headers=A).status_code == 404
    for _ in range(3):
        extract(client)
    page = client.get("/v1/invoices?limit=2", headers=A).json
    assert len(page["items"]) == 2 and page["next_before"]
    assert client.get("/v1/invoices?limit=x", headers=A).status_code == 400


def test_sin_auth_401(client):
    assert client.get("/v1/invoices").status_code == 401
