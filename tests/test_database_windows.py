"""Pruebas de las consultas de ventana completa de RouteDatabase.

Regresión: los dashboards traían `query_measurements(limit=10000)` —las
10.000 filas MÁS RECIENTES— para gráficos de "30 días" y "7 días", así que
con mucha recolección mostraban solo los últimos días sin avisar.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import RouteDatabase

AHORA = datetime.now(timezone.utc).replace(minute=30, second=0, microsecond=0)


def _registro(ts, origin="Msida", destination="Gzira", minutos=10.0, source="ors"):
    return {
        "timestamp": ts.isoformat(), "origin": origin, "destination": destination,
        "data_source": source, "travel_time_min": minutos, "distance_km": 2.0,
        "average_speed_kmh": 30.0, "origin_temperature": 20.0,
    }


@pytest.fixture
def db(tmp_path):
    return RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")


@pytest.fixture
def db_grande(db):
    """12.000 mediciones repartidas en 30 días (400/día, ~16 por hora): más
    que el limit=10000 que usaban los dashboards."""
    registros = []
    for dia in range(30):
        for i in range(400):
            ts = AHORA - timedelta(days=dia, seconds=i * 60)   # i*60s: dentro de las mismas ~7 h
            origen, destino = ("Msida", "Gzira") if i % 2 == 0 else ("Msida", "Sliema")
            registros.append(_registro(ts, origen, destino, minutos=10.0 + (dia % 5), source="ors"))
    db.save_records_to_sqlite(registros)
    return db


def test_el_limit_antiguo_si_recortaba_la_ventana(db_grande):
    """Documenta el bug: con limit=10000 solo se llega a ~25 de los 30 días."""
    df = db_grande.query_measurements(limit=10000)
    dias_cubiertos = df["timestamp"].str[:10].nunique()
    assert dias_cubiertos < 28


def test_promedio_diario_cubre_toda_la_ventana(db_grande):
    daily = db_grande.get_daily_average(days=31)
    assert len(daily) >= 30
    assert daily["measurements"].sum() == 12_000      # ninguna fila se pierde
    assert list(daily.columns) == ["date", "avg_travel_time", "measurements"]
    assert daily["date"].is_monotonic_increasing


def test_promedio_diario_respeta_la_ventana(db_grande):
    corto = db_grande.get_daily_average(days=3)
    assert 0 < len(corto) <= 5   # 3 días de ventana + el tramo parcial de cada borde
    assert corto["measurements"].sum() < 12_000


def test_promedio_diario_calcula_bien_el_promedio(db):
    hoy = AHORA
    db.save_records_to_sqlite([
        _registro(hoy, minutos=10.0),
        _registro(hoy - timedelta(minutes=1), minutos=20.0),
    ])
    daily = db.get_daily_average(days=2)
    assert daily["avg_travel_time"].iloc[-1] == pytest.approx(15.0)


def test_promedio_diario_base_vacia(db):
    assert db.get_daily_average(days=30).empty


def test_promedio_por_ruta_y_hora(db):
    base = AHORA.replace(hour=10, minute=0)
    db.save_records_to_sqlite([
        _registro(base, "Msida", "Gzira", 10.0),
        _registro(base + timedelta(minutes=5), "Msida", "Gzira", 20.0),
        _registro(base + timedelta(hours=1), "Msida", "Gzira", 40.0),
        _registro(base, "Msida", "Sliema", 7.0),
    ])
    df = db.get_route_hour_average(days=2).set_index(["origin", "destination", "hour"])
    assert df.loc[("Msida", "Gzira", 10), "avg_travel_time"] == pytest.approx(15.0)
    assert df.loc[("Msida", "Gzira", 10), "measurements"] == 2
    assert df.loc[("Msida", "Gzira", 11), "avg_travel_time"] == pytest.approx(40.0)
    assert df.loc[("Msida", "Sliema", 10), "avg_travel_time"] == pytest.approx(7.0)


def test_promedio_por_ruta_y_hora_no_pierde_filas_con_mucha_data(db_grande):
    df = db_grande.get_route_hour_average(days=31)
    assert df["measurements"].sum() == 12_000
    assert df["hour"].between(0, 23).all()


def test_columnas_numericas_excluyen_el_id_y_el_texto(db):
    cols = db.get_numeric_columns()
    assert "travel_time_min" in cols and "origin_temperature" in cols
    assert "id" not in cols
    assert "origin" not in cols and "polyline" not in cols


def test_query_columns_trae_solo_lo_pedido_sin_limit(db_grande):
    df = db_grande.query_columns(["travel_time_min", "origin_temperature"], days=31)
    assert list(df.columns) == ["travel_time_min", "origin_temperature"]
    assert len(df) == 12_000


def test_query_columns_rechaza_columnas_que_no_existen(db):
    with pytest.raises(ValueError):
        db.query_columns(["travel_time_min", "no_existe"], days=1)


def test_query_columns_no_permite_inyeccion_sql(db_grande):
    with pytest.raises(ValueError):
        db_grande.query_columns(["travel_time_min FROM route_measurements; DROP TABLE route_measurements; --"], days=1)
    assert len(db_grande.query_columns(["travel_time_min"], days=31)) == 12_000   # la tabla sigue ahí


def test_query_columns_sin_columnas(db):
    assert db.query_columns([], days=1).empty
