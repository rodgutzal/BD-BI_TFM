"""Pruebas para el módulo de base de datos."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import RouteDatabase


def _pois_guardados(db):
    import sqlite3

    conn = sqlite3.connect(db.db_path)
    try:
        return dict(conn.execute("SELECT category, COUNT(*) FROM pois GROUP BY category").fetchall())
    finally:
        conn.close()


def test_los_pois_guardados_se_reetiquetan_cuando_una_categoria_se_separa_del_cajon():
    """Las categorías de la fase 3 (`belleza`, `taller`) salieron del cajón `business`, pero las filas ya guardadas
    conservaban su categoría vieja y nada las tocaría hasta la siguiente pasada completa del recolector. Mientras
    tanto `zone_competition` las buscaba por la categoría nueva y devolvía 0 en las siete zonas: la pantalla
    puntuaba una competencia inexistente. Lo encontró un code-review.

    Se puede arreglar sin red porque `subcategory` guarda el valor de la etiqueta que decidió la categoría."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = RouteDatabase(Path(tmpdir) / "t.csv", Path(tmpdir) / "t.db")
        db.init_poi_table()
        db.save_pois(
            [
                # Guardados como los dejó una recolección ANTERIOR a la fase 3.
                {
                    "osm_type": "node",
                    "osm_id": 1,
                    "category": "business",
                    "subcategory": "hairdresser",
                    "name": "Peluquería",
                    "latitude": 35.9,
                    "longitude": 14.5,
                },
                {
                    "osm_type": "node",
                    "osm_id": 2,
                    "category": "business",
                    "subcategory": "car_repair",
                    "name": "Taller",
                    "latitude": 35.9,
                    "longitude": 14.5,
                },
                {
                    "osm_type": "node",
                    "osm_id": 3,
                    "category": "business",
                    "subcategory": "clothes",
                    "name": "Ropa",
                    "latitude": 35.9,
                    "longitude": 14.5,
                },
                # Una categoría específica NO puede perder filas por coincidencia de valor bajo otra clave.
                {
                    "osm_type": "node",
                    "osm_id": 4,
                    "category": "hospital",
                    "subcategory": "pharmacy",
                    "name": "Farmacia",
                    "latitude": 35.9,
                    "longitude": 14.5,
                },
            ]
        )
        db.init_poi_table(force=True)  # la migración corre al inicializar
        assert _pois_guardados(db) == {"belleza": 1, "taller": 1, "business": 1, "hospital": 1}

        # Idempotente: una segunda pasada no mueve nada más.
        db.init_poi_table(force=True)
        assert _pois_guardados(db) == {"belleza": 1, "taller": 1, "business": 1, "hospital": 1}


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
