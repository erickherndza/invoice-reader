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


# ── validación objetiva de campos ──────────────────────────────
from datetime import date

HOY = date(2026, 11, 17)
OK = {"emisor": {"valor": "ACME SRL", "score": 1.0}, "rnc": {"valor": "131-00000-2", "score": 1.0},
      "ncf": {"valor": "B0100000123", "score": 1.0}, "fecha": {"valor": "2026-11-14", "score": 1.0},
      "totales": {"base_imponible": 100, "itbis": 18, "total": 118}, "lineas": []}


def v(**cambios):
    import copy
    d = copy.deepcopy(OK)
    d.update(cambios)
    return validate(d, today=HOY)


def test_datos_validos_sin_avisos_y_score_nunca_certero():
    d = v()
    assert d["warnings"] == []
    assert all(d[k]["score"] == 0.95 for k in ("emisor", "rnc", "ncf", "fecha"))  # 1.0 del modelo -> 0.95


def test_rnc_invalido_baja_score():
    d = v(rnc={"valor": "1-31-45678-9", "score": 1.0})
    assert d["rnc"]["score"] == 0.4 and any("RNC" in w for w in d["warnings"])


def test_rnc_de_8_digitos_invalido():
    assert v(rnc={"valor": "13100002", "score": 0.9})["rnc"]["score"] == 0.4


def test_ncf_invalido():
    d = v(ncf={"valor": "ZZ123", "score": 1.0})
    assert d["ncf"]["score"] == 0.4 and any("NCF" in w for w in d["warnings"])


def test_ecf_valido():
    assert v(ncf={"valor": "E310000000005", "score": 0.9})["warnings"] == []


def test_fecha_futura_antigua_o_mal_formada():
    for bad in ("2030-01-01", "2010-05-05", "14/11/2026", "no-es-fecha"):
        d = v(fecha={"valor": bad, "score": 1.0})
        assert d["fecha"]["score"] == 0.4, bad


def test_valor_nulo_score_cero_y_sin_aviso():
    d = v(rnc={"valor": None, "score": 0.9}, emisor={"valor": "  ", "score": 0.9})
    assert d["rnc"]["score"] == 0 and d["emisor"]["valor"] is None and d["warnings"] == []


def test_campos_ausentes_o_malformados_no_rompen():
    d = validate({"rnc": "texto suelto", "lineas": [{"itbis_pct": 20}]}, today=HOY)
    assert d["rnc"] == {"valor": None, "score": 0.0}
    assert any("Línea 1" in w for w in d["warnings"])


def test_claude_ignora_bloques_thinking(monkeypatch):
    from types import SimpleNamespace as NS
    from invoice_reader import extractor
    msg = NS(content=[NS(type="thinking", thinking="..."), NS(type="text", text='{"a": 1}')],
             usage=NS(input_tokens=10, output_tokens=5), stop_reason="end_turn")
    fake = NS(messages=NS(create=lambda **k: msg))
    import anthropic
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(anthropic, "Anthropic", lambda api_key: fake)
    text, usage = extractor._claude(b"x", "image/png")
    assert text == '{"a": 1}' and usage == {"input": 10, "output": 5}
