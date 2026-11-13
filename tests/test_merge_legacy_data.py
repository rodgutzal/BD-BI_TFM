"""Pruebas de la herramienta de fusión heredada (`tools/merge_legacy_data.py`)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import merge_legacy_data as mld


def test_sin_el_csv_de_tomtom_se_detiene_sin_tocar_la_base(tmp_path, monkeypatch):
    """El CSV de TomTom ya no se publica. La herramienta borra la base unificada antes de regenerarla, así que sin ese
    archivo debe salir con un mensaje claro y dejar la base intacta (no sustituirla por una a medias)."""
    base = tmp_path / "mobility.db"
    base.write_bytes(b"datos que no se pueden perder")
    monkeypatch.setattr(mld, "LEGACY_TOMTOM_CSV", tmp_path / "no_existe.csv")
    monkeypatch.setattr(mld, "UNIFIED_DB", base)
    monkeypatch.setattr(mld, "UNIFIED_CSV", tmp_path / "unificado.csv")
    with pytest.raises(SystemExit) as salida:
        mld.main()
    assert "DATOS_Y_LICENCIAS" in str(salida.value)
    assert base.read_bytes() == b"datos que no se pueden perder"
    assert not (tmp_path / "unificado.csv").exists()
