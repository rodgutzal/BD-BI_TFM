"""Pruebas para el módulo de análisis."""

import sys
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analytics import MobilityAnalytics
from src.database import RouteDatabase


def test_analytics_initialization():
    """Verifica que el analizador se inicializa correctamente."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        analytics = MobilityAnalytics(db_path)
        assert analytics.db is not None


def test_consistency_score():
    """Verifica el cálculo de consistency score."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "test.csv"
        db_path = Path(tmpdir) / "test.db"

        db = RouteDatabase(csv_path, db_path)
        analytics = MobilityAnalytics(db_path)

        records = [
            {
                "timestamp": "2026-07-19T00:00:00+00:00",
                "origin": "Msida",
                "destination": "Gzira",
                "travel_time_min": 5.0,
                "distance_km": 1.5,
            },
            {
                "timestamp": "2026-07-19T00:05:00+00:00",
                "origin": "Msida",
                "destination": "Gzira",
                "travel_time_min": 5.1,
                "distance_km": 1.5,
            },
            {
                "timestamp": "2026-07-19T00:10:00+00:00",
                "origin": "Msida",
                "destination": "Gzira",
                "travel_time_min": 5.05,
                "distance_km": 1.5,
            },
            {
                "timestamp": "2026-07-19T00:15:00+00:00",
                "origin": "Msida",
                "destination": "Gzira",
                "travel_time_min": 4.95,
                "distance_km": 1.5,
            },
            {
                "timestamp": "2026-07-19T00:20:00+00:00",
                "origin": "Msida",
                "destination": "Gzira",
                "travel_time_min": 5.15,
                "distance_km": 1.5,
            },
        ]

        db.save_records_to_sqlite(records)

        score = analytics.get_consistency_score("Msida", "Gzira", hours=24)
        assert score > 0
        assert score <= 100


def test_database_summary():
    """Verifica que se puede obtener un resumen de la BD."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "test.csv"
        db_path = Path(tmpdir) / "test.db"

        db = RouteDatabase(csv_path, db_path)

        records = [
            {
                "timestamp": "2026-07-19T00:00:00+00:00",
                "origin": "Msida",
                "destination": "Gzira",
                "travel_time_min": 5.0,
                "distance_km": 1.5,
            }
        ]

        db.save_records_to_sqlite(records)
        summary = db.get_database_summary()

        assert summary["total_records"] >= 1
        assert summary["unique_routes"] >= 1


if __name__ == "__main__":
    test_analytics_initialization()
    test_consistency_score()
    test_database_summary()
    print("✓ All analytics tests passed")
