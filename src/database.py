"""Gestión de almacenamiento: CSV (histórico crudo), SQLite (capa local/analítica
con detalle completo) y TimescaleDB (capa de producción, resumen normalizado).

NOTA DE INTEGRACIÓN (BD_BI_TFM2)
---------------------------------
El `RouteDatabase` original de urban-mobility-analytics1 guardaba en SQLite
las columnas genéricas `temperature`, `feels_like`, `humidity`, `weather`,
pero el `collector.py` de ese mismo repo generaba los registros con las
claves `origin_temperature`, `destination_temperature`, etc. Como
`save_records_to_sqlite` sólo leía las claves genéricas (que nunca existían
en el registro), las ~2.664 filas históricas quedaron con el clima en NULL
en `mobility.db` (aunque sí estaba completo en el CSV). Este archivo corrige
ese bug: el esquema y el insert ahora usan explícitamente `origin_*` y
`destination_*`, que es también lo que espera el dashboard avanzado
(`streamlit_app/app_advanced.py`) y el modelo de predicción
(`src/models/travel_time_model.py`).
"""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class RouteDatabase:
    """Gestor de base de datos local (CSV + SQLite) para mediciones de rutas."""

    def __init__(self, csv_path: Path, db_path: Path):
        self.csv_path = csv_path
        self.db_path = db_path
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # CSV (histórico crudo, esquema completo)
    # ------------------------------------------------------------------

    def save_records_to_csv(self, records: List[dict]) -> None:
        """Añade registros al CSV sin sobrescribir los anteriores."""
        if not records:
            return

        dataframe = pd.DataFrame(records)
        file_exists = self.csv_path.exists() and self.csv_path.stat().st_size > 0

        dataframe.to_csv(
            self.csv_path,
            mode="a",
            header=not file_exists,
            index=False,
        )
        logger.info(f"Saved {len(records)} records to CSV")

    # ------------------------------------------------------------------
    # SQLite (capa local / analítica, detalle completo)
    # ------------------------------------------------------------------

    def init_sqlite(self) -> None:
        """Crea la tabla SQLite si no existe."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS route_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                data_source TEXT NOT NULL DEFAULT 'unknown',
                distance_km REAL,
                travel_time_min REAL,
                no_traffic_time_min REAL,
                traffic_delay_min REAL,
                traffic_length_km REAL,
                average_speed_kmh REAL,
                departure_time TEXT,
                arrival_time TEXT,
                origin_temperature REAL,
                origin_feels_like REAL,
                origin_humidity REAL,
                origin_weather TEXT,
                destination_temperature REAL,
                destination_feels_like REAL,
                destination_humidity REAL,
                destination_weather TEXT,
                mobility_level TEXT,
                polyline TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(timestamp, origin, destination, data_source)
            )
            """
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_timestamp ON route_measurements(timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_origin ON route_measurements(origin)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_destination ON route_measurements(destination)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_data_source ON route_measurements(data_source)"
        )

        conn.commit()
        conn.close()

    def save_records_to_sqlite(self, records: List[dict]) -> None:
        """Guarda registros en SQLite, evitando duplicados exactos."""
        if not records:
            return

        self.init_sqlite()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        columns = [
            "timestamp", "origin", "destination", "data_source", "distance_km",
            "travel_time_min", "no_traffic_time_min", "traffic_delay_min",
            "traffic_length_km", "average_speed_kmh", "departure_time",
            "arrival_time", "origin_temperature", "origin_feels_like",
            "origin_humidity", "origin_weather", "destination_temperature",
            "destination_feels_like", "destination_humidity", "destination_weather",
            "mobility_level", "polyline", "created_at",
        ]

        for record in records:
            record_copy = record.copy()
            record_copy["created_at"] = datetime.now(timezone.utc).isoformat()
            record_copy.setdefault("data_source", "unknown")

            polyline_json = None
            if "polyline" in record_copy:
                import json
                polyline_data = record_copy.pop("polyline")
                if polyline_data:
                    try:
                        polyline_json = json.dumps(polyline_data)
                    except (TypeError, ValueError):
                        pass
            record_copy["polyline"] = polyline_json

            values = [record_copy.get(col) for col in columns]

            try:
                cursor.execute(
                    f"INSERT OR IGNORE INTO route_measurements ({','.join(columns)}) "
                    f"VALUES ({','.join(['?' for _ in columns])})",
                    values
                )
            except sqlite3.Error as e:
                logger.error(f"Error inserting record: {e}")

        conn.commit()
        conn.close()
        logger.info(f"Saved {len(records)} records to SQLite")

    def query_measurements(
        self,
        origin: Optional[str] = None,
        destination: Optional[str] = None,
        start_timestamp: Optional[str] = None,
        end_timestamp: Optional[str] = None,
        limit: int = 1000
    ) -> pd.DataFrame:
        """Consulta mediciones del SQLite con filtros opcionales."""
        self.init_sqlite()
        conn = sqlite3.connect(self.db_path)

        query = "SELECT * FROM route_measurements WHERE 1=1"
        params = []

        if origin:
            query += " AND origin = ?"
            params.append(origin)

        if destination:
            query += " AND destination = ?"
            params.append(destination)

        if start_timestamp:
            query += " AND timestamp >= ?"
            params.append(start_timestamp)

        if end_timestamp:
            query += " AND timestamp <= ?"
            params.append(end_timestamp)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        try:
            df = pd.read_sql_query(query, conn, params=params)
        except pd.errors.DatabaseError as e:
            logger.error(f"Database query error: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()

        return df

    def get_available_routes(self) -> List[tuple]:
        """Obtiene todas las rutas únicas disponibles en la base de datos."""
        self.init_sqlite()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT DISTINCT origin, destination FROM route_measurements "
            "ORDER BY origin, destination"
        )
        routes = cursor.fetchall()
        conn.close()

        return routes

    def get_route_statistics(self, origin: str, destination: str, hours: int = 24) -> dict:
        """Obtiene estadísticas de una ruta en las últimas N horas."""
        self.init_sqlite()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        start_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        cursor.execute(
            """
            SELECT
                COUNT(*) as count,
                AVG(travel_time_min) as avg_travel_time,
                MIN(travel_time_min) as min_travel_time,
                MAX(travel_time_min) as max_travel_time,
                AVG(traffic_delay_min) as avg_delay,
                AVG(origin_temperature) as avg_temp
            FROM route_measurements
            WHERE origin = ? AND destination = ? AND timestamp >= ?
            """,
            (origin, destination, start_time)
        )

        result = cursor.fetchone()
        conn.close()

        if not result or result[0] == 0:
            return {}

        return {
            "count": result[0],
            "avg_travel_time": round(result[1], 2) if result[1] else None,
            "min_travel_time": round(result[2], 2) if result[2] else None,
            "max_travel_time": round(result[3], 2) if result[3] else None,
            "avg_delay": round(result[4], 2) if result[4] else None,
            "avg_temperature": round(result[5], 2) if result[5] else None,
        }

    def get_all_routes_statistics(self, hours: int = 24) -> pd.DataFrame:
        """Obtiene estadísticas agregadas para todas las rutas."""
        self.init_sqlite()
        conn = sqlite3.connect(self.db_path)

        start_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        query = """
        SELECT
            origin,
            destination,
            COUNT(*) as measurements,
            ROUND(AVG(travel_time_min), 2) as avg_travel_time,
            ROUND(MIN(travel_time_min), 2) as min_travel_time,
            ROUND(MAX(travel_time_min), 2) as max_travel_time,
            ROUND(AVG(traffic_delay_min), 2) as avg_delay,
            ROUND(AVG(average_speed_kmh), 2) as avg_speed,
            MAX(timestamp) as last_measurement
        FROM route_measurements
        WHERE timestamp >= ?
        GROUP BY origin, destination
        ORDER BY origin, destination
        """

        try:
            df = pd.read_sql_query(query, conn, params=[start_time])
        except pd.errors.DatabaseError as e:
            logger.error(f"Database query error: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()

        return df

    def get_time_series(
        self,
        origin: str,
        destination: str,
        metric: str = "travel_time_min",
        hours: int = 24
    ) -> pd.DataFrame:
        """Obtiene una serie temporal de una métrica para una ruta."""
        self.init_sqlite()
        conn = sqlite3.connect(self.db_path)

        start_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        valid_metrics = [
            "travel_time_min", "traffic_delay_min", "average_speed_kmh",
            "origin_temperature", "origin_humidity", "distance_km"
        ]

        if metric not in valid_metrics:
            logger.error(f"Invalid metric: {metric}")
            return pd.DataFrame()

        query = f"""
        SELECT
            timestamp,
            {metric} as value
        FROM route_measurements
        WHERE origin = ? AND destination = ? AND timestamp >= ?
        ORDER BY timestamp ASC
        """

        try:
            df = pd.read_sql_query(query, conn, params=[origin, destination, start_time])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        except pd.errors.DatabaseError as e:
            logger.error(f"Database query error: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()

        return df

    def get_hourly_statistics(
        self,
        origin: str,
        destination: str,
        days: int = 7
    ) -> pd.DataFrame:
        """Agrupa estadísticas por hora para identificar patrones."""
        self.init_sqlite()
        conn = sqlite3.connect(self.db_path)

        start_time = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        query = """
        SELECT
            strftime('%H', timestamp) as hour,
            COUNT(*) as measurements,
            ROUND(AVG(travel_time_min), 2) as avg_travel_time,
            ROUND(AVG(traffic_delay_min), 2) as avg_delay,
            ROUND(AVG(average_speed_kmh), 2) as avg_speed
        FROM route_measurements
        WHERE origin = ? AND destination = ? AND timestamp >= ?
        GROUP BY strftime('%H', timestamp)
        ORDER BY hour ASC
        """

        try:
            df = pd.read_sql_query(query, conn, params=[origin, destination, start_time])
        except pd.errors.DatabaseError as e:
            logger.error(f"Database query error: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()

        return df

    def export_route_data(
        self,
        origin: str,
        destination: str,
        output_path: Path,
        hours: int = 24
    ) -> bool:
        """Exporta datos de una ruta a CSV."""
        try:
            df = self.query_measurements(origin, destination, limit=10000)

            if df.empty:
                logger.warning(f"No data found for {origin} → {destination}")
                return False

            df.to_csv(output_path, index=False)
            logger.info(f"Exported {len(df)} records to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False

    def get_database_summary(self) -> dict:
        """Obtiene un resumen completo de la base de datos."""
        self.init_sqlite()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM route_measurements")
        total_records = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT origin, destination FROM route_measurements)"
        )
        unique_routes = cursor.fetchone()[0]

        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM route_measurements")
        date_range = cursor.fetchone()

        cursor.execute("SELECT COUNT(DISTINCT origin) FROM route_measurements")
        unique_origins = cursor.fetchone()[0]

        conn.close()

        return {
            "total_records": total_records,
            "unique_routes": unique_routes,
            "unique_origins": unique_origins,
            "first_timestamp": date_range[0] if date_range and date_range[0] else None,
            "last_timestamp": date_range[1] if date_range and date_range[1] else None,
        }

    # ------------------------------------------------------------------
    # TimescaleDB (capa de producción, esquema resumido normalizado)
    # ------------------------------------------------------------------

    def save_records_to_timescale(self, records: List[dict], timescale_config: dict) -> int:
        """
        Escribe registros en la tabla `traffic_trips` de TimescaleDB
        (esquema simplificado, apto para BI: ver init/01_init.sql).

        Requiere psycopg2-binary instalado y un servidor TimescaleDB
        accesible (por defecto, el contenedor `timescaledb` del
        docker-compose). Si la conexión falla, se registra el error y no
        se interrumpe el flujo de guardado en CSV/SQLite.
        """
        if not records:
            return 0

        try:
            import psycopg2
        except ImportError:
            logger.error(
                "psycopg2-binary no está instalado. "
                "Instálalo con `pip install psycopg2-binary` para escribir en TimescaleDB."
            )
            return 0

        insert_sql = """
            INSERT INTO traffic_trips (
                datetime, origin, destination, distance_km, duration_min,
                temperature, humidity, weather_description, mobility_level,
                data_source, traffic_delay_min
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        rows = []
        for record in records:
            rows.append((
                record.get("timestamp"),
                record.get("origin"),
                record.get("destination"),
                record.get("distance_km"),
                record.get("travel_time_min"),
                record.get("origin_temperature"),
                record.get("origin_humidity"),
                record.get("origin_weather"),
                record.get("mobility_level"),
                record.get("data_source", "unknown"),
                record.get("traffic_delay_min"),
            ))

        conn = None
        try:
            conn = psycopg2.connect(**timescale_config)
            cursor = conn.cursor()
            cursor.executemany(insert_sql, rows)
            conn.commit()
            cursor.close()
            logger.info(f"Saved {len(rows)} records to TimescaleDB (traffic_trips)")
            return len(rows)
        except Exception as e:
            logger.error(f"Error writing to TimescaleDB: {e}")
            if conn:
                conn.rollback()
            return 0
        finally:
            if conn:
                conn.close()
