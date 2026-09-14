"""Gold layer: Analytics-ready data and KPIs."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import sqlite3


class GoldLayer:
    """
    Gold Layer: Analytics-ready data.
    - Pre-aggregated metrics
    - KPIs and business metrics
    - Dimension tables
    - Ready for BI consumption
    """

    def __init__(self, db_path: Path):
        """Initialize gold layer."""
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        """Create gold layer tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Route KPIs (daily)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gold_route_kpis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                avg_travel_time REAL,
                median_travel_time REAL,
                p95_travel_time REAL,
                avg_delay REAL,
                reliability_score REAL,
                peak_hour TEXT,
                peak_travel_time REAL,
                sample_count INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, origin, destination)
            )
        """)

        # Route rankings (daily)
        # BD_BI_TFM fix: se añade UNIQUE(date, origin, destination) — la
        # tabla original no tenía ninguna restricción, así que recalcular
        # el ranking del mismo día (cada vez que corre el collector)
        # acumulaba filas duplicadas sin parar. Con la restricción,
        # calculate_rankings() puede usar INSERT OR REPLACE de forma segura.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gold_route_rankings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                rank INTEGER,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                avg_travel_time REAL,
                reliability_score REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, origin, destination)
            )
        """)

        # Time-based summaries
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gold_time_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                hour INTEGER,
                total_measurements INTEGER,
                avg_travel_time REAL,
                std_travel_time REAL,
                congestion_percentage REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, hour)
            )
        """)

        # Weather impact analysis
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gold_weather_impact (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                weather_condition TEXT,
                avg_travel_time REAL,
                impact_factor REAL,
                sample_count INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, weather_condition)
            )
        """)

        conn.commit()
        conn.close()

    def calculate_kpis(self, date: Optional[str] = None) -> Dict:
        """Calculate daily KPIs for all routes."""
        if date is None:
            date = datetime.utcnow().date().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get data for date
        query = f"""
            SELECT
                origin,
                destination,
                travel_time_min,
                traffic_delay_min,
                hour,
                average_speed_kmh
            FROM silver_measurements
            WHERE DATE(timestamp) = ?
        """

        try:
            df = pd.read_sql_query(query, conn, params=(date,))

            if df.empty:
                return {'status': 'no_data', 'date': date}

            kpis = []
            for (origin, destination), group in df.groupby(['origin', 'destination']):
                # Calculate metrics
                avg_travel = group['travel_time_min'].mean()
                median_travel = group['travel_time_min'].median()
                p95_travel = group['travel_time_min'].quantile(0.95)
                avg_delay = group['traffic_delay_min'].mean()

                # Reliability (low std = reliable)
                travel_std = group['travel_time_min'].std()
                reliability_score = max(0, 100 - (travel_std * 2))  # 0-100 scale

                # Peak hour
                peak_hour_group = group.groupby('hour')['travel_time_min'].mean()
                peak_hour = str(peak_hour_group.idxmax()).zfill(2) if not peak_hour_group.empty else '00'
                peak_time = float(peak_hour_group.max()) if not peak_hour_group.empty else avg_travel

                kpi = {
                    'date': date,
                    'origin': origin,
                    'destination': destination,
                    'avg_travel_time': float(avg_travel),
                    'median_travel_time': float(median_travel),
                    'p95_travel_time': float(p95_travel),
                    'avg_delay': float(avg_delay),
                    'reliability_score': float(reliability_score),
                    'peak_hour': peak_hour,
                    'peak_travel_time': float(peak_time),
                    'sample_count': len(group)
                }
                kpis.append(kpi)

            # Store in gold
            # BD_BI_TFM fix: el `to_sql(if_exists='append')` original
            # hacía un INSERT plano — la segunda vez que se calculaban las
            # KPIs de un mismo día (p.ej. porque el collector corre cada
            # pocos minutos) chocaba con el UNIQUE(date, origin,
            # destination) y lanzaba IntegrityError. Se usa INSERT OR
            # REPLACE para que recalcular el día actual, según van
            # llegando más mediciones, sea seguro.
            kpi_df = pd.DataFrame(kpis)
            columns = [
                'date', 'origin', 'destination', 'avg_travel_time',
                'median_travel_time', 'p95_travel_time', 'avg_delay',
                'reliability_score', 'peak_hour', 'peak_travel_time',
                'sample_count',
            ]
            placeholders = ','.join(['?'] * len(columns))
            col_list = ','.join(columns)
            rows = [tuple(r) for r in kpi_df[columns].itertuples(index=False, name=None)]
            cursor.executemany(
                f"INSERT OR REPLACE INTO gold_route_kpis ({col_list}) VALUES ({placeholders})",
                rows,
            )
            conn.commit()

            return {
                'status': 'success',
                'date': date,
                'kpis_calculated': len(kpis),
                'routes': len(kpi_df.groupby(['origin', 'destination']))
            }
        except Exception as e:
            return {'error': str(e)}
        finally:
            conn.close()

    def calculate_rankings(self, date: Optional[str] = None, metric: str = 'reliability_score') -> Dict:
        """Calculate route rankings for a date.

        BD_BI_TFM fix: el valor por defecto original era 'reliability',
        que no es el nombre real de ninguna columna de gold_route_kpis
        (la columna se llama `reliability_score`) — SQLite fallaba con
        `no such column: reliability` en cuanto se llamaba sin argumentos.
        """
        if date is None:
            date = datetime.utcnow().date().isoformat()

        valid_metrics = {'reliability_score', 'avg_travel_time'}
        if metric not in valid_metrics:
            metric = 'reliability_score'

        conn = sqlite3.connect(self.db_path)

        query = f"""
            SELECT
                origin,
                destination,
                avg_travel_time,
                reliability_score
            FROM gold_route_kpis
            WHERE date = ?
            ORDER BY {metric} {'DESC' if metric == 'reliability_score' else 'ASC'}
        """

        try:
            df = pd.read_sql_query(query, conn, params=(date,))

            if df.empty:
                return {'status': 'no_data'}

            df['rank'] = range(1, len(df) + 1)
            df['date'] = date
            df = df[['date', 'rank', 'origin', 'destination', 'avg_travel_time', 'reliability_score']]

            # Store rankings (INSERT OR REPLACE: ver nota en _ensure_tables)
            cursor = conn.cursor()
            columns = ['date', 'rank', 'origin', 'destination', 'avg_travel_time', 'reliability_score']
            placeholders = ','.join(['?'] * len(columns))
            col_list = ','.join(columns)
            rows = [tuple(r) for r in df[columns].itertuples(index=False, name=None)]
            cursor.executemany(
                f"INSERT OR REPLACE INTO gold_route_rankings ({col_list}) VALUES ({placeholders})",
                rows,
            )
            conn.commit()

            return {
                'status': 'success',
                'date': date,
                'rankings': df.to_dict('records')
            }
        except Exception as e:
            return {'error': str(e)}
        finally:
            conn.close()

    def get_executive_summary(self, days: int = 30) -> Dict:
        """Get executive summary for dashboard."""
        conn = sqlite3.connect(self.db_path)

        try:
            # Overall metrics
            query = f"""
                SELECT
                    AVG(avg_travel_time) as system_avg_travel_time,
                    AVG(reliability_score) as system_reliability,
                    COUNT(DISTINCT origin || '-' || destination) as route_count,
                    SUM(sample_count) as total_measurements
                FROM gold_route_kpis
                WHERE date >= datetime('now', '-{days} days')
            """

            summary_df = pd.read_sql_query(query, conn)

            # Best and worst routes
            rankings_query = f"""
                SELECT
                    origin,
                    destination,
                    AVG(avg_travel_time) as avg_time,
                    AVG(reliability_score) as avg_reliability
                FROM gold_route_kpis
                WHERE date >= datetime('now', '-{days} days')
                GROUP BY origin, destination
                ORDER BY avg_reliability DESC
            """

            rankings = pd.read_sql_query(rankings_query, conn)

            return {
                'system_avg_travel_time': float(summary_df['system_avg_travel_time'].iloc[0]) if not summary_df.empty else 0,
                'system_reliability': float(summary_df['system_reliability'].iloc[0]) if not summary_df.empty else 0,
                'total_routes': int(summary_df['route_count'].iloc[0]) if not summary_df.empty else 0,
                'total_measurements': int(summary_df['total_measurements'].iloc[0]) if not summary_df.empty else 0,
                'best_routes': rankings.head(3).to_dict('records'),
                'worst_routes': rankings.tail(3).to_dict('records')
            }
        except Exception as e:
            return {'error': str(e)}
        finally:
            conn.close()
