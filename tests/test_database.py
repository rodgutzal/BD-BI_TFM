"""Pruebas para el módulo de base de datos."""

import sys
from pathlib import Path
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import RouteDatabase


def test_database_init():
    """Verifica que la base de datos se inicializa correctamente."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "test.csv"
        db_path = Path(tmpdir) / "test.db"

        db = RouteDatabase(csv_path, db_path)
        db.init_sqlite()

        assert db_path.exists()


def test_save_records_to_csv():
    """Verifica que se guardan registros en CSV."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "test.csv"
        db_path = Path(tmpdir) / "test.db"

        db = RouteDatabase(csv_path, db_path)

        records = [
            {
                "timestamp": "2026-07-19T00:00:00+00:00",
                "origin": "Msida",
                "destination": "Gzira",
                "distance_km": 1.5,
                "travel_time_min": 5.0,
                "no_traffic_time_min": 4.8,
                "traffic_delay_min": 0.2,
            }
        ]

        db.save_records_to_csv(records)
        assert csv_path.exists()


def test_save_records_to_sqlite():
    """Verifica que se guardan registros en SQLite."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "test.csv"
        db_path = Path(tmpdir) / "test.db"

        db = RouteDatabase(csv_path, db_path)

        records = [
            {
                "timestamp": "2026-07-19T00:00:00+00:00",
                "origin": "Msida",
                "destination": "Gzira",
                "distance_km": 1.5,
                "travel_time_min": 5.0,
                "no_traffic_time_min": 4.8,
                "traffic_delay_min": 0.2,
            }
        ]

        db.save_records_to_sqlite(records)
        assert db_path.exists()


def test_query_measurements():
    """Verifica que se pueden consultar mediciones."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "test.csv"
        db_path = Path(tmpdir) / "test.db"

        db = RouteDatabase(csv_path, db_path)

        records = [
            {
                "timestamp": "2026-07-19T00:00:00+00:00",
                "origin": "Msida",
                "destination": "Gzira",
                "distance_km": 1.5,
                "travel_time_min": 5.0,
                "no_traffic_time_min": 4.8,
                "traffic_delay_min": 0.2,
            }
        ]

        db.save_records_to_sqlite(records)
        result = db.query_measurements(origin="Msida", destination="Gzira")

        assert len(result) == 1
        assert result.iloc[0]["origin"] == "Msida"


if __name__ == "__main__":
    test_database_init()
    test_save_records_to_csv()
    test_save_records_to_sqlite()
    test_query_measurements()
    print("✓ All database tests passed")
