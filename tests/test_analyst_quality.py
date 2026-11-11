"""Pruebas de Analyst: abrir la pantalla usa UN perfil de la base y no las consultas caras de antes.

Regresión (medido en el bind mount de Windows de Docker, donde cada recorrido de la tabla cuesta ~8 s):
  - `get_available_routes()` (un SELECT DISTINCT que recorre toda la tabla) se llamaba 4 veces;
  - la completitud por ruta hacía 12 consultas (33 s);
  - "Missing Values" cargaba 100 mil filas en un DataFrame (15 s);
  - `get_all_routes_statistics()` recorría la tabla otra vez solo para contar filas por ruta.
Todo eso sale ahora de `get_data_profile()`, una sola pasada.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from streamlit.testing.v1 import AppTest

from src.database import RouteDatabase
from streamlit_app.dashboards import analyst_dashboard as ad

AHORA = datetime.now(timezone.utc)
APP = f"""
import sys
sys.path.insert(0, r'{ROOT}')
from streamlit_app.dashboards import analyst_dashboard as ad
ad.main()
"""


def _fila(i, origin, destination, **extra):
    base = {
        "timestamp": (AHORA - timedelta(hours=i)).isoformat(),
        "origin": origin, "destination": destination, "data_source": "tomtom",
        "travel_time_min": 10.0 + (i % 5), "distance_km": 3.0, "average_speed_kmh": 30.0,
        "traffic_delay_min": 1.0, "origin_temperature": 20.0 + (i % 4), "origin_humidity": 50.0,
    }
    base.update(extra)
    return base


@pytest.fixture
def espia(tmp_path, monkeypatch):
    """Base temporal con 3 rutas + un espía sobre los métodos de RouteDatabase."""
    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    db.save_records_to_sqlite(
        [_fila(i, "Msida", "Gzira") for i in range(60)]
        + [_fila(i, "Msida", "Sliema", traffic_delay_min=None) for i in range(40)]
        + [_fila(i, "Valletta", "Sliema") for i in range(20)]
    )
    st.cache_data.clear()
    monkeypatch.setattr(ad, "get_database", lambda: db)
    monkeypatch.setattr(ad.predictive_modeling_dashboard, "render", lambda: None)   # el modelado ya tiene sus propios tests

    llamadas = {"get_available_routes": 0, "get_all_routes_statistics": 0, "get_data_profile": 0, "query_measurements": []}
    for nombre in ("get_available_routes", "get_all_routes_statistics", "get_data_profile"):
        original = getattr(RouteDatabase, nombre)

        def envoltorio(self, *a, _n=nombre, _o=original, **k):
            llamadas[_n] += 1
            return _o(self, *a, **k)

        monkeypatch.setattr(RouteDatabase, nombre, envoltorio)

    original_q = RouteDatabase.query_measurements

    def q(self, *a, **k):
        llamadas["query_measurements"].append({"args": a, "kwargs": dict(k)})
        return original_q(self, *a, **k)

    monkeypatch.setattr(RouteDatabase, "query_measurements", q)
    yield db, llamadas
    st.cache_data.clear()


def _abrir():
    at = AppTest.from_string(APP, default_timeout=120)
    at.run()
    return at


def _metricas(at):
    return {m.label: m.value for m in at.metric}


def test_abrir_analyst_no_usa_las_consultas_caras(espia):
    """Abrir el Analyst no lanza `get_available_routes` ni `get_all_routes_statistics`; hace un único `get_data_profile` compartido por todas las pestañas."""
    db, llamadas = espia
    at = _abrir()
    assert not at.exception, [e.value for e in at.exception]
    assert llamadas["get_available_routes"] == 0, "las rutas salen del perfil, no de un SELECT DISTINCT"
    assert llamadas["get_all_routes_statistics"] == 0, "los conteos por ruta salen del perfil"
    assert llamadas["get_data_profile"] == 1, "un único recorrido, compartido por todas las pestañas"


def test_ninguna_consulta_carga_la_base_entera(espia):
    """'Missing Values' ya no carga 100 mil filas: toda lectura de filas es de UNA ruta."""
    db, llamadas = espia
    _abrir()
    assert llamadas["query_measurements"], "el explorador y los tests estadísticos sí leen la ruta elegida"
    for c in llamadas["query_measurements"]:
        k = c["kwargs"]
        assert k.get("origin") and k.get("destination"), f"lectura sin filtrar por ruta: {c}"


def test_las_metricas_de_calidad_son_las_del_perfil(espia):
    """Total de registros, valores faltantes, duplicados y rango de fechas de la pestaña de calidad coinciden con los del perfil de datos."""
    db, _ = espia
    p = db.get_data_profile()
    m = _metricas(_abrir())
    assert m["Total Records"] == f"{p['total_rows']:,}" == "120"
    assert m["Missing Values"] == f"{p['missing_pct']:.1f}%"
    assert m["Duplicates"] == "0"
    assert m["Date Range"].endswith("days")


def test_la_completitud_por_ruta_sale_del_perfil_y_cubre_todas_las_rutas(espia):
    """La tabla de completitud sale del perfil, trae todas las rutas y la ruta con `traffic_delay_min` vacío es menos completa que la que lo trae."""
    db, _ = espia
    at = _abrir()
    tablas = [t.value for t in at.dataframe if "Completeness" in getattr(t.value, "columns", [])]
    assert len(tablas) == 1
    comp = tablas[0].set_index("Route")
    assert set(comp.index) == {"Msida → Gzira", "Msida → Sliema", "Valletta → Sliema"}
    assert comp.loc["Msida → Gzira", "Records"] == 60
    # la ruta con traffic_delay_min vacío es menos completa que la que lo trae
    pct = lambda r: float(comp.loc[r, "Completeness"].rstrip("%"))
    assert pct("Msida → Sliema") < pct("Msida → Gzira")


def test_las_muestras_por_ruta_de_model_performance_son_las_filas_reales(espia):
    """La tabla de muestras por ruta de Model Performance cuenta las filas reales de cada ruta."""
    db, _ = espia
    at = _abrir()
    tablas = [t.value for t in at.dataframe if "Samples" in getattr(t.value, "columns", [])]
    assert len(tablas) == 1
    muestras = tablas[0].set_index("Route")["Samples"].to_dict()
    assert muestras == {"Msida → Gzira": 60, "Msida → Sliema": 40, "Valletta → Sliema": 20}


def test_el_panel_lateral_usa_el_ultimo_timestamp_y_no_el_resumen_completo(tmp_path, monkeypatch):
    """app.py pedía get_database_summary() (con el DISTINCT de rutas) solo para la hora del último dato."""
    from streamlit_app import app

    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    db.save_records_to_sqlite([_fila(i, "Msida", "Gzira") for i in range(5)])
    st.cache_data.clear()
    resumen = []
    original = RouteDatabase.get_database_summary
    monkeypatch.setattr(RouteDatabase, "get_database_summary", lambda self, *a, **k: resumen.append(1) or original(self, *a, **k))
    assert app._last_measurement_timestamp(db) == db.get_last_timestamp()
    assert resumen == [], "no debe construir el resumen completo para sacar una fecha"
    st.cache_data.clear()
