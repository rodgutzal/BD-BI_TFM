"""
Backfill del histórico CSV hacia TimescaleDB (capa de producción).

Uso (con el stack Docker levantado, `docker compose up -d`):

    python -m src.timescale_migration

Lee data/raw/route_weather_data.csv (esquema unificado BD_BI_TFM2) y lo
inserta en la tabla `traffic_trips`. Es idempotente a nivel de intento
(usa INSERT simple; si se corre dos veces se duplicarán filas, ya que
`traffic_trips` no tiene una restricción UNIQUE — está pensada para
recibir mediciones periódicas del collector, no para reintentos de carga
masiva. Si necesitas re-ejecutar el backfill, trunca la tabla primero).
"""

import logging
import sys
from pathlib import Path

import pandas as pd

from src import config

logger = logging.getLogger(__name__)


def backfill(csv_path: Path) -> int:
    """Inserta el CSV histórico en traffic_trips. Retorna filas insertadas."""
    try:
        import psycopg2
    except ImportError:
        logger.error(
            "psycopg2-binary no está instalado. "
            "Instálalo con `pip install psycopg2-binary`."
        )
        return 0

    if not csv_path.exists():
        logger.error(f"CSV no encontrado: {csv_path}")
        return 0

    df = pd.read_csv(csv_path, on_bad_lines="skip", engine="python")
    if df.empty:
        logger.warning("CSV vacío, nada que migrar")
        return 0

    timescale_config = config.get_timescale_config()

    insert_sql = """
        INSERT INTO traffic_trips (
            datetime, origin, destination, distance_km, duration_min,
            temperature, humidity, weather_description, mobility_level,
            data_source, traffic_delay_min
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    rows = []
    for _, row in df.iterrows():
        rows.append((
            row.get("timestamp"),
            row.get("origin"),
            row.get("destination"),
            row.get("distance_km"),
            row.get("travel_time_min"),
            row.get("origin_temperature"),
            row.get("origin_humidity"),
            row.get("origin_weather"),
            row.get("mobility_level"),
            row.get("data_source", "unknown"),
            row.get("traffic_delay_min"),
        ))

    conn = None
    try:
        conn = psycopg2.connect(**timescale_config)
        cursor = conn.cursor()
        cursor.executemany(insert_sql, rows)
        conn.commit()
        cursor.close()
        logger.info(f"Backfill completo: {len(rows)} filas insertadas en traffic_trips")
        return len(rows)
    except Exception as e:
        logger.error(f"Error en backfill hacia TimescaleDB: {e}")
        if conn:
            conn.rollback()
        return 0
    finally:
        if conn:
            conn.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    root_dir = Path(__file__).resolve().parents[1]
    csv_path = root_dir / "data" / "raw" / "route_weather_data.csv"
    count = backfill(csv_path)
    return 0 if count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
