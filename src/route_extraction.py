"""
Recolector principal de datos de tráfico y clima para rutas en Malta.

Uso:
    python -m src.route_extraction                       # Una ejecución (fuente = .env DATA_SOURCE)
    python -m src.route_extraction --interval 120         # Continuo cada 120 segundos
    python -m src.route_extraction --source tomtom        # Forzar TomTom para esta ejecución
    python -m src.route_extraction --source ors           # Forzar OpenRouteService para esta ejecución
    python -m src.route_extraction --hybrid               # ORS + TomTom en paralelo, cada uno a su
                                                            # propio ritmo (--ors-interval / --tomtom-interval)
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src import config
from src.collector import DataCollector, HybridScheduler

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

# Defaults calculados para 12 rutas dentro de las cuotas gratuitas
# mensuales reales de cada API (ver PRODUCTION.md): ORS ~40,000/mes,
# TomTom ~20,000/mes. Configurables por si el número de rutas cambia.
DEFAULT_ORS_INTERVAL_MIN = 15
DEFAULT_TOMTOM_INTERVAL_MIN = 27


def main() -> None:
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(
        description="Urban Mobility Analytics - Data Collector (BD_BI_TFM)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.route_extraction                    # Run once, using DATA_SOURCE from .env
  python -m src.route_extraction --interval 120      # Run continuously every 120 seconds
  python -m src.route_extraction --source tomtom     # Force TomTom for this run
  python -m src.route_extraction --no-timescale      # Skip writing to TimescaleDB (CSV/SQLite only)
  python -m src.route_extraction --hybrid            # ORS every 15 min + TomTom every 27 min
        """,
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Interval in seconds for continuous collection (single-source mode). If not provided, runs once.",
    )
    parser.add_argument(
        "--source",
        choices=["ors", "tomtom"],
        default=None,
        help="Override DATA_SOURCE from .env for this run (ignored with --hybrid).",
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
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Run ORS and TomTom in parallel, each on its own interval, both within their free "
             "monthly quotas (see PRODUCTION.md). Ignores --source and --interval.",
    )
    parser.add_argument(
        "--ors-interval",
        type=float,
        default=DEFAULT_ORS_INTERVAL_MIN,
        help=f"Minutes between ORS cycles in --hybrid mode (default: {DEFAULT_ORS_INTERVAL_MIN}).",
    )
    parser.add_argument(
        "--tomtom-interval",
        type=float,
        default=DEFAULT_TOMTOM_INTERVAL_MIN,
        help=f"Minutes between TomTom cycles in --hybrid mode (default: {DEFAULT_TOMTOM_INTERVAL_MIN}).",
    )

    args = parser.parse_args()

    timescale_config = config.get_timescale_config()

    if args.hybrid:
        try:
            ors_key = config.get_ors_api_key()
            tomtom_key = config.get_tomtom_api_key()
            weather_api_key = config.get_openweather_api_key()
        except RuntimeError as e:
            logger.error(str(e))
            sys.exit(1)

        logger.info(
            f"API keys validated (hybrid mode: ORS every {args.ors_interval}min, "
            f"TomTom every {args.tomtom_interval}min)"
        )

        ors_collector = DataCollector(
            data_source="ors",
            traffic_api_key=ors_key,
            weather_key=weather_api_key,
            csv_path=CSV_PATH,
            db_path=DB_PATH,
            timescale_config=timescale_config,
            enable_timescale=not args.no_timescale,
            enable_medallion=not args.no_medallion,
            register_signal_handler=False,
        )
        tomtom_collector = DataCollector(
            data_source="tomtom",
            traffic_api_key=tomtom_key,
            weather_key=weather_api_key,
            csv_path=CSV_PATH,
            db_path=DB_PATH,
            timescale_config=timescale_config,
            enable_timescale=not args.no_timescale,
            enable_medallion=not args.no_medallion,
            register_signal_handler=False,
        )

        scheduler = HybridScheduler(
            ors_collector=ors_collector,
            tomtom_collector=tomtom_collector,
            ors_interval_min=args.ors_interval,
            tomtom_interval_min=args.tomtom_interval,
        )

        try:
            scheduler.run()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)
        return

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
