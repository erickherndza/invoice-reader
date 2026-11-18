import base64

import pytest

from invoice_reader import create_app, api
from invoice_reader.extractor import ExtractionError, parse_response, validate
from invoice_reader.security import reset_rate_limits

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
H = {"Authorization": "Bearer k1"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1,k2")
    monkeypatch.setenv("RATE_LIMIT_MAX", "3")
    reset_rate_limits()
    monkeypatch.setattr(api, "extract_invoice", lambda b, m: {"provider": "t", "warnings": []})
    return create_app().test_client()


def post(c, body, headers=H):
    return c.post("/v1/invoices/extract", json=body, headers=headers)


def test_health(client):
    assert client.get("/health").status_code == 200


def test_sin_key_401(client):
    assert post(client, {"image": "x"}, headers={}).status_code == 401


def test_key_mala_401(client):
    assert post(client, {"image": "x"}, headers={"X-API-Key": "nope"}).status_code == 401


def test_sin_keys_configuradas_503(client, monkeypatch):
    monkeypatch.setenv("API_KEYS", "")
    assert post(client, {"image": "x"}).status_code == 503


def test_ok(client):
    r = post(client, {"image": base64.b64encode(PNG).decode()})
    assert r.status_code == 200 and r.json["ok"] and r.json["provider"] == "t"


def test_tipo_falso_415(client):  # declara PNG pero es texto
    assert post(client, {"image": base64.b64encode(b"hola").decode()}).status_code == 415


def test_base64_invalido_400(client):
    assert post(client, {"image": "@@@"}).status_code == 400


def test_multipart(client):
    import io
    r = client.post("/v1/invoices/extract", headers=H,
                    data={"file": (io.BytesIO(PNG), "f.png")}, content_type="multipart/form-data")
    assert r.status_code == 200


def test_rate_limit_429(client):
    b = {"image": base64.b64encode(PNG).decode()}
    codes = [post(client, b).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_error_proveedor_503(client, monkeypatch):
    def boom(b, m): raise ExtractionError("GROQ_API_KEY no configurada")
    monkeypatch.setattr(api, "extract_invoice", boom)
    assert post(client, {"image": base64.b64encode(PNG).decode()}).status_code == 503


def test_parse_markdown():
    assert parse_response('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_sin_json():
    with pytest.raises(ExtractionError):
        parse_response("sin json")


def test_validate_totales():
    d = validate({"totales": {"base_imponible": 100, "itbis": 18, "total": 120}, "lineas": []})
    assert any("no coincide" in w for w in d["warnings"])
    d = validate({"totales": {"base_imponible": 100, "itbis": 18, "total": 118.01}, "lineas": []})
    assert d["warnings"] == []
