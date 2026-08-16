"""Script de migración de datos CSV históricos a SQLite (esquema unificado)."""

import logging
import sys
from pathlib import Path

import pandas as pd

from src.database import RouteDatabase

logger = logging.getLogger(__name__)


def migrate_csv_to_sqlite(csv_path: Path, db_path: Path, dry_run: bool = False) -> int:
    """
    Migra registros del CSV histórico (esquema unificado BD_BI_TFM2) a SQLite.

    Args:
        csv_path: Ruta al archivo CSV
        db_path: Ruta a la base de datos SQLite
        dry_run: Si True, muestra lo que haría sin escribir

    Returns:
        Número de registros importados exitosamente
    """
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        return 0

    logger.info(f"Reading CSV: {csv_path}")

    try:
        df = pd.read_csv(csv_path, on_bad_lines='skip', engine='python')
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        return 0

    if df.empty:
        logger.warning("CSV is empty, nothing to migrate")
        return 0

    logger.info(f"CSV contains {len(df)} records")

    required_columns = ["timestamp", "origin", "destination"]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        logger.error(f"Missing required columns: {missing}")
        return 0

    numeric_cols = [
        "distance_km", "travel_time_min", "no_traffic_time_min",
        "traffic_delay_min", "traffic_length_km", "average_speed_kmh",
        "origin_temperature", "origin_feels_like", "origin_humidity",
        "destination_temperature", "destination_feels_like", "destination_humidity",
    ]
    text_cols = [
        "data_source", "departure_time", "arrival_time", "origin_weather",
        "destination_weather", "mobility_level", "polyline",
    ]

    records = []
    for idx, row in df.iterrows():
        record = {"timestamp": row.get("timestamp"), "origin": row.get("origin"),
                   "destination": row.get("destination")}

        for col in numeric_cols:
            record[col] = pd.to_numeric(row.get(col), errors="coerce") if col in df.columns else None

        for col in text_cols:
            record[col] = row.get(col) if col in df.columns else None

        record.setdefault("data_source", "unknown")
        if not record.get("data_source") or pd.isna(record.get("data_source")):
            record["data_source"] = "unknown"

        if pd.isna(record["timestamp"]) or pd.isna(record["origin"]) or pd.isna(record["destination"]):
            logger.warning(f"Skipping record {idx + 1} - missing required fields")
            continue

        records.append(record)

    logger.info(f"Prepared {len(records)} valid records for import")

    if dry_run:
        logger.info("[DRY RUN] Would import the following:")
        logger.info(f"  - Total records: {len(records)}")
        if records:
            logger.info(f"  - Timestamp range: {records[0]['timestamp']} to {records[-1]['timestamp']}")
        return len(records)

    db = RouteDatabase(csv_path, db_path)
    db.init_sqlite()

    logger.info("Importing records to SQLite...")
    db.save_records_to_sqlite(records)

    verify_count = 0
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM route_measurements")
        verify_count = cursor.fetchone()[0]
        conn.close()
    except Exception as e:
        logger.warning(f"Could not verify import count: {e}")

    logger.info(f"✓ Migration complete. Total records in SQLite: {verify_count}")
    return len(records)


def main():
    """Punto de entrada del script de migración."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate CSV historical data to SQLite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.migration                    # Migrate with confirmation
  python -m src.migration --dry-run          # Show what would be imported
  python -m src.migration --skip-confirmation # Import without asking
        """,
    )

    parser.add_argument("--dry-run", action="store_true",
                         help="Show what would be imported without actually importing")
    parser.add_argument("--skip-confirmation", action="store_true",
                         help="Skip confirmation prompt")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger(__name__)

    root_dir = Path(__file__).resolve().parents[1]
    csv_path = root_dir / "data" / "raw" / "route_weather_data.csv"
    db_path = root_dir / "data" / "mobility.db"

    logger.info("Urban Mobility Analytics - Data Migration")
    logger.info(f"CSV: {csv_path}")
    logger.info(f"DB:  {db_path}")
    logger.info("")

    if args.dry_run:
        logger.info("DRY RUN MODE - No data will be written")
        logger.info("")
        count = migrate_csv_to_sqlite(csv_path, db_path, dry_run=True)
        logger.info(f"Preview: {count} records would be imported")
        return 0

    if not args.skip_confirmation:
        logger.warning("This will import all CSV records to SQLite.")
        response = input("Continue? (yes/no): ").strip().lower()
        if response not in ("yes", "y"):
            logger.info("Migration cancelled")
            return 0

    try:
        count = migrate_csv_to_sqlite(csv_path, db_path, dry_run=False)
        if count > 0:
            logger.info(f"Successfully imported {count} records")
            return 0
        else:
            logger.error("Migration failed - no records imported")
            return 1
    except Exception as e:
        logger.error(f"Fatal error during migration: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
