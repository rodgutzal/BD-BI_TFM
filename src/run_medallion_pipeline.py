"""
Ejecuta el pipeline medallion completo (Bronze → Silver → Gold) sobre los
datos ya recolectados en `route_measurements`, dejando pobladas las tablas
`gold_route_kpis` / `gold_route_rankings` que consume el dashboard
Executive (`streamlit_app/dashboards/executive_dashboard.py`).

Uso:
    python -m src.run_medallion_pipeline

Es seguro volver a ejecutarlo: Bronze usa INSERT normal (puede duplicar si
corres sobre las mismas filas dos veces — pensado para correr sobre datos
nuevos), Silver usa INSERT OR IGNORE (respeta UNIQUE(timestamp, origin,
destination), no duplica), y Gold usa UNIQUE(date, origin, destination) /
UNIQUE(date, hour) — si repites una fecha ya calculada, fallará esa fila
puntual con un error de integridad que el script atrapa y reporta sin
detener el resto del proceso.

Ver INTEGRATION_NOTES.md para el detalle de los bugs originales que este
pipeline corrige (bronze_layer.py, silver_layer.py, gold_layer.py).
"""

import logging
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.data_warehouse.bronze_layer import BronzeLayer  # noqa: E402
from src.data_warehouse.silver_layer import SilverLayer  # noqa: E402
from src.data_warehouse.gold_layer import GoldLayer  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = ROOT_DIR / "data" / "mobility.db"

# Columnas de route_measurements que Bronze espera (el resto se descarta).
BRONZE_INPUT_COLUMNS = [
    "timestamp", "origin", "destination", "travel_time_min", "no_traffic_time_min",
    "average_speed_kmh", "origin_temperature", "origin_humidity", "origin_weather",
    "destination_temperature", "destination_humidity", "destination_weather",
]


def run(db_path: Path = DB_PATH) -> dict:
    import sqlite3

    summary = {"bronze": None, "silver": None, "gold_dates": []}

    # --- Bronze: extract + validate ---
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(f"SELECT {', '.join(BRONZE_INPUT_COLUMNS)} FROM route_measurements", conn)
    conn.close()

    if df.empty:
        logger.warning("route_measurements está vacía, nada que procesar.")
        return summary

    logger.info(f"Leídos {len(df)} registros de route_measurements")

    bronze = BronzeLayer(db_path)
    bronze_result = bronze.ingest(df)
    summary["bronze"] = bronze_result
    logger.info(f"Bronze: {bronze_result}")

    if bronze_result.get("status") != "success":
        logger.error("Bronze falló, abortando pipeline.")
        return summary

    # --- Silver: transform + enrich ---
    conn = sqlite3.connect(db_path)
    bronze_df = pd.read_sql_query("SELECT * FROM bronze_measurements", conn)
    conn.close()

    silver = SilverLayer(db_path)
    silver_result = silver.transform_bronze(bronze_df)
    summary["silver"] = silver_result
    logger.info(f"Silver: {silver_result}")

    hourly_result = silver.aggregate_hourly()
    logger.info(f"Silver (hourly aggregate): {hourly_result}")

    # --- Gold: KPIs por cada fecha presente en los datos ---
    conn = sqlite3.connect(db_path)
    dates_df = pd.read_sql_query("SELECT DISTINCT DATE(timestamp) as d FROM silver_measurements", conn)
    conn.close()

    gold = GoldLayer(db_path)
    for date in sorted(dates_df["d"].dropna().tolist()):
        try:
            kpi_result = gold.calculate_kpis(date=date)
            rank_result = gold.calculate_rankings(date=date)
            summary["gold_dates"].append({"date": date, "kpis": kpi_result, "rankings": rank_result})
            logger.info(f"Gold [{date}]: {kpi_result.get('status')} "
                        f"({kpi_result.get('kpis_calculated', 0)} rutas)")
        except Exception as e:
            logger.warning(f"Gold [{date}] falló (probablemente ya estaba calculada): {e}")

    logger.info("Pipeline medallion completo.")
    return summary


if __name__ == "__main__":
    result = run()
    total_kpi_dates = sum(
        1 for d in result["gold_dates"] if d["kpis"].get("status") == "success"
    )
    print(f"\n✓ Fechas con KPIs calculadas: {total_kpi_dates}/{len(result['gold_dates'])}")
    sys.exit(0)
