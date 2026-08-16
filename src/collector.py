"""Orquestador principal de recolección de datos de tráfico y clima.

BD_BI_TFM2: fusiona el `collector.py` de urban-mobility-analytics1 (TomTom,
SQLite) con el flujo de BD_BI_TFM (ORS, TimescaleDB). La fuente de tráfico
es intercambiable vía `DATA_SOURCE` (ver src/config.py); ambas escriben al
mismo esquema unificado en CSV/SQLite (capa local y de analítica/ML) y,
adicionalmente, a TimescaleDB (capa de producción para el dashboard BI).
"""

import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd

from src.data_warehouse.bronze_layer import BronzeLayer
from src.data_warehouse.gold_layer import GoldLayer
from src.data_warehouse.silver_layer import SilverLayer
from src.database import RouteDatabase
from src.locations import ROUTES, get_all_unique_locations
from src.ors_client import ORSClient
from src.tomtom_client import TomTomClient
from src.weather_client import WeatherClient

logger = logging.getLogger(__name__)

# Umbral (en minutos) a partir del cual una ruta se considera de alta demora.
# Se mantiene el mismo criterio que usaba BD_BI_TFM originalmente.
HIGH_DELAY_THRESHOLD_MIN = 20

# Columnas de un registro del collector que necesita BronzeLayer.ingest().
_BRONZE_INPUT_COLUMNS = [
    "timestamp", "origin", "destination", "travel_time_min", "no_traffic_time_min",
    "average_speed_kmh", "origin_temperature", "origin_humidity", "origin_weather",
    "destination_temperature", "destination_humidity", "destination_weather",
]


class DataCollector:
    """Recolector de datos de tráfico y clima para rutas en Malta."""

    def __init__(
        self,
        data_source: str,
        traffic_api_key: str,
        weather_key: str,
        csv_path: Path,
        db_path: Path,
        timescale_config: Optional[dict] = None,
        enable_timescale: bool = True,
        enable_medallion: bool = True,
    ):
        if data_source not in ("ors", "tomtom"):
            raise ValueError(f"data_source debe ser 'ors' o 'tomtom', recibido: {data_source}")

        self.data_source = data_source
        self.traffic_client = (
            TomTomClient(traffic_api_key)
            if data_source == "tomtom"
            else ORSClient(traffic_api_key)
        )
        self.weather = WeatherClient(weather_key)
        self.db = RouteDatabase(csv_path, db_path)
        self.db_path = db_path
        self.timescale_config = timescale_config
        self.enable_timescale = enable_timescale and timescale_config is not None
        self.enable_medallion = enable_medallion
        self.running = True

        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Maneja Ctrl+C para detener gracefully."""
        logger.info("Stopping collector...")
        self.running = False
        self.traffic_client.close()
        self.weather.close()
        sys.exit(0)

    def collect_cycle(self) -> int:
        """
        Ejecuta un ciclo completo de recolección.

        Retorna el número de registros guardados exitosamente.
        """
        logger.info(f"Starting collection cycle (source={self.data_source})")

        timestamp_utc = datetime.now(timezone.utc).isoformat()
        records: List[dict] = []

        unique_locations = get_all_unique_locations()
        weather_data = {}

        for location_name, location in unique_locations.items():
            try:
                weather_data[location_name] = self.weather.get_current_weather(
                    location.latitude,
                    location.longitude,
                )
            except Exception as e:
                logger.warning(
                    f"Weather fetch failed for {location_name}: {e}. "
                    f"Will continue with other routes."
                )

        for origin_name, destination_name in ROUTES:
            try:
                origin = unique_locations[origin_name]
                destination = unique_locations[destination_name]

                if self.data_source == "tomtom":
                    route_data = self.traffic_client.calculate_route(
                        origin.latitude, origin.longitude,
                        destination.latitude, destination.longitude,
                    )
                else:
                    route_data = self.traffic_client.calculate_route(
                        origin.latitude, origin.longitude,
                        destination.latitude, destination.longitude,
                    )

                travel_time_min = route_data["travel_time_min"]
                mobility_level = (
                    "Alta demora" if travel_time_min > HIGH_DELAY_THRESHOLD_MIN
                    else "Movilidad normal"
                )

                record = {
                    "timestamp": timestamp_utc,
                    "origin": origin_name,
                    "destination": destination_name,
                    "data_source": self.data_source,
                    "mobility_level": mobility_level,
                    **route_data,
                }

                origin_weather = weather_data.get(origin_name, {})
                destination_weather = weather_data.get(destination_name, {})

                record["origin_temperature"] = origin_weather.get("temperature")
                record["origin_feels_like"] = origin_weather.get("feels_like")
                record["origin_humidity"] = origin_weather.get("humidity")
                record["origin_weather"] = origin_weather.get("weather")

                record["destination_temperature"] = destination_weather.get("temperature")
                record["destination_feels_like"] = destination_weather.get("feels_like")
                record["destination_humidity"] = destination_weather.get("humidity")
                record["destination_weather"] = destination_weather.get("weather")

                records.append(record)

                delay = route_data.get("traffic_delay_min")
                delay_str = f" (+{delay:.1f}min delay)" if delay is not None else ""
                logger.info(
                    f"[{self.data_source}] {origin_name}→{destination_name}: "
                    f"{travel_time_min:.1f}min{delay_str}"
                )

            except Exception as e:
                logger.error(
                    f"Failed to collect {origin_name} → {destination_name}: {e}"
                )
                continue

        if not records:
            logger.error("No records were collected successfully")
            return 0

        try:
            self.db.save_records_to_csv(records)
            self.db.save_records_to_sqlite(records)

            if self.enable_timescale:
                self.db.save_records_to_timescale(records, self.timescale_config)

            if self.enable_medallion:
                self._run_incremental_medallion(records, timestamp_utc)

            self._write_heartbeat()

            logger.info(f"Successfully saved {len(records)} records")
            return len(records)
        except Exception as e:
            logger.error(f"Failed to save records: {e}")
            return 0

    def _write_heartbeat(self) -> None:
        """
        Escribe logs/heartbeat con la hora del último ciclo exitoso.

        Usado por el HEALTHCHECK de docker-compose.yml: el collector no
        expone ningún puerto HTTP (a diferencia de dashboard/timescaledb),
        así que Docker no tiene otra forma nativa de saber si el proceso
        sigue vivo y funcionando de verdad (no solo "el proceso no ha
        crasheado", sino "de verdad completó un ciclo hace poco").
        """
        try:
            root_dir = Path(__file__).resolve().parents[1]
            heartbeat_path = root_dir / "logs" / "heartbeat"
            heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            heartbeat_path.write_text(datetime.now(timezone.utc).isoformat())
        except Exception as e:
            logger.warning(f"No se pudo escribir el heartbeat (no crítico): {e}")

    def _run_incremental_medallion(self, records: List[dict], timestamp_utc: str) -> None:
        """
        Alimenta Bronze → Silver → Gold con SOLO los registros de este
        ciclo (no toda la tabla histórica), para que el dashboard
        Executive (`gold_route_kpis`) se mantenga al día automáticamente.

        Se ejecuta sobre este ciclo únicamente, y no sobre todo el
        histórico, por dos motivos:
          1. Rendimiento: con el collector corriendo cada 1-2 minutos,
             reprocesar miles de filas históricas en cada ciclo no
             escalaría.
          2. Correctud: `bronze_measurements` no tiene restricción UNIQUE
             (es un log de ingesta), así que volver a insertar filas ya
             vistas las duplicaría sin parar.

        Cualquier error aquí se registra pero NUNCA interrumpe el guardado
        de CSV/SQLite/TimescaleDB, que ya se completó antes de llegar a
        este punto: Executive es una vista adicional, no el flujo crítico.
        """
        try:
            cycle_df = pd.DataFrame(records)
            for col in _BRONZE_INPUT_COLUMNS:
                if col not in cycle_df.columns:
                    cycle_df[col] = None

            bronze = BronzeLayer(self.db_path)
            bronze_result = bronze.ingest(cycle_df[_BRONZE_INPUT_COLUMNS])

            if bronze_result.get("status") != "success":
                logger.warning(f"Medallion (bronze) omitido este ciclo: {bronze_result}")
                return

            import sqlite3
            conn = sqlite3.connect(self.db_path)
            bronze_cycle_df = pd.read_sql_query(
                "SELECT * FROM bronze_measurements WHERE raw_timestamp = ?",
                conn, params=(timestamp_utc,),
            )
            conn.close()

            silver = SilverLayer(self.db_path)
            silver_result = silver.transform_bronze(bronze_cycle_df)
            if "error" in silver_result:
                logger.warning(f"Medallion (silver) falló este ciclo: {silver_result}")
                return

            today = timestamp_utc[:10]  # YYYY-MM-DD
            gold = GoldLayer(self.db_path)
            kpi_result = gold.calculate_kpis(date=today)
            gold.calculate_rankings(date=today)

            logger.info(
                f"Medallion pipeline OK: bronze +{bronze_result.get('inserted_records', 0)}, "
                f"silver +{silver_result.get('records_transformed', 0)}, "
                f"gold[{today}]={kpi_result.get('status')}"
            )
        except Exception as e:
            logger.warning(f"Medallion pipeline falló este ciclo (no crítico): {e}")

    def run_once(self) -> None:
        """Ejecuta un solo ciclo de recolección."""
        self.collect_cycle()

    def run_continuous(self, interval_seconds: int) -> None:
        """
        Ejecuta recolecciones continuas cada N segundos.

        Detiene correctamente con Ctrl+C.
        """
        logger.info(f"Starting continuous collection (interval: {interval_seconds}s)")

        while self.running:
            self.collect_cycle()

            if not self.running:
                break

            logger.info(f"Next collection in {interval_seconds} seconds...")
            for _ in range(interval_seconds):
                if not self.running:
                    break
                time.sleep(1)

        logger.info("Collector stopped")
