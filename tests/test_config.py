"""Pruebas para el módulo de configuración (BD_BI_TFM2: selección de fuente de datos)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import config


def test_get_data_source_default(monkeypatch):
    """Sin DATA_SOURCE definido, debe usar 'ors' por defecto."""
    monkeypatch.delenv("DATA_SOURCE", raising=False)
    monkeypatch.setattr(config, "_get_env_value_from_dotenv", lambda name: None)
    assert config.get_data_source() == "ors"


def test_get_data_source_tomtom(monkeypatch):
    """Con DATA_SOURCE=tomtom en el entorno, debe respetarlo."""
    monkeypatch.setenv("DATA_SOURCE", "tomtom")
    assert config.get_data_source() == "tomtom"


def test_get_data_source_invalid(monkeypatch):
    """Un valor inválido debe lanzar RuntimeError."""
    monkeypatch.setenv("DATA_SOURCE", "invalid_source")
    try:
        config.get_data_source()
        assert False, "Should have raised RuntimeError"
    except RuntimeError:
        pass


def test_get_timescale_config_defaults(monkeypatch):
    """Sin variables PG* definidas, deben usarse los valores de docker-compose.yml."""
    for var in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(config, "_get_env_value_from_dotenv", lambda name: None)

    cfg = config.get_timescale_config()
    assert cfg["host"] == "localhost"
    assert cfg["port"] == 5432
    assert cfg["dbname"] == "movilidad_urbana"


if __name__ == "__main__":
    print("Run with: pytest tests/test_config.py -v")
