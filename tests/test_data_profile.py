"""Pruebas del perfil de calidad de la base en UNA pasada (RouteDatabase.get_data_profile).

Regresión: Analyst hacía más de diez consultas al abrirse (rutas únicas ×4, una consulta por ruta
para la completitud, un resumen completo, 100 mil filas cargadas...). Cada recorrido de la tabla
cuesta ~8 s en el bind mount de Windows de Docker (décimas de segundo en el host), así que sumaban
~87 s. Un único perfil agregado da todo eso en un recorrido.
"""

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import RouteDatabase

AHORA = datetime.now(timezone.utc)


def _fila(minutos_atras, origin, destination, fuente="tomtom", **extra):
    base = {
        "timestamp": (AHORA - timedelta(minutes=minutos_atras)).isoformat(),
        "origin": origin,
        "destination": destination,
        "data_source": fuente,
        "travel_time_min": 10.0,
        "distance_km": 3.0,
        "average_speed_kmh": 30.0,
        "traffic_delay_min": 1.0,
        "origin_temperature": 20.0,
        "origin_humidity": 50.0,
    }
    base.update(extra)
    return base


@pytest.fixture
def db(tmp_path):
    return RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")


@pytest.fixture
def db_con_datos(db):
    db.save_records_to_sqlite(
        [_fila(i, "Msida", "Gzira") for i in range(10)]
        + [_fila(i, "Msida", "Sliema", fuente="ors", traffic_delay_min=None, origin_temperature=None) for i in range(6)]
        + [_fila(5, "Valletta", "Sliema")]
    )
    return db


# ---------------------------------------------------------------------------
# Los números
# ---------------------------------------------------------------------------


def test_totales_y_rutas(db_con_datos):
    """El perfil da el total de filas, de rutas y de orígenes, y las filas de cada ruta."""
    p = db_con_datos.get_data_profile()
    assert p["total_rows"] == 17
    assert p["n_routes"] == 3
    assert p["n_origins"] == 2
    assert dict(zip(zip(p["routes"]["origin"], p["routes"]["destination"]), p["routes"]["rows"])) == {
        ("Msida", "Gzira"): 10,
        ("Msida", "Sliema"): 6,
        ("Valletta", "Sliema"): 1,
    }


def test_fechas_primera_y_ultima(db_con_datos):
    """El primer y el último timestamp del perfil son el mínimo y el máximo de las mediciones."""
    p = db_con_datos.get_data_profile()
    assert p["first_timestamp"] == min(db_con_datos.query_measurements(limit=100)["timestamp"])
    assert p["last_timestamp"] == max(db_con_datos.query_measurements(limit=100)["timestamp"])


def test_los_nulos_coinciden_con_un_calculo_independiente_en_pandas(db_con_datos):
    """Los nulos por columna, por ruta y el porcentaje de faltantes coinciden con un cálculo independiente en pandas."""
    p = db_con_datos.get_data_profile()
    cols = p["measurement_columns"]
    df = db_con_datos.query_measurements(limit=100)[cols]
    assert p["null_counts"] == {c: int(df[c].isna().sum()) for c in cols}
    assert int(p["routes"]["nulls"].sum()) == int(df.isna().sum().sum())
    assert p["missing_pct"] == round(100 * df.isna().sum().sum() / (len(df) * len(cols)), 1)


def test_completitud_por_ruta(db_con_datos):
    """La completitud por ruta está entre 0 y 100, y la ruta de ORS, con más columnas vacías, es menos completa que las de TomTom."""
    r = db_con_datos.get_data_profile()["routes"].set_index(["origin", "destination"])
    # la ruta de ORS tiene 2 columnas más vacías en cada fila: es menos completa que las de TomTom
    assert r.loc[("Msida", "Sliema"), "completeness_pct"] < r.loc[("Msida", "Gzira"), "completeness_pct"]
    assert r["completeness_pct"].between(0, 100).all()


def test_id_polyline_y_created_at_no_son_columnas_de_medicion(db_con_datos):
    """`id`, `polyline` y `created_at` no cuentan como columnas de medición."""
    cols = db_con_datos.get_data_profile()["measurement_columns"]
    for no_medida in ("id", "polyline", "created_at"):
        assert no_medida not in cols
    assert "travel_time_min" in cols and "origin_temperature" in cols


def test_una_polilinea_nula_no_cuenta_como_dato_faltante(db):
    """Las filas históricas de TomTom no tienen polyline: eso no debe bajar la completitud."""
    db.save_records_to_sqlite([_fila(i, "Msida", "Gzira") for i in range(5)])  # sin polyline (NULL)
    p = db.get_data_profile()
    assert "polyline" not in p["null_counts"]
    nulos_reales = sum(p["null_counts"].values())
    assert p["routes"].iloc[0]["nulls"] == nulos_reales


def test_base_vacia(db):
    """Con una base vacía el perfil devuelve ceros, fechas `None` y una tabla de rutas vacía pero con sus columnas."""
    p = db.get_data_profile()
    assert p["total_rows"] == 0 and p["n_routes"] == 0 and p["n_origins"] == 0
    assert p["first_timestamp"] is None and p["last_timestamp"] is None
    assert p["missing_pct"] == 0.0 and p["duplicates"] == 0
    assert p["routes"].empty and list(p["routes"].columns)[:3] == ["origin", "destination", "rows"]


def test_cuenta_duplicados_de_ruta_instante_y_fuente(tmp_path):
    """La clave UNIQUE de la tabla real los impide; se prueba con una tabla SIN la restricción."""
    ruta = tmp_path / "sin_unique.db"
    conn = sqlite3.connect(ruta)
    conn.execute(
        "CREATE TABLE route_measurements (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, "
        "origin TEXT NOT NULL, destination TEXT NOT NULL, data_source TEXT NOT NULL, travel_time_min REAL, "
        "polyline TEXT, created_at TEXT)"
    )
    filas = [("2026-11-01T00:00:00", "A", "B", "ors", 5.0, None, "x")] * 3 + [
        ("2026-11-01T00:15:00", "A", "B", "ors", 6.0, None, "x")
    ]
    conn.executemany(
        "INSERT INTO route_measurements (timestamp, origin, destination, data_source, travel_time_min, polyline, created_at) VALUES (?,?,?,?,?,?,?)",
        filas,
    )
    conn.commit()
    conn.close()
    base = RouteDatabase(tmp_path / "t.csv", ruta)
    p = base.get_data_profile()
    assert p["total_rows"] == 4 and p["duplicates"] == 2  # 3 filas iguales = 2 repetidas


def test_en_la_tabla_real_no_hay_duplicados(db_con_datos):
    """El perfil no encuentra duplicados en la tabla de datos de prueba."""
    assert db_con_datos.get_data_profile()["duplicates"] == 0


# ---------------------------------------------------------------------------
# UNA sola pasada por la tabla (el motivo de existir)
# ---------------------------------------------------------------------------


def test_el_perfil_hace_una_sola_consulta_sobre_la_tabla(db_con_datos, monkeypatch):
    """El perfil recorre la tabla de mediciones con una sola consulta."""
    consultas = []
    original = RouteDatabase._connect

    def conectar(self):
        conn = original(self)
        conn.set_trace_callback(lambda sql: consultas.append(sql))
        return conn

    monkeypatch.setattr(RouteDatabase, "_connect", conectar)
    db_con_datos.get_data_profile()
    sobre_la_tabla = [
        q for q in consultas if "FROM route_measurements" in q and q.lstrip().upper().startswith("SELECT")
    ]
    assert (
        len(sobre_la_tabla) == 1
    ), f"se esperaba 1 recorrido de la tabla y hubo {len(sobre_la_tabla)}: {sobre_la_tabla}"


# ---------------------------------------------------------------------------
# Lo barato: último timestamp y resumen sin rutas
# ---------------------------------------------------------------------------


def test_ultimo_timestamp(db_con_datos):
    """`get_last_timestamp` devuelve el máximo de los timestamps."""
    esperado = max(db_con_datos.query_measurements(limit=100)["timestamp"])
    assert db_con_datos.get_last_timestamp() == esperado


def test_ultimo_timestamp_de_base_vacia(db):
    """`get_last_timestamp` devuelve `None` con una base vacía."""
    assert db.get_last_timestamp() is None


def test_resumen_sin_rutas_omite_solo_las_rutas_unicas(db_con_datos):
    """`get_database_summary(include_routes=False)` omite solo las rutas únicas y el resto del resumen es igual."""
    completo = db_con_datos.get_database_summary()
    rapido = db_con_datos.get_database_summary(include_routes=False)
    assert completo["unique_routes"] == 3
    assert rapido["unique_routes"] is None
    for k in ("total_records", "unique_origins", "first_timestamp", "last_timestamp"):
        assert rapido[k] == completo[k]


def test_el_resumen_por_defecto_sigue_igual(db_con_datos):
    """Compatibilidad: quien lo llame sin argumentos sigue obteniendo unique_routes."""
    assert db_con_datos.get_database_summary()["unique_routes"] == 3


def test_ultimo_timestamp_no_recorre_la_tabla(db_con_datos, monkeypatch):
    """MAX(timestamp) se resuelve con el índice: una sola consulta, sin DISTINCT."""
    consultas = []
    original = RouteDatabase._connect

    def conectar(self):
        conn = original(self)
        conn.set_trace_callback(lambda sql: consultas.append(sql))
        return conn

    monkeypatch.setattr(RouteDatabase, "_connect", conectar)
    db_con_datos.get_last_timestamp()
    sobre_la_tabla = [q for q in consultas if "FROM route_measurements" in q]
    assert len(sobre_la_tabla) == 1 and "DISTINCT" not in sobre_la_tabla[0].upper()
