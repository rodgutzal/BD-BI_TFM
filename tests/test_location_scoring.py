"""Pruebas del sistema de puntuación de zonas (MCDA) de location_scoring.py.

Usan una RouteDatabase real sobre un directorio temporal (no mocks), para
ejercitar también los métodos de database.py que consume el módulo.
"""

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import RouteDatabase
from src.location_scoring import (
    DEFAULT_WEIGHTS,
    FOOD_DRINK_OSM_COVERAGE,
    _haversine_m,
    _normalize_minmax,
    recommend_locations,
    score_zones,
    zone_accessibility,
    zone_competition,
    zone_demand,
)
from src.locations import LOCATIONS


@pytest.fixture
def db(tmp_path):
    return RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")


def _poi(i, category, zona, dlat=0.0):
    loc = LOCATIONS[zona]
    return {
        "osm_type": "node", "osm_id": i, "category": category, "subcategory": "x",
        "name": f"poi{i}", "latitude": loc.latitude + dlat, "longitude": loc.longitude,
    }


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------

def test_haversine_conocida():
    # 0.01 grados de latitud ~ 1112 m
    assert _haversine_m(35.0, 14.0, 35.01, 14.0) == pytest.approx(1112, abs=5)
    assert _haversine_m(35.9, 14.5, 35.9, 14.5) == 0


def test_normalize_minmax_basico():
    out = _normalize_minmax(pd.Series([10.0, 20.0, 30.0]))
    assert list(out) == [0.0, 0.5, 1.0]


def test_normalize_minmax_sin_variacion_queda_en_medio_no_en_cero():
    out = _normalize_minmax(pd.Series([5.0, 5.0, 5.0]))
    assert list(out) == [0.5, 0.5, 0.5]


def test_normalize_minmax_conserva_nan():
    out = _normalize_minmax(pd.Series([1.0, float("nan"), 3.0]))
    assert out.iloc[0] == 0.0 and out.iloc[2] == 1.0
    assert math.isnan(out.iloc[1])


# ---------------------------------------------------------------------------
# dimensiones
# ---------------------------------------------------------------------------

def test_demanda_sin_demografia_es_nan_no_cero(db):
    out = zone_demand(db)
    assert list(out.index) == list(LOCATIONS)
    assert out["demanda"].isna().all()


def test_demanda_lee_poblacion_guardada(db):
    db.save_demographics([{"zone_name": "Sliema", "population": 23000}])
    out = zone_demand(db)
    assert out.loc["Sliema", "demanda"] == 23000
    assert math.isnan(out.loc["Msida", "demanda"])


def test_competencia_cuenta_solo_dentro_del_radio(db):
    # 2 comercios en Sliema, 1 a ~2.2 km (fuera del radio de 1.500 m)
    db.save_pois([
        _poi(1, "business", "Sliema"),
        _poi(2, "business", "Sliema", dlat=0.001),
        _poi(3, "business", "Sliema", dlat=0.02),
    ])
    out = zone_competition(db, "business")
    assert out.loc["Sliema", "competencia"] == 2
    assert out.loc["Sliema", "metodo_competencia"] == "observado"
    assert out.loc["Marsaskala", "competencia"] == 0


def test_competencia_filtra_por_categoria(db):
    db.save_pois([_poi(1, "business", "Sliema"), _poi(2, "school", "Sliema")])
    assert zone_competition(db, "school").loc["Sliema", "competencia"] == 1


def test_competencia_food_drink_se_corrige_por_cobertura_de_osm(db):
    db.save_pois([_poi(i, "food_drink", "Sliema", dlat=0.0001 * i) for i in range(1, 7)])
    out = zone_competition(db, "food_drink")
    assert out.loc["Sliema", "competencia_cruda"] == 6
    assert out.loc["Sliema", "competencia"] == pytest.approx(6 / FOOD_DRINK_OSM_COVERAGE)
    assert out.loc["Sliema", "metodo_competencia"] == "corregido_por_cobertura"


def test_competencia_sin_pois_es_cero(db):
    assert (zone_competition(db, "business")["competencia"] == 0).all()


def _medicion(ts, origin, destination, minutos):
    return {
        "timestamp": ts.isoformat(), "origin": origin, "destination": destination,
        "data_source": "tomtom", "travel_time_min": minutos, "distance_km": 3.0,
    }


def test_accesibilidad_promedia_rutas_que_tocan_la_zona(db):
    ahora = datetime.now(timezone.utc)
    db.save_records_to_sqlite([
        _medicion(ahora - timedelta(minutes=5), "Msida", "Gzira", 10.0),
        _medicion(ahora - timedelta(minutes=10), "Msida", "Gzira", 14.0),   # prom. ruta = 12
        _medicion(ahora - timedelta(minutes=5), "Msida", "Sliema", 20.0),
    ])
    out = zone_accessibility(db)
    assert out.loc["Gzira", "tiempo_viaje_prom"] == pytest.approx(12.0)
    assert out.loc["Msida", "tiempo_viaje_prom"] == pytest.approx(16.0)  # (12 + 20) / 2, como origen
    assert math.isnan(out.loc["Birkirkara", "tiempo_viaje_prom"])


# ---------------------------------------------------------------------------
# score_zones
# ---------------------------------------------------------------------------

def _features(**cols):
    zonas = ["A", "B", "C"]
    base = {"demanda": [100.0, 200.0, 300.0], "competencia": [5.0, 5.0, 5.0],
            "tiempo_viaje_prom": [10.0, 10.0, 10.0]}
    base.update(cols)
    return pd.DataFrame(base, index=pd.Index(zonas, name="zone_name"))


def test_pesos_por_defecto_suman_uno():
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)
    assert DEFAULT_WEIGHTS == {"demanda": 0.40, "competencia": 0.35, "accesibilidad": 0.25}


def test_pesos_que_no_suman_uno_lanzan_error():
    with pytest.raises(ValueError):
        score_zones(_features(), {"demanda": 0.5, "competencia": 0.5, "accesibilidad": 0.5})


def test_mas_demanda_mejora_el_puntaje():
    out = score_zones(_features())
    assert list(out.index) == ["C", "B", "A"]


def test_mas_competencia_empeora_el_puntaje():
    out = score_zones(_features(demanda=[100.0, 100.0, 100.0], competencia=[1.0, 5.0, 9.0]))
    assert list(out.index) == ["A", "B", "C"]


def test_mas_tiempo_de_viaje_empeora_el_puntaje():
    out = score_zones(_features(demanda=[100.0] * 3, tiempo_viaje_prom=[5.0, 15.0, 30.0]))
    assert list(out.index) == ["A", "B", "C"]


def test_zona_sin_dato_se_trata_como_neutral_no_como_la_peor():
    out = score_zones(_features(demanda=[100.0, float("nan"), 300.0]))
    assert out.loc["B", "demanda_norm"] != out.loc["B", "demanda_norm"]  # NaN en la columna normalizada
    # pero el puntaje usa 0.5 en esa dimensión: queda entre la peor (A) y la mejor (C)
    assert out.loc["A", "score"] < out.loc["B", "score"] < out.loc["C", "score"]
    assert out.loc["B", "dimensiones_con_dato"] == 2
    assert out.loc["A", "dimensiones_con_dato"] == 3


def test_un_peso_en_cero_ignora_esa_dimension():
    out = score_zones(_features(), {"demanda": 0.0, "competencia": 0.5, "accesibilidad": 0.5})
    # sin demanda ni variación en las otras dos, las tres zonas empatan
    assert out["score"].nunique() == 1


def test_el_puntaje_queda_entre_0_y_1():
    out = score_zones(_features(competencia=[1.0, 5.0, 9.0], tiempo_viaje_prom=[5.0, 15.0, 30.0]))
    assert out["score"].between(0, 1).all()


# ---------------------------------------------------------------------------
# recommend_locations (extremo a extremo)
# ---------------------------------------------------------------------------

def test_recomienda_de_extremo_a_extremo(db):
    db.save_demographics([{"zone_name": z, "population": 1000 * (i + 1)} for i, z in enumerate(LOCATIONS)])
    db.save_pois([_poi(1, "food_drink", "Sliema")])
    out = recommend_locations(db, "quiero abrir una pizzería")

    assert set(out.index) == set(LOCATIONS)
    assert (out["categoria"] == "food_drink").all()
    assert out["score"].is_monotonic_decreasing
    # el desglose completo está presente, no solo el puntaje final
    for col in ("demanda", "competencia", "competencia_cruda", "tiempo_viaje_prom",
                "demanda_norm", "competencia_norm", "accesibilidad_norm", "dimensiones_con_dato"):
        assert col in out.columns


def test_recomendar_con_texto_incomprensible_lanza_error(db):
    with pytest.raises(ValueError):
        recommend_locations(db, "asdfgh qwerty")


def test_recomendar_acepta_pesos_personalizados(db):
    db.save_demographics([{"zone_name": z, "population": 1000 * (i + 1)} for i, z in enumerate(LOCATIONS)])
    solo_demanda = {"demanda": 1.0, "competencia": 0.0, "accesibilidad": 0.0}
    out = recommend_locations(db, "farmacia", weights=solo_demanda)
    # con todo el peso en demanda, gana la zona más poblada (la última guardada)
    assert out.index[0] == list(LOCATIONS)[-1]
