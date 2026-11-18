import pytest

from invoice_reader import create_app


@pytest.fixture
def client():
    return create_app().test_client()


def test_index_y_assets(client):
    r = client.get("/")
    assert r.status_code == 200 and b"Invoice Reader" in r.data
    for path in ("/static/app.js", "/static/app.css", "/static/fonts/inter-latin.woff2",
                 "/static/fonts/space-grotesk-latin.woff2"):
        assert client.get(path).status_code == 200, path


def test_cabeceras_seguridad(client):
    h = client.get("/").headers
    assert "script-src 'self'" in h["Content-Security-Policy"]
    assert "unsafe-inline" not in h["Content-Security-Policy"]
    assert "unsafe-eval" not in h["Content-Security-Policy"]
    assert h["X-Content-Type-Options"] == "nosniff"
    assert "camera=(self)" in h["Permissions-Policy"]


def test_ui_sin_innerhtml_ni_recursos_externos():
    import pathlib
    root = pathlib.Path(__file__).parent.parent / "invoice_reader" / "static"
    js = (root / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "eval(" not in js
    for f in ("index.html", "app.css"):
        assert "http://" not in (root / f).read_text(encoding="utf-8").replace("http://www.w3.org", "")
        assert "https://" not in (root / f).read_text(encoding="utf-8")


def test_api_json_no_cache(client, monkeypatch):
    monkeypatch.setenv("API_KEYS", "k")
    r = client.post("/v1/invoices/extract", json={})
    assert r.headers["Cache-Control"] == "no-store"
