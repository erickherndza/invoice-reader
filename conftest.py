import pytest


@pytest.fixture(autouse=True)
def _sin_db_por_defecto(monkeypatch):
    """Los tests unitarios no deben tocar una base real aunque DATABASE_URL esté definida."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
