"""Pruebas del estado por ruta del dashboard Operations.

Regresión: el estado salía de `traffic_delay_min` de la última fila, y `_safe()`
convertía el NULL en 0. ORS no reporta tráfico (el 100% de sus filas lo trae
NULL), así que cualquier ruta cuya última medición fuera de ORS aparecía como
"🟢 Free Flow" sin ningún dato detrás.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import RouteDatabase
from streamlit_app.dashboards.operations_dashboard import (
    STALE_TRAFFIC_MINUTES,
    build_route_status_grid,
)

AHORA = datetime.now(timezone.utc)


def _fila(minutos_atras, origin, destination, fuente, delay, viaje=10.0, velocidad=30.0):
    return {
        "timestamp": (AHORA - timedelta(minutes=minutos_atras)).isoformat(),
        "origin": origin, "destination": destination, "data_source": fuente,
        "travel_time_min": viaje, "traffic_delay_min": delay, "average_speed_kmh": velocidad,
        "distance_km": 3.0, "polyline": [[35.9, 14.5], [35.8, 14.4]],
    }


@pytest.fixture
def db(tmp_path):
    return RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")


# ---------------------------------------------------------------------------
# get_latest_per_route
# ---------------------------------------------------------------------------

def test_ultima_medicion_de_cada_ruta_en_una_consulta(db):
    db.save_records_to_sqlite([
        _fila(30, "Msida", "Gzira", "ors", None, viaje=5.0),
        _fila(5, "Msida", "Gzira", "ors", None, viaje=6.0),      # la más reciente de Msida→Gzira
        _fila(20, "Msida", "Sliema", "tomtom", 2.0, viaje=9.0),
    ])
    latest = db.get_latest_per_route().set_index(["origin", "destination"])
    assert len(latest) == 2
    assert latest.loc[("Msida", "Gzira"), "travel_time_min"] == 6.0
    assert latest.loc[("Msida", "Sliema"), "travel_time_min"] == 9.0


def test_no_trae_la_polilinea(db):
    db.save_records_to_sqlite([_fila(5, "Msida", "Gzira", "ors", None)])
    assert "polyline" not in db.get_latest_per_route().columns
    assert "rn" not in db.get_latest_per_route().columns


def test_require_column_trae_la_ultima_fila_que_tiene_ese_dato(db):
    db.save_records_to_sqlite([
        _fila(40, "Msida", "Gzira", "tomtom", 3.5),   # última CON tráfico
        _fila(5, "Msida", "Gzira", "ors", None),      # la más reciente, pero sin tráfico
    ])
    con_trafico = db.get_latest_per_route(require_column="traffic_delay_min")
    assert len(con_trafico) == 1
    assert con_trafico.iloc[0]["data_source"] == "tomtom"
    assert con_trafico.iloc[0]["traffic_delay_min"] == 3.5


def test_require_column_omite_las_rutas_que_nunca_tuvieron_ese_dato(db):
    db.save_records_to_sqlite([_fila(5, "Msida", "Gzira", "ors", None)])
    assert db.get_latest_per_route(require_column="traffic_delay_min").empty


def test_require_column_rechaza_columnas_inexistentes(db):
    with pytest.raises(ValueError):
        db.get_latest_per_route(require_column="no_existe; DROP TABLE route_measurements")


def test_base_vacia(db):
    assert db.get_latest_per_route().empty


# ---------------------------------------------------------------------------
# build_route_status_grid
# ---------------------------------------------------------------------------

def _grid(db):
    return build_route_status_grid(
        db.get_latest_per_route(),
        db.get_latest_per_route(require_column="traffic_delay_min"),
        now=pd.Timestamp(AHORA),
    ).set_index("Route")


def test_ruta_cuya_ultima_medicion_es_de_ors_usa_la_lectura_de_tomtom(db):
    db.save_records_to_sqlite([
        _fila(20, "Msida", "Gzira", "tomtom", 0.5),
        _fila(3, "Msida", "Gzira", "ors", None, viaje=7.0),
    ])
    g = _grid(db).loc["Msida → Gzira"]
    assert g["Status"] == "🟢 Free Flow"
    assert g["Delay"] == "0.5 min"                    # el retraso de TomTom, no un 0.0 inventado
    assert g["Travel Time"] == "7.0 min"              # la última medición, de ORS
    assert "tomtom" in g["Traffic reading"] and "hace 20 min" in g["Traffic reading"]
    assert "ors" in g["Last measurement"]


def test_ruta_sin_ninguna_lectura_de_trafico_nunca_se_pinta_de_verde(db):
    """El bug: la última fila es de ORS (delay NULL) -> antes '🟢 Free Flow'."""
    db.save_records_to_sqlite([_fila(3, "Valletta", "Sliema", "ors", None)])
    g = _grid(db).loc["Valletta → Sliema"]
    assert g["Status"] == "⚪ Sin dato de tráfico"
    assert g["Delay"] == "sin dato"
    assert "Free Flow" not in g["Status"]


def test_lectura_de_trafico_desactualizada_se_avisa(db):
    db.save_records_to_sqlite([
        _fila(STALE_TRAFFIC_MINUTES + 30, "Msida", "Gzira", "tomtom", 0.2),
        _fila(2, "Msida", "Gzira", "ors", None),
    ])
    assert _grid(db).loc["Msida → Gzira", "Status"] == "⚪ Lectura desactualizada"


@pytest.mark.parametrize("delay, esperado", [
    (0.0, "🟢 Free Flow"), (1.0, "🟢 Free Flow"),
    (2.5, "🟡 Moderate"), (4.0, "🟡 Moderate"),
    (4.1, "🔴 Heavy"), (12.0, "🔴 Heavy"),
])
def test_umbrales_de_estado(db, delay, esperado):
    db.save_records_to_sqlite([_fila(5, "Msida", "Gzira", "tomtom", delay)])
    assert _grid(db).loc["Msida → Gzira", "Status"] == esperado


def test_una_fila_por_ruta_con_las_columnas_esperadas(db):
    db.save_records_to_sqlite([
        _fila(5, "Msida", "Gzira", "tomtom", 1.0),
        _fila(5, "Msida", "Sliema", "ors", None),
    ])
    g = build_route_status_grid(
        db.get_latest_per_route(), db.get_latest_per_route(require_column="traffic_delay_min"),
        now=pd.Timestamp(AHORA),
    )
    assert len(g) == 2
    assert list(g.columns) == ["Route", "Status", "Travel Time", "Delay", "Speed",
                               "Traffic reading", "Last measurement"]
