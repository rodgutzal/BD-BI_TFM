"""
Recolector de infraestructura urbana COMPLEMENTARIO vía Foursquare Places API
(tier Pro/gratis) — aporta una taxonomía de negocio más rica que la categoría
genérica "business" de poi_extraction.py (Overpass): restaurant, retail,
services, entertainment... Trae TODO lo que devuelve Foursquare, sin excluir
ninguna categoría: también school, health y mall, que se solapan a propósito
con Overpass para poder comparar la cobertura entre fuentes. Se guarda en la
tabla pois_foursquare, separada de `pois`.

Mismo espíritu que poi_extraction.py: este dato cambia con muy poca
frecuencia, por defecto se refresca una vez por semana.

Presupuesto de llamadas: 1 por punto de búsqueda por ciclo — 7 zonas más
puntos intermedios a lo largo de cada corredor único entre ellas (ver
src.foursquare_client.build_search_points), para no perder POIs que caen
a mitad de camino entre dos zonas. Con las rutas actuales son ~27 llamadas
por ciclo. Con refresco semanal, ~117 llamadas/mes — 23% del límite gratis
de 500/mes del tier Pro (vigente desde jun-2026), con margen amplio. Se
lleva un contador simple persistido en logs/foursquare_calls_this_month.json
para poder confirmar de un vistazo que no se acerca al límite.

Uso:
    python -m src.poi_extraction_foursquare                      # una sola ejecución
    python -m src.poi_extraction_foursquare --interval-hours 168 # continuo, cada 7 días
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.database import RouteDatabase
from src.foursquare_client import FoursquareClient, build_search_points
from src.locations import LOCATIONS, ROUTES

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
CSV_PATH = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"
DB_PATH = ROOT_DIR / "data" / "mobility.db"
LOG_DIR = ROOT_DIR / "logs"
CALL_COUNTER_PATH = LOG_DIR / "foursquare_calls_this_month.json"

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "foursquare_collector.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

load_dotenv(ENV_PATH)

# Igual que poi_extraction.py: los negocios no cambian a diario.
DEFAULT_INTERVAL_HOURS = 168

FREE_TIER_MONTHLY_LIMIT = 500  # tier Pro, vigente desde jun-2026 — verificar
# en la consola de Foursquare si cambia


def _write_heartbeat() -> None:
    try:
        heartbeat_path = LOG_DIR / "foursquare_heartbeat"
        heartbeat_path.write_text(datetime.now(timezone.utc).isoformat())
    except Exception as e:
        logger.warning(f"No se pudo escribir el heartbeat de Foursquare (no crítico): {e}")


def _bump_call_counter(n_calls: int) -> int:
    """Contador simple de llamadas del mes en curso, persistido en un JSON
    chico. Se reinicia solo al cambiar de mes. No es un rate-limiter real
    (Foursquare ya aplica el suyo) — es solo para poder ver de un vistazo,
    en los logs, si se está acercando al límite gratis."""
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    data = {"month": month_key, "calls": 0}

    if CALL_COUNTER_PATH.exists():
        try:
            existing = json.loads(CALL_COUNTER_PATH.read_text())
            if existing.get("month") == month_key:
                data = existing
        except (json.JSONDecodeError, OSError):
            pass  # contador corrupto o ilegible: se reinicia, no es critico

    data["calls"] += n_calls
    try:
        CALL_COUNTER_PATH.write_text(json.dumps(data))
    except OSError as e:
        logger.warning(f"No se pudo guardar el contador de llamadas (no crítico): {e}")

    return data["calls"]


def run_once(db: RouteDatabase, client: FoursquareClient) -> int:
    """Ejecuta un ciclo de refresco: descarga POIs de Foursquare (zonas +
    puntos intermedios a lo largo de las rutas) y los guarda (upsert) en
    pois_foursquare."""
    search_points = build_search_points(LOCATIONS, ROUTES)
    n_calls = len(search_points)
    n_extra = n_calls - len(LOCATIONS)
    logger.info(
        f"Fetching Foursquare POIs: {n_calls} llamadas "
        f"({len(LOCATIONS)} zonas + {n_extra} puntos intermedios a lo largo de rutas)..."
    )

    pois = client.fetch_pois(LOCATIONS, routes=ROUTES)

    calls_this_month = _bump_call_counter(n_calls)
    pct = 100 * calls_this_month / FREE_TIER_MONTHLY_LIMIT
    logger.info(f"Llamadas a Foursquare este mes: {calls_this_month}/{FREE_TIER_MONTHLY_LIMIT} ({pct:.0f}%)")
    if calls_this_month > FREE_TIER_MONTHLY_LIMIT:
        logger.warning(
            "Se superó el estimado del tier gratis de Foursquare este mes — "
            "revisar la consola de Foursquare para confirmar facturación."
        )

    count = db.save_pois_foursquare(pois)
    logger.info(f"Foursquare POI refresh complete: {count} POIs stored")
    _write_heartbeat()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Urban Mobility Analytics - Foursquare POI Collector (complementario a Overpass)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.poi_extraction_foursquare                        # Run once
  python -m src.poi_extraction_foursquare --interval-hours 168   # Refresh weekly, continuously
        """,
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=None,
        help=f"Hours between refresh cycles for continuous mode. If not provided, runs once. "
        f"Recommended: {DEFAULT_INTERVAL_HOURS} (weekly) since POI data changes rarely.",
    )

    args = parser.parse_args()

    api_key = os.getenv("FOURSQUARE_API_KEY")
    if not api_key:
        logger.error("FOURSQUARE_API_KEY no configurada en .env — abortando.")
        sys.exit(1)

    db = RouteDatabase(CSV_PATH, DB_PATH)
    client = FoursquareClient(api_key=api_key)

    try:
        if args.interval_hours:
            logger.info(f"Starting continuous Foursquare POI refresh every {args.interval_hours}h")
            while True:
                run_once(db, client)
                logger.info(f"Next Foursquare refresh in {args.interval_hours} hours...")
                time.sleep(args.interval_hours * 3600)
        else:
            logger.info("Starting single Foursquare POI refresh cycle")
            run_once(db, client)
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
