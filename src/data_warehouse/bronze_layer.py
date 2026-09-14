"""Bronze layer: Raw data ingestion and validation."""

import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
import sqlite3


class BronzeLayer:
    """
    Bronze Layer: Raw data ingestion, validation, and cleaning.
    - Accepts raw data from collectors
    - Performs basic data quality checks
    - Stores raw + validation metadata
    """

    def __init__(self, db_path: Path):
        """Initialize bronze layer with database."""
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        """Create bronze layer tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Raw measurements (bronze)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bronze_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_timestamp TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                travel_time_min REAL,
                no_traffic_time_min REAL,
                average_speed_kmh REAL,
                origin_temperature REAL,
                origin_humidity REAL,
                origin_weather TEXT,
                destination_temperature REAL,
                destination_humidity REAL,
                destination_weather TEXT,
                ingestion_timestamp TEXT NOT NULL,
                data_quality_score REAL,
                validation_status TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Data quality metrics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_quality_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                total_records INTEGER,
                valid_records INTEGER,
                missing_values INTEGER,
                outliers INTEGER,
                avg_quality_score REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def ingest(self, df: pd.DataFrame) -> Dict:
        """
        Ingest raw data with validation.

        Args:
            df: Raw DataFrame from collector

        Returns:
            Ingestion summary with quality metrics
        """
        df = df.copy()
        original_count = len(df)
        issues = []

        # 1. Handle duplicates (keep first occurrence)
        before_dedup = len(df)
        df = df.drop_duplicates(subset=['timestamp', 'origin', 'destination'], keep='first')
        if len(df) < before_dedup:
            issues.append(f"Removed {before_dedup - len(df)} duplicates")

        # 2. Validate required columns
        required_cols = ['timestamp', 'origin', 'destination', 'travel_time_min']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            issues.append(f"Missing columns: {missing_cols}")
            return {'error': 'Missing required columns', 'issues': issues}

        # 3. Data type validation
        # format='mixed': ver la misma nota en silver_layer.py — robustez
        # ante timestamps con formato inconsistente en el df de entrada.
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce', utc=True, format='mixed')
        df['travel_time_min'] = pd.to_numeric(df['travel_time_min'], errors='coerce')

        # 4. Remove rows with NaN in critical columns
        before_validation = len(df)
        df = df.dropna(subset=['timestamp', 'travel_time_min', 'origin', 'destination'])
        if len(df) < before_validation:
            issues.append(f"Removed {before_validation - len(df)} rows with missing critical values")

        # BD_BI_TFM fix: pd.to_datetime() de arriba convierte la columna a
        # datetime64 (necesario para validar/soltar filas inválidas), pero
        # si se guarda así, pandas.to_sql() la serializa con un ESPACIO
        # como separador ('2026-08-17 04:00:40...'), no con 'T' como el
        # resto del proyecto ('2026-08-17T04:00:40...'). Como
        # src/collector.py vuelve a consultar bronze_measurements buscando
        # el string original (con 'T') para pasárselo a Silver, esa
        # comparación nunca coincidía — Silver recibía 0 filas cada ciclo,
        # y por lo tanto Gold nunca tenía nada que agregar ("no_data").
        # Se reconvierte a string ISO explícitamente para mantener el
        # formato consistente en toda la base.
        df['timestamp'] = df['timestamp'].apply(lambda t: t.isoformat())

        # 5. Outlier detection (basic bounds check)
        travel_time_bounds = (0, 500)  # 0 to 500 minutes
        outliers = len(df[(df['travel_time_min'] < travel_time_bounds[0]) | (df['travel_time_min'] > travel_time_bounds[1])])
        if outliers > 0:
            issues.append(f"Found {outliers} potential outliers in travel_time_min")
            df = df[(df['travel_time_min'] >= travel_time_bounds[0]) & (df['travel_time_min'] <= travel_time_bounds[1])]

        # 6. Calculate data quality score
        quality_scores = []
        for _, row in df.iterrows():
            score = self._calculate_quality_score(row)
            quality_scores.append(score)
        df['data_quality_score'] = quality_scores

        # 7. Store in bronze
        df['ingestion_timestamp'] = datetime.utcnow().isoformat()
        df['validation_status'] = 'validated'

        # BD_BI_TFM fix: la tabla bronze_measurements define la columna
        # como `raw_timestamp` (no `timestamp`), y sólo acepta las columnas
        # de su propio esquema. El df de entrada puede traer columnas extra
        # del esquema unificado de route_measurements (traffic_delay_min,
        # data_source, mobility_level, polyline, etc.) que no existen aquí
        # y que `to_sql` rechazaría. Se renombra y se filtra explícitamente
        # antes de insertar.
        df = df.rename(columns={'timestamp': 'raw_timestamp'})
        bronze_columns = [
            'raw_timestamp', 'origin', 'destination', 'travel_time_min',
            'no_traffic_time_min', 'average_speed_kmh', 'origin_temperature',
            'origin_humidity', 'origin_weather', 'destination_temperature',
            'destination_humidity', 'destination_weather',
            'ingestion_timestamp', 'data_quality_score', 'validation_status',
        ]
        for col in bronze_columns:
            if col not in df.columns:
                df[col] = None
        df_to_insert = df[bronze_columns]

        conn = sqlite3.connect(self.db_path)
        try:
            df_to_insert.to_sql('bronze_measurements', conn, if_exists='append', index=False)
            conn.commit()
            inserted = len(df_to_insert)
        except Exception as e:
            issues.append(f"Database error: {str(e)}")
            inserted = 0
        finally:
            conn.close()

        return {
            'status': 'success',
            'original_records': original_count,
            'inserted_records': inserted,
            'removed_records': original_count - inserted,
            'quality_score': float(np.mean(quality_scores)) if quality_scores else 0,
            'issues': issues
        }

    @staticmethod
    def _calculate_quality_score(row: pd.Series) -> float:
        """
        Calculate data quality score (0-100).

        Factors:
        - Presence of values (40 points)
        - Reasonable ranges (30 points)
        - Completeness (30 points)
        """
        score = 100.0

        # Check for required fields
        required = ['timestamp', 'origin', 'destination', 'travel_time_min']
        missing = sum(1 for col in required if pd.isna(row.get(col)))
        score -= missing * 10

        # Check ranges
        if pd.notna(row.get('travel_time_min')):
            if not (0 < row['travel_time_min'] < 500):
                score -= 20
        else:
            score -= 20

        # Check optional fields
        optional = ['origin_temperature', 'origin_humidity', 'destination_temperature', 'destination_humidity']
        missing_optional = sum(1 for col in optional if pd.isna(row.get(col)))
        score -= missing_optional * 2

        return max(0, min(100, score))

    def get_statistics(self, date: Optional[str] = None) -> Dict:
        """Get data quality statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if date:
            cursor.execute("""
                SELECT COUNT(*), AVG(data_quality_score)
                FROM bronze_measurements
                WHERE DATE(created_at) = ?
            """, (date,))
        else:
            cursor.execute("""
                SELECT COUNT(*), AVG(data_quality_score)
                FROM bronze_measurements
            """)

        total, avg_score = cursor.fetchone() or (0, 0)
        conn.close()

        return {
            'total_records': total,
            'avg_quality_score': float(avg_score) if avg_score else 0
        }
