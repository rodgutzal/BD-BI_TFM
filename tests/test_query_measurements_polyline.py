"""Pruebas de `include_polyline` en RouteDatabase.query_measurements.

Regresión: query_measurements hacía `SELECT *` e incluía `polyline` (el JSON de la
geometría de la ruta, ~4,5 KB por fila). En la base real eso es el 93% del tamaño en
memoria de la tabla (339 de 365 MB con 78.561 filas) y, repetido por cada pestaña y por
la caché de Streamlit, agotaba el límite de 1 GiB del contenedor del dashboard al abrir
Analyst (el proceso moría por falta de memoria).
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import RouteDatabase

AHORA = datetime.now(timezone.utc)
POLILINEA = [[35.9 + i * 1e-4, 14.5 + i * 1e-4] for i in range(400)]     # ~12 KB en JSON


def _registro(minutos_atras, origin="Msida", destination="Gzira", minutos=10.0):
    return {
        "timestamp": (AHORA - timedelta(minutes=minutos_atras)).isoformat(),
        "origin": origin, "destination": destination, "data_source": "tomtom",
        "travel_time_min": minutos, "distance_km": 3.0, "polyline": POLILINEA,
    }


@pytest.fixture
def db(tmp_path):
    base = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    base.save_records_to_sqlite([_registro(i, minutos=10.0 + i) for i in range(40)]
                                + [_registro(5, "Valletta", "Sliema", 20.0)])
    return base


def test_por_defecto_no_carga_la_polilinea(db):
    df = db.query_measurements(limit=1000)
    assert "polyline" not in df.columns
    assert len(df) == 41


def test_include_polyline_la_devuelve_intacta(db):
    df = db.query_measurements(limit=1000, include_polyline=True)
    assert "polyline" in df.columns
    assert json.loads(df.iloc[0]["polyline"]) == POLILINEA


def test_las_demas_columnas_son_exactamente_las_mismas(db):
    sin = db.query_measurements(limit=1000)
    con = db.query_measurements(limit=1000, include_polyline=True)
    assert list(sin.columns) == [c for c in con.columns if c != "polyline"]
    pd.testing.assert_frame_equal(sin.reset_index(drop=True), con.drop(columns="polyline").reset_index(drop=True))


def test_los_filtros_y_el_orden_no_cambian(db):
    solo_msida = db.query_measurements(origin="Msida", destination="Gzira", limit=1000)
    assert len(solo_msida) == 40 and set(solo_msida["origin"]) == {"Msida"}
    assert solo_msida["timestamp"].is_monotonic_decreasing       # más reciente primero
    assert len(db.query_measurements(limit=5)) == 5

    desde = (AHORA - timedelta(minutes=10)).isoformat()
    recientes = db.query_measurements(start_timestamp=desde, limit=1000)
    assert 0 < len(recientes) < 41


def test_sin_la_polilinea_la_memoria_baja_mucho(db):
    """No es una cifra mágica: con polilíneas de ~12 KB, cargarlas pesa >10× lo que pesa el resto."""
    con = db.query_measurements(limit=1000, include_polyline=True).memory_usage(deep=True).sum()
    sin = db.query_measurements(limit=1000).memory_usage(deep=True).sum()
    assert con > 10 * sin, f"con={con:,} sin={sin:,}"


def test_base_vacia_no_falla(tmp_path):
    vacia = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    assert vacia.query_measurements().empty


def test_export_route_data_conserva_la_polilinea(db, tmp_path):
    """La exportación por ruta no cambia: sigue incluyendo la geometría."""
    destino = tmp_path / "ruta.csv"
    assert db.export_route_data("Msida", "Gzira", destino)
    exportado = pd.read_csv(destino)
    assert "polyline" in exportado.columns
    assert json.loads(exportado.iloc[0]["polyline"]) == POLILINEA
