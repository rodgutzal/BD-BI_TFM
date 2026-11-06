"""
Recolector de demografía por zona vía Google Data Commons — COMPLEMENTARIO,
pensado desde el inicio para transicionar a otras ciudades: agrega el
nombre del lugar a `src/locations.py` y el resto del pipeline funciona
igual, sin tocar código, porque la resolución de lugar -> DCID se hace por
nombre en tiempo de ejecución, no está hardcodeada.

A diferencia de poi_extraction.py/poi_extraction_foursquare.py (semanal),
la demografía cambia MUY poco (una estimación de población nueva, cuando
mucho, una vez al año) — no tiene sentido un refresco semanal. Se usa un
intervalo por defecto mucho más largo, y en la práctica lo normal es
correrlo a mano cuando haga falta, no como servicio siempre encendido.

Uso:
    python -m src.demographics_extraction                        # una sola corrida
    python -m src.demographics_extraction --interval-hours 2160  # continuo, cada 90 días
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from src.database import RouteDatabase
from src.demographics_client import DemographicsClient
from src.locations import LOCATIONS

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
        logging.FileHandler(LOG_DIR / "demographics_collector.log"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

load_dotenv(ENV_PATH)

# La población no cambia semana a semana como el tráfico o incluso los
# POIs — este valor es solo una referencia para el modo --interval-hours
# continuo; lo normal es correr este script a mano de vez en cuando.
DEFAULT_INTERVAL_HOURS = 24 * 90  # 90 días


def ensure_dcids(db: RouteDatabase, client: DemographicsClient) -> dict:
    """Devuelve {zona: dcid} para todas las zonas de LOCATIONS. Las que no
    tienen dcid cacheado en la base se resuelven por nombre (una llamada API
    cada una) y se guardan de inmediato — así, si el proceso se interrumpe a
    mitad de camino, lo ya resuelto no se pierde."""
    existing = db.get_demographics()
    cached_dcids = dict(zip(existing["zone_name"], existing["dcid"])) if not existing.empty else {}

    all_dcids: dict = {}
    for zone_name in LOCATIONS:
        dcid = cached_dcids.get(zone_name)
        if dcid and str(dcid) != "nan":
            all_dcids[zone_name] = dcid
            continue

        logger.info(f"Resolviendo DCID para zona nueva: {zone_name}")
        dcid = client.resolve_dcid(zone_name)
        if dcid:
            logger.info(f"  -> {zone_name}: {dcid}")
            db.save_demographics([{"zone_name": zone_name, "dcid": dcid}])
            all_dcids[zone_name] = dcid
        else:
            logger.warning(f"  -> No se encontró DCID para '{zone_name}' — se omite esta zona")

    return all_dcids


def run_once(db: RouteDatabase, client: DemographicsClient) -> int:
    """Refresco normal: resuelve DCIDs pendientes y guarda la población más
    reciente de cada zona en una sola llamada."""
    all_dcids = ensure_dcids(db, client)

    if not all_dcids:
        logger.warning("Ninguna zona tiene DCID resuelto todavía — nada que consultar")
        return 0

    logger.info(f"Consultando población para {len(all_dcids)} zonas...")
    populations = client.fetch_population(all_dcids)

    records = [
        {
            "zone_name": zone_name,
            "population": data["population"],
            "observation_date": data["date"],
            "source": "datacommons",
        }
        for zone_name, data in populations.items()
    ]

    if not records:
        logger.warning("Data Commons no devolvió observaciones de población para ninguna zona")
        return 0

    count = db.save_demographics(records)
    for r in records:
        dc_name = populations[r["zone_name"]].get("dc_name", "")
        logger.info(
            f"  {r['zone_name']}: {r['population']:,} hab. ({r['observation_date']})"
            + (f" [Data Commons lo llama: {dc_name}]" if dc_name else "")
        )
    logger.info(f"Demographics refresh complete: {count} zonas actualizadas")
    return count


def summarize_history(history: dict, zones: list) -> dict:
    """Años con al menos una observación por zona, y años comunes a TODAS.
    Una zona sin ninguna observación cuenta con conjunto vacío (=> no hay
    año común posible, y queda a la vista en vez de ocultarse)."""
    years_by_zone = {
        z: {r["year"] for r in history.get(z, []) if r["year"] is not None}
        for z in zones
    }
    common = sorted(set.intersection(*years_by_zone.values())) if years_by_zone else []
    return {"years_by_zone": years_by_zone, "common_years": common}


def run_diagnose(db: RouteDatabase, client: DemographicsClient, country_dcid: str) -> None:
    """Muestra QUÉ fechas de población existen realmente en Data Commons para
    cada zona (y para el país, como referencia), y las guarda en
    zone_population_history. No modifica zone_demographics: es para decidir
    con datos reales cómo unificar el año de referencia."""
    dcids = ensure_dcids(db, client)
    if not dcids:
        logger.warning("Ninguna zona tiene DCID resuelto — nada que diagnosticar")
        return

    logger.info(f"Diagnóstico: pidiendo la serie COMPLETA de población de {len(dcids)} zonas...")
    history = client.fetch_population_history(dcids)
    if not history:
        logger.warning("Data Commons no devolvió series de población (revisa el error anterior en el log)")
        return

    records = []
    for zone, rows in history.items():
        logger.info(f"{zone} ({dcids[zone]}): {len(rows)} observaciones")
        for r in rows:
            logger.info(f"    {r['date']:<12} {r['population']:>9,}  [{r['source'] or 'fuente n/d'}]")
            records.append({
                "zone_name": zone, "observation_date": r["date"], "year": r["year"],
                "population": r["population"], "source": r["source"],
            })
    db.save_population_history(records)

    summary = summarize_history(history, list(dcids))
    logger.info("Años disponibles por zona:")
    for zone, years in summary["years_by_zone"].items():
        logger.info(f"    {zone:<12} {sorted(years) if years else 'SIN DATOS'}")
    if summary["common_years"]:
        logger.info(f"Años comunes a las {len(dcids)} zonas: {summary['common_years']}  -> se puede unificar sin estimar")
    else:
        logger.info(f"NO hay ningún año común a las {len(dcids)} zonas -> hará falta estimar o cargar una fuente adicional")

    if country_dcid:
        national = client.fetch_population_history({"país": country_dcid}).get("país", [])
        if national:
            years = sorted({r["year"] for r in national if r["year"] is not None})
            logger.info(f"Referencia nacional ({country_dcid}): {len(national)} observaciones, años {years[0]}-{years[-1]}"
                        f" ({len(years)} años distintos)")
        else:
            logger.info(f"Referencia nacional ({country_dcid}): sin datos")


def latest_observation_per_zone(history: dict) -> dict:
    """{zona: fila más reciente} usando el AÑO más alto de la serie completa
    de cada zona (no `date="latest"` de la API: se comprobó en producción que
    puede devolver un valor menos reciente que otro disponible en la misma
    serie completa — para Valletta, "latest" dio 2014 mientras que la propia
    serie ya traía 2021)."""
    return {
        zone: max(rows, key=lambda r: (r["year"] is not None, r["year"] or -1, r["date"]))
        for zone, rows in history.items() if rows
    }


def reconcile_to_common_year(zone_latest: dict, national_history: list, target_year: int = None) -> tuple:
    """Proyecta el dato más reciente de cada zona a un año común usando la
    tasa de crecimiento NACIONAL entre el año de esa zona y `target_year`
    (por defecto, el año más reciente de la serie nacional).

    Por qué así: las 7 zonas casi nunca comparten año de observación (ver
    --diagnose). Forzarlas a la fecha común MÁS VIEJA es exacto pero
    desactualiza a todas; usar cada quien su propio último dato real y
    proyectar SOLO la diferencia de años con la tasa del país es el balance
    entre "lo más reciente posible" y no inventar una tendencia propia que no
    se puede observar con 1-2 puntos por zona. Un dato ya igual o más nuevo
    que target_year no se toca (method="observed"); solo se proyecta lo que
    quedó atrás (method="national_growth_adjustment").

    Devuelve (registros_para_guardar, target_year_usado).
    """
    nat_by_year = {r["year"]: r["population"] for r in national_history if r["year"] is not None}
    if target_year is None:
        target_year = max(nat_by_year) if nat_by_year else None
    if target_year is None:
        logger.warning("Sin serie nacional utilizable: no se puede reconciliar a un año común")
        return [], None

    records = []
    for zone, row in zone_latest.items():
        anchor_year, anchor_pop = row["year"], row["population"]
        if anchor_year is None:
            logger.warning(f"{zone}: su observación más reciente no tiene año identificable — se omite")
            continue

        if anchor_year >= target_year:
            projected, method = anchor_pop, "observed"
        elif anchor_year in nat_by_year and target_year in nat_by_year:
            factor = nat_by_year[target_year] / nat_by_year[anchor_year]
            projected, method = round(anchor_pop * factor), "national_growth_adjustment"
        else:
            logger.warning(f"{zone}: falta la tasa nacional para {anchor_year} o {target_year} — se omite")
            continue

        records.append({
            "zone_name": zone, "population": projected, "observation_date": str(target_year),
            "source": row["source"], "basis_year": anchor_year, "basis_population": anchor_pop,
            "method": method,
        })
        tag = "(observado, sin ajustar)" if method == "observed" else f"(ancla real {anchor_year}: {anchor_pop:,})"
        logger.info(f"    {zone:<12} {target_year}: {projected:>9,} hab.  {tag}")
    return records, target_year


def run_reconcile(db: RouteDatabase, client: DemographicsClient, country_dcid: str, target_year) -> None:
    """Actualiza zone_demographics con la población de cada zona llevada al
    año más reciente posible (ver reconcile_to_common_year). Requiere haber
    corrido antes --diagnose (usa zone_population_history, no vuelve a
    resolver DCIDs)."""
    hist_df = db.get_population_history()
    if hist_df.empty:
        logger.error("zone_population_history está vacía — corre primero --diagnose")
        return

    # zone_population_history usa la columna `observation_date`; las funciones
    # de reconciliado esperan la forma que devuelve fetch_population_history
    # (clave `date`) — se renombra al leer, en vez de duplicar la clave en el
    # esquema de la base.
    history = {
        zone: g.rename(columns={"observation_date": "date"})[["date", "year", "population", "source"]].to_dict("records")
        for zone, g in hist_df.groupby("zone_name")
    }
    zone_latest = latest_observation_per_zone({z: history.get(z, []) for z in LOCATIONS})
    missing = set(LOCATIONS) - set(zone_latest)
    if missing:
        logger.warning(f"Sin ninguna observación en el historial para: {sorted(missing)} — corre --diagnose de nuevo")

    logger.info(f"Pidiendo la serie nacional ({country_dcid}) para calcular la tasa de crecimiento...")
    national_history = client.fetch_population_history({"__país__": country_dcid}).get("__país__", [])
    if not national_history:
        logger.error("Sin serie nacional — no se puede reconciliar (¿DCID de país correcto?)")
        return

    records, used_year = reconcile_to_common_year(zone_latest, national_history, target_year)
    if not records:
        logger.error("No se generó ningún registro reconciliado")
        return

    logger.info(f"Año común usado: {used_year}")
    db.save_demographics(records)
    logger.info(f"zone_demographics actualizada: {len(records)} zonas")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Urban Mobility Analytics - Demographics Collector (Google Data Commons)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.demographics_extraction                         # Run once
  python -m src.demographics_extraction --interval-hours 2160   # Refresh every 90 days, continuously
  python -m src.demographics_extraction --diagnose              # Ver qué fechas de población existen por zona
  python -m src.demographics_extraction --reconcile             # Llevar cada zona a un año común (recomendado)
        """,
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=None,
        help=f"Hours between refresh cycles for continuous mode. If not provided, runs once. "
             f"Recommended: {DEFAULT_INTERVAL_HOURS} (90 días) o más — la población cambia muy poco.",
    )

    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="Lleva la población de cada zona a un año común (el más reciente de la serie nacional, o "
             "--target-year) usando la tasa de crecimiento nacional sobre el dato propio más reciente de "
             "cada zona. Requiere haber corrido --diagnose antes.",
    )
    parser.add_argument(
        "--target-year", type=int, default=None,
        help="Año al que reconciliar (default: el más reciente de la serie nacional).",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Muestra qué fechas de población existen en Data Commons para cada zona "
             "(y guarda la serie en zone_population_history) sin tocar zone_demographics.",
    )
    parser.add_argument(
        "--country",
        default="country/MLT",
        help="DCID del país, solo para la referencia nacional del diagnóstico (default: country/MLT).",
    )

    args = parser.parse_args()

    api_key = os.getenv("DATACOMMONS_API_KEY")
    if not api_key:
        logger.error("DATACOMMONS_API_KEY no configurada en .env — abortando.")
        sys.exit(1)

    db = RouteDatabase(CSV_PATH, DB_PATH)
    client = DemographicsClient(api_key=api_key)

    try:
        if args.diagnose:
            run_diagnose(db, client, args.country)
        elif args.reconcile:
            run_reconcile(db, client, args.country, args.target_year)
        elif args.interval_hours:
            logger.info(f"Starting continuous demographics refresh every {args.interval_hours}h")
            while True:
                run_once(db, client)
                logger.info(f"Next demographics refresh in {args.interval_hours} hours...")
                time.sleep(args.interval_hours * 3600)
        else:
            logger.info("Starting single demographics refresh cycle")
            run_once(db, client)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
