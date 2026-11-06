"""Gestión de almacenamiento: CSV (histórico crudo), SQLite (capa local/analítica
con detalle completo) y TimescaleDB (capa de producción, resumen normalizado).

NOTA DE INTEGRACIÓN (BD_BI_TFM)
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
        self._sqlite_initialized = False
        self._poi_initialized = False
        self._poi_foursquare_initialized = False
        self._demographics_initialized = False
        self._population_history_initialized = False

    def _connect(self) -> sqlite3.Connection:
        """Conexión SQLite con WAL activado y timeout de reintento.

        FIX (database is locked): el collector (escritor) y el dashboard
        (lector, vía RouteDatabase cacheada con @st.cache_resource) tocan
        el mismo archivo mobility.db en paralelo. Con el modo de journal
        por defecto (DELETE) y sin timeout, cualquier choque momentáneo
        fallaba al instante. WAL permite que lectores y un escritor
        convivan sin bloquearse mutuamente en el caso normal, y el timeout
        hace que, si de todos modos hay contención puntual, la conexión
        espere y reintente en vez de lanzar `database is locked` de inmediato.
        """
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        return conn

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

    def init_sqlite(self, force: bool = False) -> None:
        """Crea la tabla SQLite si no existe.

        FIX (database is locked): antes se ejecutaba el CREATE TABLE/INDEX
        en CADA llamada a save_records_to_sqlite/query_measurements/etc.
        — es decir, en cada lectura del dashboard, no solo al arrancar.
        Cada una de esas sentencias DDL pide un lock de escritura aunque la
        tabla ya exista (el "IF NOT EXISTS" evita el error, no evita el
        lock), compitiendo directo con las escrituras reales del collector.
        Ahora el DDL corre una sola vez por instancia de RouteDatabase
        (que además ya vive cacheada vía @st.cache_resource en el
        dashboard), y se puede forzar a re-ejecutar con force=True si algún
        día hace falta (p. ej. tras borrar el archivo a mano).
        """
        if self._sqlite_initialized and not force:
            return

        conn = self._connect()
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
        self._sqlite_initialized = True

    def save_records_to_sqlite(self, records: List[dict]) -> None:
        """Guarda registros en SQLite, evitando duplicados exactos."""
        if not records:
            return

        self.init_sqlite()
        conn = self._connect()
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
        conn = self._connect()

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
        conn = self._connect()
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
        conn = self._connect()
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

    # ------------------------------------------------------------------
    # POIs / infraestructura urbana (escuelas, hospitales, centros
    # comerciales, negocios) — refrescados periódicamente por
    # src/poi_extraction.py vía Overpass API, no por el collector de
    # tráfico/clima (cadencia totalmente distinta: esto cambia poco).
    # ------------------------------------------------------------------

    def init_poi_table(self, force: bool = False) -> None:
        """Crea la tabla de POIs si no existe (mismo fix que init_sqlite:
        solo corre el DDL una vez por instancia, ver nota ahí)."""
        if self._poi_initialized and not force:
            return

        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pois (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                osm_type TEXT NOT NULL,
                osm_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT,
                name TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(osm_type, osm_id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_poi_category ON pois(category)"
        )

        conn.commit()
        conn.close()
        self._poi_initialized = True

    def save_pois(self, pois: List[dict]) -> int:
        """Guarda/actualiza POIs (upsert por osm_type+osm_id), para que
        refrescos sucesivos actualicen registros existentes en vez de
        acumular duplicados indefinidamente."""
        if not pois:
            return 0

        self.init_poi_table()
        conn = self._connect()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        for poi in pois:
            try:
                cursor.execute(
                    """
                    INSERT INTO pois
                        (osm_type, osm_id, category, subcategory, name, latitude, longitude, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(osm_type, osm_id) DO UPDATE SET
                        category=excluded.category,
                        subcategory=excluded.subcategory,
                        name=excluded.name,
                        latitude=excluded.latitude,
                        longitude=excluded.longitude,
                        updated_at=excluded.updated_at
                    """,
                    (
                        poi["osm_type"], poi["osm_id"], poi["category"], poi.get("subcategory"),
                        poi.get("name"), poi["latitude"], poi["longitude"], now,
                    ),
                )
            except sqlite3.Error as e:
                logger.error(f"Error upserting POI {poi.get('osm_type')}/{poi.get('osm_id')}: {e}")

        conn.commit()
        conn.close()
        logger.info(f"Saved/updated {len(pois)} POIs")
        return len(pois)

    def get_pois(self, categories: Optional[List[str]] = None) -> pd.DataFrame:
        """Consulta POIs guardados, opcionalmente filtrados por categoría."""
        self.init_poi_table()
        conn = self._connect()

        query = "SELECT * FROM pois"
        params: list = []
        if categories:
            placeholders = ",".join("?" for _ in categories)
            query += f" WHERE category IN ({placeholders})"
            params = list(categories)

        try:
            df = pd.read_sql_query(query, conn, params=params)
        except pd.errors.DatabaseError as e:
            logger.error(f"POI query error: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()

        return df

    def init_poi_foursquare_table(self, force: bool = False) -> None:
        """Crea la tabla de POIs de Foursquare si no existe.

        Tabla SEPARADA de `pois` (Overpass) a propósito: `pois` tiene
        UNIQUE(osm_type, osm_id), específico de OpenStreetMap — forzar ahí
        filas de Foursquare (que se identifican por fsq_place_id, sin
        osm_type/osm_id) habría implicado modificar el esquema de una tabla
        que ya tiene miles de registros reales de Overpass (3.800+ al 6-nov-2026). Mismo patrón de
        inicialización única por instancia que init_sqlite/init_poi_table
        (ver nota en init_sqlite): evita repetir el DDL en cada consulta.
        """
        if self._poi_foursquare_initialized and not force:
            return

        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pois_foursquare (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fsq_place_id TEXT NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT,
                name TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(fsq_place_id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_poi_fsq_category ON pois_foursquare(category)"
        )

        conn.commit()
        conn.close()
        self._poi_foursquare_initialized = True

    def save_pois_foursquare(self, pois: List[dict]) -> int:
        """Guarda/actualiza POIs de Foursquare (upsert por fsq_place_id).
        Mismo patrón que save_pois (Overpass)."""
        if not pois:
            return 0

        self.init_poi_foursquare_table()
        conn = self._connect()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        for poi in pois:
            try:
                cursor.execute(
                    """
                    INSERT INTO pois_foursquare
                        (fsq_place_id, category, subcategory, name, latitude, longitude, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fsq_place_id) DO UPDATE SET
                        category=excluded.category,
                        subcategory=excluded.subcategory,
                        name=excluded.name,
                        latitude=excluded.latitude,
                        longitude=excluded.longitude,
                        updated_at=excluded.updated_at
                    """,
                    (
                        poi["fsq_place_id"], poi["category"], poi.get("subcategory"),
                        poi.get("name"), poi["latitude"], poi["longitude"], now,
                    ),
                )
            except sqlite3.Error as e:
                logger.error(f"Error upserting Foursquare POI {poi.get('fsq_place_id')}: {e}")

        conn.commit()
        conn.close()
        logger.info(f"Saved/updated {len(pois)} Foursquare POIs")
        return len(pois)

    def get_pois_foursquare(self, categories: Optional[List[str]] = None) -> pd.DataFrame:
        """Consulta POIs de Foursquare guardados, opcionalmente filtrados
        por categoría. Mismo patrón que get_pois (Overpass)."""
        self.init_poi_foursquare_table()
        conn = self._connect()

        query = "SELECT * FROM pois_foursquare"
        params: list = []
        if categories:
            placeholders = ",".join("?" for _ in categories)
            query += f" WHERE category IN ({placeholders})"
            params = list(categories)

        try:
            df = pd.read_sql_query(query, conn, params=params)
        except pd.errors.DatabaseError as e:
            logger.error(f"Foursquare POI query error: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()

        return df

    def init_demographics_table(self, force: bool = False) -> None:
        """Crea la tabla de demografía por zona si no existe.

        `dcid` (Data Commons ID) se guarda como CACHÉ de la resolución por
        nombre — resolver un lugar nuevo cuesta una llamada API; una vez
        resuelto, las corridas siguientes reusan el dcid guardado en vez de
        volver a resolver. `population`/`observation_date` quedan NULL
        hasta que llega la primera observación exitosa (una fila puede
        existir solo con el dcid resuelto, aún sin población).
        """
        if self._demographics_initialized and not force:
            return

        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS zone_demographics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_name TEXT NOT NULL,
                dcid TEXT,
                population INTEGER,
                observation_date TEXT,
                source TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(zone_name)
            )
            """
        )

        # Columnas agregadas después (ALTER TABLE es aditivo — no recrea la
        # tabla ni toca las filas existentes) para el reconciliado a un año
        # común: `basis_year`/`basis_population` guardan el dato REAL
        # (observado) que se usó como ancla; `method` indica si el valor de
        # `population` es tal cual observado o si se proyectó con la tasa de
        # crecimiento nacional. SQLite no soporta "ADD COLUMN IF NOT EXISTS",
        # así que se consulta el esquema actual antes de intentar agregarlas.
        existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(zone_demographics)")}
        for col, ddl in (
            ("basis_year", "ALTER TABLE zone_demographics ADD COLUMN basis_year INTEGER"),
            ("basis_population", "ALTER TABLE zone_demographics ADD COLUMN basis_population INTEGER"),
            ("method", "ALTER TABLE zone_demographics ADD COLUMN method TEXT"),
        ):
            if col not in existing_cols:
                cursor.execute(ddl)

        conn.commit()
        conn.close()
        self._demographics_initialized = True

    def save_demographics(self, records: List[dict]) -> int:
        """Guarda/actualiza registros de demografía (upsert por zone_name).
        Cada `record` puede traer solo `zone_name` + `dcid` (recién
        resuelto, sin observación todavía) o los cinco campos completos."""
        if not records:
            return 0

        self.init_demographics_table()
        conn = self._connect()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        for r in records:
            try:
                cursor.execute(
                    """
                    INSERT INTO zone_demographics
                        (zone_name, dcid, population, observation_date, source, updated_at, basis_year, basis_population, method)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(zone_name) DO UPDATE SET
                        dcid=COALESCE(excluded.dcid, zone_demographics.dcid),
                        population=COALESCE(excluded.population, zone_demographics.population),
                        observation_date=COALESCE(excluded.observation_date, zone_demographics.observation_date),
                        source=COALESCE(excluded.source, zone_demographics.source),
                        basis_year=COALESCE(excluded.basis_year, zone_demographics.basis_year),
                        basis_population=COALESCE(excluded.basis_population, zone_demographics.basis_population),
                        method=COALESCE(excluded.method, zone_demographics.method),
                        updated_at=excluded.updated_at
                    """,
                    (
                        r["zone_name"], r.get("dcid"), r.get("population"),
                        r.get("observation_date"), r.get("source"), now,
                        r.get("basis_year"), r.get("basis_population"), r.get("method"),
                    ),
                )
            except sqlite3.Error as e:
                logger.error(f"Error upserting demographics for {r.get('zone_name')}: {e}")

        conn.commit()
        conn.close()
        logger.info(f"Saved/updated demographics for {len(records)} zones")
        return len(records)

    def get_demographics(self) -> pd.DataFrame:
        """Consulta la demografía guardada por zona."""
        self.init_demographics_table()
        conn = self._connect()
        try:
            df = pd.read_sql_query("SELECT * FROM zone_demographics", conn)
        except pd.errors.DatabaseError as e:
            logger.error(f"Demographics query error: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()
        return df

    def init_population_history_table(self, force: bool = False) -> None:
        """Serie histórica de población por zona: TODAS las observaciones que
        Data Commons tiene (varias fechas y fuentes por zona), no solo la más
        reciente. Permite elegir después un año de referencia común, o ver
        la tendencia de crecimiento de cada zona. `zone_demographics` sigue
        siendo la tabla "operativa" (una fila por zona)."""
        if self._population_history_initialized and not force:
            return

        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS zone_population_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_name TEXT NOT NULL,
                observation_date TEXT NOT NULL,
                year INTEGER,
                population INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE(zone_name, observation_date, source)
            )
            """
        )
        conn.commit()
        conn.close()
        self._population_history_initialized = True

    def save_population_history(self, records: List[dict]) -> int:
        """Upsert por (zone_name, observation_date, source)."""
        if not records:
            return 0

        self.init_population_history_table()
        conn = self._connect()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        for r in records:
            try:
                cursor.execute(
                    """
                    INSERT INTO zone_population_history
                        (zone_name, observation_date, year, population, source, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(zone_name, observation_date, source) DO UPDATE SET
                        year=excluded.year,
                        population=excluded.population,
                        updated_at=excluded.updated_at
                    """,
                    (r["zone_name"], r["observation_date"], r.get("year"),
                     r["population"], r.get("source") or "", now),
                )
            except sqlite3.Error as e:
                logger.error(f"Error upserting population history for {r.get('zone_name')}: {e}")

        conn.commit()
        conn.close()
        logger.info(f"Saved/updated {len(records)} population history rows")
        return len(records)

    def get_population_history(self) -> pd.DataFrame:
        self.init_population_history_table()
        conn = self._connect()
        try:
            df = pd.read_sql_query(
                "SELECT * FROM zone_population_history ORDER BY zone_name, observation_date", conn
            )
        except pd.errors.DatabaseError as e:
            logger.error(f"Population history query error: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()
        return df

    def get_all_routes_statistics(self, hours: int = 24) -> pd.DataFrame:
        """Obtiene estadísticas agregadas para todas las rutas."""
        self.init_sqlite()
        conn = self._connect()

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
        conn = self._connect()

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
        conn = self._connect()

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

    # ------------------------------------------------------------------
    # Consultas de ventana completa (sin LIMIT)
    #
    # query_measurements() ordena de la más reciente a la más antigua y corta
    # en `limit` filas. Los dashboards lo usaban con limit=10000 para
    # gráficos de "30 días" y "7 días", pero con recolección continua (~1.800
    # filas/día) 10.000 filas son ~5 días: el gráfico decía cubrir 30 días
    # y mostraba solo los más recientes, sin avisar. Estos métodos agregan en
    # SQL (devuelven una fila por día / por ruta-hora, no por medición) o
    # traen solo las columnas necesarias, así la ventana pedida se cubre
    # entera sin importar cuántas filas haya.
    # ------------------------------------------------------------------

    def _window_start(self, days: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    def get_daily_average(self, days: int = 30) -> pd.DataFrame:
        """Tiempo de viaje promedio por día (UTC) de las últimas `days` días,
        sobre todas las rutas. Columnas: date, avg_travel_time, measurements."""
        self.init_sqlite()
        conn = self._connect()
        try:
            return pd.read_sql_query(
                """
                SELECT substr(timestamp, 1, 10) AS date,
                       AVG(travel_time_min)     AS avg_travel_time,
                       COUNT(travel_time_min)   AS measurements
                FROM route_measurements
                WHERE timestamp >= ? AND travel_time_min IS NOT NULL
                GROUP BY substr(timestamp, 1, 10)
                ORDER BY date
                """,
                conn, params=[self._window_start(days)],
            )
        except pd.errors.DatabaseError as e:
            logger.error(f"Daily average query error: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def get_route_hour_average(self, days: int = 7) -> pd.DataFrame:
        """Tiempo de viaje promedio por ruta y hora del día (UTC) en las
        últimas `days` días. Columnas: origin, destination, hour (0-23),
        avg_travel_time, measurements."""
        self.init_sqlite()
        conn = self._connect()
        try:
            return pd.read_sql_query(
                """
                SELECT origin, destination,
                       CAST(strftime('%H', timestamp) AS INTEGER) AS hour,
                       AVG(travel_time_min)                       AS avg_travel_time,
                       COUNT(travel_time_min)                     AS measurements
                FROM route_measurements
                WHERE timestamp >= ? AND travel_time_min IS NOT NULL
                GROUP BY origin, destination, strftime('%H', timestamp)
                ORDER BY origin, destination, hour
                """,
                conn, params=[self._window_start(days)],
            )
        except pd.errors.DatabaseError as e:
            logger.error(f"Route-hour average query error: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def get_numeric_columns(self) -> List[str]:
        """Columnas numéricas (REAL/INTEGER) de route_measurements, sin `id`."""
        self.init_sqlite()
        conn = self._connect()
        try:
            return [
                row[1] for row in conn.execute("PRAGMA table_info(route_measurements)")
                if row[2].upper() in ("REAL", "INTEGER") and row[1] != "id"
            ]
        finally:
            conn.close()

    def query_columns(self, columns: List[str], days: int) -> pd.DataFrame:
        """Solo las `columns` pedidas de TODAS las mediciones de las últimas
        `days` días (sin LIMIT). Los nombres se validan contra el esquema real
        antes de armar el SQL."""
        self.init_sqlite()
        conn = self._connect()
        try:
            valid = {row[1] for row in conn.execute("PRAGMA table_info(route_measurements)")}
            unknown = [c for c in columns if c not in valid]
            if unknown:
                raise ValueError(f"Columnas desconocidas en route_measurements: {unknown}")
            if not columns:
                return pd.DataFrame()
            select = ", ".join(f'"{c}"' for c in columns)
            return pd.read_sql_query(
                f"SELECT {select} FROM route_measurements WHERE timestamp >= ?",
                conn, params=[self._window_start(days)],
            )
        finally:
            conn.close()

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
        conn = self._connect()
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
