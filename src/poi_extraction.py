"""
Recolector de infraestructura urbana (POIs: escuelas, hospitales, centros
comerciales, negocios) vía Overpass API (OpenStreetMap).

A diferencia de route_extraction.py (tráfico/clima, ciclos cada 1-27 min),
este dato cambia con muy poca frecuencia — por defecto se refresca una vez
por semana. No requiere API key.

Uso:
    python -m src.poi_extraction                        # una sola ejecución
    python -m src.poi_extraction --interval-hours 168    # continuo, cada 7 días
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.database import RouteDatabase
from src.locations import LOCATIONS
from src.poi_client import OverpassClient

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
CSV_PATH = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"
DB_PATH = ROOT_DIR / "data" / "mobility.db"
LOG_DIR = ROOT_DIR / "logs"

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "poi_collector.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

load_dotenv(ENV_PATH)

# POIs no cambian a diario: 168h (1 semana) es más que suficiente y evita
# gastar cuota/cortesía de los servidores públicos de Overpass sin motivo.
DEFAULT_INTERVAL_HOURS = 168


def _write_heartbeat() -> None:
    """Heartbeat propio (separado del de route_extraction.py) para no
    pisar la señal de salud del collector de tráfico si ambos corren en
    contenedores distintos con healthchecks independientes."""
    try:
        heartbeat_path = LOG_DIR / "poi_heartbeat"
        heartbeat_path.write_text(datetime.now(timezone.utc).isoformat())
    except Exception as e:
        logger.warning(f"No se pudo escribir el heartbeat de POIs (no crítico): {e}")


def run_once(db: RouteDatabase, client: OverpassClient, margin_deg: float) -> int:
    """Ejecuta un ciclo de refresco: descarga POIs de Overpass y los
    guarda (upsert) en la tabla `pois` de mobility.db."""
    logger.info(f"Fetching POIs from Overpass for {len(LOCATIONS)} locations...")
    try:
        pois = client.fetch_pois(LOCATIONS, margin_deg=margin_deg)
    except Exception as e:
        logger.error(f"POI fetch failed: {e}")
        return 0

    count = db.save_pois(pois)
    logger.info(f"POI refresh complete: {count} POIs stored")
    _write_heartbeat()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Urban Mobility Analytics - POI Collector (Overpass API)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.poi_extraction                        # Run once
  python -m src.poi_extraction --interval-hours 168    # Refresh weekly, continuously
        """,
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=None,
        help=f"Hours between refresh cycles for continuous mode. If not provided, runs once. "
             f"Recommended: {DEFAULT_INTERVAL_HOURS} (weekly) since POI data changes rarely.",
    )
    parser.add_argument(
        "--margin-deg",
        type=float,
        default=0.015,
        help="Margin (degrees) added around the bounding box of all monitored locations "
             "when querying Overpass (default: 0.015, ~1.6km).",
    )

    args = parser.parse_args()

    db = RouteDatabase(CSV_PATH, DB_PATH)
    client = OverpassClient()

    try:
        if args.interval_hours:
            logger.info(f"Starting continuous POI refresh every {args.interval_hours}h")
            while True:
                run_once(db, client, args.margin_deg)
                logger.info(f"Next POI refresh in {args.interval_hours} hours...")
                time.sleep(args.interval_hours * 3600)
        else:
            logger.info("Starting single POI refresh cycle")
            run_once(db, client, args.margin_deg)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
