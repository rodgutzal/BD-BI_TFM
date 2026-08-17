"""Silver layer: Cleaned and transformed data."""

import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import sqlite3


class SilverLayer:
    """
    Silver Layer: Data transformation and enrichment.
    - Cleans and standardizes data
    - Performs transformations
    - Calculates derived metrics
    - Stores cleaned data
    """

    def __init__(self, db_path: Path):
        """Initialize silver layer."""
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        """Create silver layer tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Cleaned measurements (silver)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS silver_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                travel_time_min REAL NOT NULL,
                no_traffic_time_min REAL,
                traffic_delay_min REAL,
                average_speed_kmh REAL,
                congestion_level TEXT,
                origin_temperature REAL,
                origin_humidity REAL,
                origin_weather TEXT,
                destination_temperature REAL,
                destination_humidity REAL,
                destination_weather TEXT,
                hour INTEGER,
                day_of_week INTEGER,
                day_of_month INTEGER,
                month INTEGER,
                is_peak_hour INTEGER,
                is_weekend INTEGER,
                transformation_timestamp TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(timestamp, origin, destination)
            )
        """)

        # Route aggregations (hourly)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS silver_route_hourly (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                avg_travel_time REAL,
                median_travel_time REAL,
                std_travel_time REAL,
                min_travel_time REAL,
                max_travel_time REAL,
                sample_count INTEGER,
                avg_speed REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(timestamp, origin, destination)
            )
        """)

        conn.commit()
        conn.close()

    def transform_bronze(self, bronze_df: pd.DataFrame) -> Dict:
        """
        Transform bronze data to silver.

        Args:
            bronze_df: Data from bronze layer

        Returns:
            Transformation summary
        """
        df = bronze_df.copy()

        # 1. Standardize column names
        # BD_BI_TFM2 fix: este rename tenía que ir ANTES de convertir la
        # columna a datetime — el df que llega de bronze_measurements trae
        # `raw_timestamp`, no `timestamp`, así que la línea original
        # `pd.to_datetime(df['timestamp'], ...)` fallaba con KeyError antes
        # de siquiera llegar al rename.
        df = df.rename(columns={
            'raw_timestamp': 'timestamp'
        })
        # format='mixed': robustez ante timestamps guardados con distinto
        # formato en distintos momentos (ver bug del separador T-vs-espacio
        # en bronze_layer.py) — sin esto, pd.to_datetime() infiere un solo
        # formato para todo el lote y falla en cuanto encuentra una fila
        # que no coincide, en vez de parsear cada una individualmente.
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, format='mixed')

        # 2. Calculate derived metrics
        df['traffic_delay_min'] = df['travel_time_min'] - df.get('no_traffic_time_min', df['travel_time_min'])
        df['traffic_delay_min'] = df['traffic_delay_min'].clip(lower=0)

        # 3. Classify congestion level
        def classify_congestion(delay):
            if pd.isna(delay):
                return 'unknown'
            if delay <= 1:
                return 'free_flow'
            elif delay <= 4:
                return 'moderate'
            else:
                return 'heavy'

        df['congestion_level'] = df['traffic_delay_min'].apply(classify_congestion)

        # 4. Add temporal features
        df['hour'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['day_of_month'] = df['timestamp'].dt.day
        df['month'] = df['timestamp'].dt.month
        df['is_peak_hour'] = (df['hour'].isin([7, 8, 9, 17, 18, 19])).astype(int)
        df['is_weekend'] = (df['day_of_week'].isin([5, 6])).astype(int)

        # 5. Store in silver
        df['transformation_timestamp'] = datetime.utcnow().isoformat()

        # BD_BI_TFM2 fix: el df que llega de bronze_measurements trae
        # columnas propias de esa capa (id, ingestion_timestamp,
        # data_quality_score, validation_status) que no existen en el
        # esquema de silver_measurements y que `to_sql` rechazaría. Se
        # filtra explícitamente a las columnas del esquema silver antes
        # de insertar (created_at usa su propio DEFAULT, no se envía).
        silver_columns = [
            'timestamp', 'origin', 'destination', 'travel_time_min',
            'no_traffic_time_min', 'traffic_delay_min', 'average_speed_kmh',
            'congestion_level', 'origin_temperature', 'origin_humidity',
            'origin_weather', 'destination_temperature', 'destination_humidity',
            'destination_weather', 'hour', 'day_of_week', 'day_of_month',
            'month', 'is_peak_hour', 'is_weekend', 'transformation_timestamp',
        ]
        for col in silver_columns:
            if col not in df.columns:
                df[col] = None
        df_to_insert = df[silver_columns].copy()
        # sqlite3 no sabe bindear pandas.Timestamp directamente; se guarda
        # como texto ISO 8601 (igual que el resto del proyecto).
        df_to_insert['timestamp'] = df_to_insert['timestamp'].apply(
            lambda t: t.isoformat() if pd.notna(t) else None
        )

        conn = sqlite3.connect(self.db_path)
        try:
            # INSERT OR IGNORE respeta el UNIQUE(timestamp, origin,
            # destination): reejecutar el pipeline sobre datos ya
            # transformados no duplica filas.
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(silver_columns))
            col_list = ','.join(silver_columns)
            rows = [tuple(r) for r in df_to_insert.itertuples(index=False, name=None)]
            cursor.executemany(
                f"INSERT OR IGNORE INTO silver_measurements ({col_list}) VALUES ({placeholders})",
                rows,
            )
            conn.commit()
            inserted = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else len(rows)
        except Exception as e:
            inserted = 0
            return {'error': str(e), 'inserted': 0}
        finally:
            conn.close()

        return {
            'status': 'success',
            'records_transformed': inserted,
            'mean_travel_time': float(df['travel_time_min'].mean()),
            'mean_delay': float(df['traffic_delay_min'].mean())
        }

    def aggregate_hourly(self) -> Dict:
        """Aggregate silver data to hourly summaries.

        BD_BI_TFM2 fix: la consulta original usaba MEDIAN()/STDDEV() en
        SQL, funciones que SQLite no trae integradas (a diferencia de
        PostgreSQL) — fallaba con `no such function`. Se agrupa en pandas
        en su lugar, que sí soporta .median()/.std() nativamente.
        """
        conn = sqlite3.connect(self.db_path)

        try:
            raw = pd.read_sql_query(
                "SELECT timestamp, origin, destination, travel_time_min, average_speed_kmh "
                "FROM silver_measurements",
                conn,
            )

            if raw.empty:
                return {'status': 'no_data', 'hourly_records_created': 0}

            raw['timestamp'] = pd.to_datetime(raw['timestamp'], utc=True)
            raw['hour_bucket'] = raw['timestamp'].dt.strftime('%Y-%m-%d %H:00')

            grouped = raw.groupby(['hour_bucket', 'origin', 'destination']).agg(
                avg_travel_time=('travel_time_min', 'mean'),
                median_travel_time=('travel_time_min', 'median'),
                std_travel_time=('travel_time_min', 'std'),
                min_travel_time=('travel_time_min', 'min'),
                max_travel_time=('travel_time_min', 'max'),
                sample_count=('travel_time_min', 'count'),
                avg_speed=('average_speed_kmh', 'mean'),
            ).reset_index()

            grouped = grouped.rename(columns={'hour_bucket': 'timestamp'})
            grouped['created_at'] = datetime.utcnow().isoformat()

            cursor = conn.cursor()
            columns = [
                'timestamp', 'origin', 'destination', 'avg_travel_time',
                'median_travel_time', 'std_travel_time', 'min_travel_time',
                'max_travel_time', 'sample_count', 'avg_speed', 'created_at',
            ]
            placeholders = ','.join(['?'] * len(columns))
            col_list = ','.join(columns)
            rows = [tuple(r) for r in grouped[columns].itertuples(index=False, name=None)]
            cursor.executemany(
                f"INSERT OR IGNORE INTO silver_route_hourly ({col_list}) VALUES ({placeholders})",
                rows,
            )
            conn.commit()

            return {
                'status': 'success',
                'hourly_records_created': len(grouped)
            }
        except Exception as e:
            return {'error': str(e)}
        finally:
            conn.close()

    def get_route_profile(self, origin: str, destination: str, days: int = 30) -> Dict:
        """Get silver-layer profile for a route."""
        conn = sqlite3.connect(self.db_path)

        query = f"""
            SELECT
                hour,
                day_of_week,
                AVG(travel_time_min) as avg_time,
                STDDEV(travel_time_min) as std_time,
                COUNT(*) as count
            FROM silver_measurements
            WHERE origin = ? AND destination = ?
            AND timestamp > datetime('now', '-{days} days')
            GROUP BY hour, day_of_week
        """

        try:
            df = pd.read_sql_query(query, conn, params=(origin, destination))
            return {
                'status': 'success',
                'route': f'{origin} -> {destination}',
                'days': days,
                'profiles': df.to_dict('records')
            }
        except Exception as e:
            return {'error': str(e)}
        finally:
            conn.close()
