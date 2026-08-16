"""
Recolector principal de datos de tráfico y clima para rutas en Malta.

Uso:
    python -m src.route_extraction                       # Una ejecución (fuente = .env DATA_SOURCE)
    python -m src.route_extraction --interval 120         # Continuo cada 120 segundos
    python -m src.route_extraction --source tomtom        # Forzar TomTom para esta ejecución
    python -m src.route_extraction --source ors           # Forzar OpenRouteService para esta ejecución
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src import config
from src.collector import DataCollector

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
        logging.FileHandler(LOG_DIR / "collector.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

load_dotenv(ENV_PATH)


def main() -> None:
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(
        description="Urban Mobility Analytics - Data Collector (BD_BI_TFM2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.route_extraction                    # Run once, using DATA_SOURCE from .env
  python -m src.route_extraction --interval 120      # Run continuously every 120 seconds
  python -m src.route_extraction --source tomtom     # Force TomTom for this run
  python -m src.route_extraction --no-timescale      # Skip writing to TimescaleDB (CSV/SQLite only)
        """,
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Interval in seconds for continuous collection. If not provided, runs once.",
    )
    parser.add_argument(
        "--source",
        choices=["ors", "tomtom"],
        default=None,
        help="Override DATA_SOURCE from .env for this run.",
    )
    parser.add_argument(
        "--no-timescale",
        action="store_true",
        help="Do not write to TimescaleDB, only CSV + SQLite.",
    )
    parser.add_argument(
        "--no-medallion",
        action="store_true",
        help="Do not run the Bronze/Silver/Gold pipeline (Executive dashboard KPIs won't update).",
    )

    args = parser.parse_args()

    data_source = args.source or config.get_data_source()

    try:
        traffic_api_key = (
            config.get_tomtom_api_key() if data_source == "tomtom" else config.get_ors_api_key()
        )
        weather_api_key = config.get_openweather_api_key()
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info(f"API keys validated (data_source={data_source})")

    timescale_config = config.get_timescale_config()

    collector = DataCollector(
        data_source=data_source,
        traffic_api_key=traffic_api_key,
        weather_key=weather_api_key,
        csv_path=CSV_PATH,
        db_path=DB_PATH,
        timescale_config=timescale_config,
        enable_timescale=not args.no_timescale,
        enable_medallion=not args.no_medallion,
    )

    try:
        if args.interval:
            if args.interval < 30:
                logger.warning("Interval is very short. Minimum recommended is 30 seconds.")
            logger.info(f"Starting continuous collection every {args.interval} seconds")
            collector.run_continuous(args.interval)
        else:
            logger.info("Starting single collection cycle")
            collector.run_once()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
