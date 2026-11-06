"""Pruebas del pipeline medallion (Bronze -> Silver -> Gold)."""

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_warehouse.bronze_layer import BronzeLayer
from src.data_warehouse.gold_layer import GoldLayer
from src.data_warehouse.silver_layer import SilverLayer
from src.database import RouteDatabase
from src.run_medallion_pipeline import run as run_pipeline

HOY = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _df(n=6, origin="Msida", destination="Gzira", base=HOY, no_traffic=None):
    ts = [base + timedelta(hours=i) for i in range(n)]
    return pd.DataFrame({
        "timestamp": [t.isoformat() for t in ts],
        "origin": origin, "destination": destination,
        "travel_time_min": [10.0, 12.0, 11.0, 15.0, 9.0, 13.0][:n],
        "no_traffic_time_min": [no_traffic] * n,
        "average_speed_kmh": 30.0,
        "origin_temperature": 20.0, "origin_humidity": 50.0, "origin_weather": "clear",
        "destination_temperature": 20.0, "destination_humidity": 50.0, "destination_weather": "clear",
    })


def _count(db_path, table):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "t.db"


# ---------------------------------------------------------------------------
# Bronze
# ---------------------------------------------------------------------------

def test_bronze_inserta_las_filas_validas(db_path):
    r = BronzeLayer(db_path).ingest(_df())
    assert r["status"] == "success"
    assert r["inserted_records"] == 6
    assert _count(db_path, "bronze_measurements") == 6


def test_bronze_es_idempotente_reingerir_no_duplica(db_path):
    """Regresión: Bronze no tenía restricción UNIQUE y reingerir las mismas
    filas (p. ej. al correr run_medallion_pipeline dos veces) las duplicaba."""
    bronze = BronzeLayer(db_path)
    df = _df()
    assert bronze.ingest(df)["inserted_records"] == 6
    assert bronze.ingest(df)["inserted_records"] == 0
    assert _count(db_path, "bronze_measurements") == 6


def test_bronze_ingiere_solo_lo_nuevo(db_path):
    bronze = BronzeLayer(db_path)
    bronze.ingest(_df(n=3))
    r = bronze.ingest(_df(n=6))  # las 3 primeras ya existen
    assert r["inserted_records"] == 3
    assert _count(db_path, "bronze_measurements") == 6


def test_bronze_rechaza_datos_sin_columnas_requeridas(db_path):
    r = BronzeLayer(db_path).ingest(_df().drop(columns=["travel_time_min"]))
    assert r["error"] == "Missing required columns"


def test_bronze_descarta_duplicados_dentro_del_lote(db_path):
    df = pd.concat([_df(n=3), _df(n=3)], ignore_index=True)
    r = BronzeLayer(db_path).ingest(df)
    assert r["inserted_records"] == 3


def test_bronze_descarta_tiempos_fuera_de_rango_y_nulos(db_path):
    df = _df(n=4)
    df.loc[0, "travel_time_min"] = 9999.0   # fuera de (0, 500)
    df.loc[1, "travel_time_min"] = None     # nulo en columna crítica
    r = BronzeLayer(db_path).ingest(df)
    assert r["inserted_records"] == 2


def test_bronze_guarda_timestamps_iso_con_t(db_path):
    """Regresión: pandas.to_sql guardaba un espacio en vez de 'T' y el
    collector nunca encontraba las filas de Bronze para pasárselas a Silver."""
    BronzeLayer(db_path).ingest(_df(n=1))
    conn = sqlite3.connect(db_path)
    ts = conn.execute("SELECT raw_timestamp FROM bronze_measurements").fetchone()[0]
    conn.close()
    assert "T" in ts and " " not in ts


# ---------------------------------------------------------------------------
# Silver
# ---------------------------------------------------------------------------

def _bronze_df(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql_query("SELECT * FROM bronze_measurements", conn)
    finally:
        conn.close()


def test_silver_transforma_y_agrega_variables_temporales(db_path):
    BronzeLayer(db_path).ingest(_df(no_traffic=8.0))
    r = SilverLayer(db_path).transform_bronze(_bronze_df(db_path))
    assert r["status"] == "success"

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT travel_time_min, traffic_delay_min, congestion_level, hour, is_weekend "
        "FROM silver_measurements ORDER BY timestamp LIMIT 1"
    ).fetchone()
    conn.close()
    assert row[0] == 10.0
    assert row[1] == pytest.approx(2.0)          # 10 - 8
    assert row[2] == "moderate"                   # 1 < retraso <= 4
    assert row[3] == 0                            # la hora de la primera medición


def test_silver_sin_tiempo_sin_trafico_deja_el_retraso_desconocido(db_path):
    """ORS no reporta tiempo sin tráfico: el retraso no se inventa."""
    BronzeLayer(db_path).ingest(_df(no_traffic=None))
    SilverLayer(db_path).transform_bronze(_bronze_df(db_path))
    conn = sqlite3.connect(db_path)
    niveles = {r[0] for r in conn.execute("SELECT congestion_level FROM silver_measurements")}
    conn.close()
    assert niveles == {"unknown"}


def test_silver_no_duplica_al_transformar_dos_veces(db_path):
    BronzeLayer(db_path).ingest(_df())
    silver = SilverLayer(db_path)
    bronze = _bronze_df(db_path)
    silver.transform_bronze(bronze)
    silver.transform_bronze(bronze)
    assert _count(db_path, "silver_measurements") == 6


def test_silver_perfil_de_ruta_calcula_la_desviacion_sin_stddev_de_sql(db_path):
    """Regresión: get_route_profile usaba STDDEV(), que SQLite no trae."""
    BronzeLayer(db_path).ingest(_df(no_traffic=8.0))
    silver = SilverLayer(db_path)
    silver.transform_bronze(_bronze_df(db_path))

    perfil = silver.get_route_profile("Msida", "Gzira", days=365)
    assert perfil["status"] == "success"
    assert len(perfil["profiles"]) == 6
    assert {"hour", "day_of_week", "avg_time", "std_time", "count"} <= set(perfil["profiles"][0])


def test_silver_agregacion_horaria(db_path):
    BronzeLayer(db_path).ingest(_df())
    silver = SilverLayer(db_path)
    silver.transform_bronze(_bronze_df(db_path))
    assert silver.aggregate_hourly()["hourly_records_created"] == 6


# ---------------------------------------------------------------------------
# Gold
# ---------------------------------------------------------------------------

def _poblar_hasta_silver(db_path, **kwargs):
    BronzeLayer(db_path).ingest(_df(**kwargs))
    SilverLayer(db_path).transform_bronze(_bronze_df(db_path))


def test_gold_calcula_kpis_por_ruta(db_path):
    _poblar_hasta_silver(db_path, no_traffic=8.0)
    gold = GoldLayer(db_path)
    r = gold.calculate_kpis(date=HOY.date().isoformat())
    assert r["status"] == "success" and r["kpis_calculated"] == 1

    conn = sqlite3.connect(db_path)
    avg, n, rel = conn.execute(
        "SELECT avg_travel_time, sample_count, reliability_score FROM gold_route_kpis"
    ).fetchone()
    conn.close()
    assert avg == pytest.approx(sum([10, 12, 11, 15, 9, 13]) / 6)
    assert n == 6
    assert 0 <= rel <= 100


def test_gold_recalcular_el_mismo_dia_no_falla_ni_duplica(db_path):
    """Regresión: el INSERT plano chocaba con UNIQUE(date, origin, destination)
    la segunda vez que se calculaban las KPIs de un mismo día."""
    _poblar_hasta_silver(db_path, no_traffic=8.0)
    gold = GoldLayer(db_path)
    fecha = HOY.date().isoformat()
    assert gold.calculate_kpis(date=fecha)["status"] == "success"
    assert gold.calculate_kpis(date=fecha)["status"] == "success"
    assert gold.calculate_rankings(date=fecha)["status"] == "success"
    assert gold.calculate_rankings(date=fecha)["status"] == "success"
    assert _count(db_path, "gold_route_kpis") == 1
    assert _count(db_path, "gold_route_rankings") == 1


def test_gold_dia_sin_datos(db_path):
    _poblar_hasta_silver(db_path)
    assert GoldLayer(db_path).calculate_kpis(date="2000-01-01")["status"] == "no_data"


def test_gold_ranking_ordena_por_fiabilidad(db_path):
    BronzeLayer(db_path).ingest(_df(origin="Msida", destination="Gzira"))
    estable = _df(origin="Msida", destination="Sliema", base=HOY)
    estable["travel_time_min"] = 10.0                       # sin variación -> fiabilidad 100
    BronzeLayer(db_path).ingest(estable)
    SilverLayer(db_path).transform_bronze(_bronze_df(db_path))

    gold = GoldLayer(db_path)
    fecha = HOY.date().isoformat()
    gold.calculate_kpis(date=fecha)
    ranking = gold.calculate_rankings(date=fecha)["rankings"]
    assert ranking[0]["destination"] == "Sliema" and ranking[0]["rank"] == 1


def test_gold_metricas_de_periodo(db_path):
    _poblar_hasta_silver(db_path, no_traffic=8.0)
    gold = GoldLayer(db_path)
    gold.calculate_kpis(date=HOY.date().isoformat())

    manana = (HOY + timedelta(days=1)).date().isoformat()
    con_datos = gold.get_period_metrics(HOY.date().isoformat(), manana)
    assert con_datos["rows"] == 1 and con_datos["avg_travel_time"] is not None

    vacio = gold.get_period_metrics("2000-01-01", "2000-02-01")
    assert vacio == {"avg_travel_time": None, "reliability": None, "rows": 0}


def test_gold_resumen_ejecutivo_en_base_vacia_devuelve_ceros_no_error(db_path):
    """Regresión: AVG()/SUM() sin filas dan NULL y float(NaN) reventaba, así
    que en un clon limpio (sin histórico) Executive mostraba "Error loading
    summary data"."""
    resumen = GoldLayer(db_path).get_executive_summary(days=30)
    assert "error" not in resumen
    assert resumen["system_avg_travel_time"] == 0
    assert resumen["total_routes"] == 0
    assert resumen["total_measurements"] == 0
    assert resumen["best_routes"] == [] and resumen["worst_routes"] == []


def test_gold_resumen_ejecutivo_con_datos(db_path):
    _poblar_hasta_silver(db_path, no_traffic=8.0)
    gold = GoldLayer(db_path)
    gold.calculate_kpis(date=HOY.date().isoformat())
    resumen = gold.get_executive_summary(days=30)
    assert resumen["total_routes"] == 1
    assert resumen["total_measurements"] == 6
    assert resumen["system_avg_travel_time"] > 0


# ---------------------------------------------------------------------------
# Pipeline completo
# ---------------------------------------------------------------------------

def test_pipeline_completo_es_idempotente(tmp_path):
    db_path = tmp_path / "t.db"
    db = RouteDatabase(tmp_path / "t.csv", db_path)
    db.save_records_to_sqlite([
        {"timestamp": (HOY + timedelta(hours=i)).isoformat(), "origin": "Msida", "destination": "Gzira",
         "data_source": "tomtom", "travel_time_min": 10.0 + i, "no_traffic_time_min": 8.0,
         "average_speed_kmh": 30.0}
        for i in range(5)
    ])

    run_pipeline(db_path)
    cuentas = {t: _count(db_path, t) for t in
               ("bronze_measurements", "silver_measurements", "gold_route_kpis")}
    assert cuentas["bronze_measurements"] == 5
    assert cuentas["silver_measurements"] == 5
    assert cuentas["gold_route_kpis"] >= 1

    run_pipeline(db_path)  # segunda vez: nada se duplica
    assert {t: _count(db_path, t) for t in cuentas} == cuentas
