"""Puntuación de zonas para apoyar la decisión de dónde abrir un negocio.

Qué es y qué NO es: es un ranking por criterios explícitos (demanda,
competencia, accesibilidad), no un modelo predictivo de machine learning —
no existen datos históricos de resultados de negocio (ventas, cierres,
supervivencia) con los que entrenar algo así. Es la técnica estándar para
este tipo de problema: análisis de decisión multicriterio (MCDA), en su
variante más simple, suma ponderada sobre criterios normalizados.

Las 3 dimensiones, con lo que ya existe en el proyecto:
    - demanda:       población de la zona (zone_demographics, ya reconciliada
                      a un año común — ver src/demographics_extraction.py)
    - competencia:    cuántos POIs de la categoría elegida hay cerca de la
                      zona (tabla `pois`, Overpass)
    - accesibilidad:  qué tan bien conectada está la zona con el resto
                      (route_measurements, vía get_all_routes_statistics)

Corrección conocida: Overpass ve ~61% de los restaurantes reales que ve
Foursquare (FOOD_DRINK_OSM_COVERAGE, más abajo; medido en
tools/compare_overpass_foursquare.py, en los únicos puntos donde Foursquare
no estaba topado en 50 resultados). Para la categoría food_drink, el conteo
de competencia se corrige dividiendo por ese factor — un solo número por
zona, marcado como corregido, no como observado directo. La constante es la
única fuente del valor: si se vuelve a medir, se cambia solo allí.
"""

import logging
import math
from typing import Dict, Optional

import pandas as pd

from src.locations import LOCATIONS
from src.ml.text_hibrido import interpretar

logger = logging.getLogger(__name__)

# Medido en tools/compare_overpass_foursquare.py, sección A1 (círculos donde
# Foursquare no estaba topado en 50 resultados, único punto de comparación
# confiable) — no es una constante universal, es una observación puntual de
# Malta y puede no generalizar igual a zonas mucho más densas que donde se
# midió (cerca de Marsaskala, la menos densa de las 7).
FOOD_DRINK_OSM_COVERAGE = 0.611

DEFAULT_WEIGHTS = {"demanda": 0.40, "competencia": 0.35, "accesibilidad": 0.25}
DEFAULT_POI_RADIUS_M = 1500  # mismo radio que ya se usa en foursquare_client.py
DEFAULT_ROUTE_HOURS = 24 * 365 * 10  # "todo el histórico" (ver analyst_dashboard.py)


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (
        math.sin((lat2 - lat1) * p / 2) ** 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    )
    return 2 * 6371000 * math.asin(math.sqrt(a))


def zone_demand(db) -> pd.DataFrame:
    """Población por zona (`zone_demographics`, ya reconciliada a un año
    común — ver --reconcile en demographics_extraction.py). Una zona sin
    demografía cargada queda con NaN, no con 0 — 0 significaría "sin
    demanda", que es una afirmación distinta a "no lo sabemos"."""
    demo = db.get_demographics()
    rows = []
    for zone in LOCATIONS:
        match = demo[demo.zone_name == zone] if not demo.empty else demo
        rows.append({"zone_name": zone, "demanda": float(match.iloc[0]["population"]) if len(match) else float("nan")})
    return pd.DataFrame(rows).set_index("zone_name")


def zone_competition(db, category: str, radius_m: float = DEFAULT_POI_RADIUS_M) -> pd.DataFrame:
    """Cuántos POIs de `category` (una de las 7 de Overpass) hay dentro de
    `radius_m` del centro de cada zona. Para food_drink, corrige por
    FOOD_DRINK_OSM_COVERAGE (ver docstring del módulo) y deja constancia en
    `metodo`."""
    pois = db.get_pois(categories=[category])
    corregido = category == "food_drink"
    rows = []
    for zone, loc in LOCATIONS.items():
        if pois.empty:
            crudo = 0
        else:
            dist = pois.apply(lambda r: _haversine_m(loc.latitude, loc.longitude, r.latitude, r.longitude), axis=1)
            crudo = int((dist <= radius_m).sum())
        valor = crudo / FOOD_DRINK_OSM_COVERAGE if corregido else crudo
        rows.append(
            {
                "zone_name": zone,
                "competencia": valor,
                "competencia_cruda": crudo,
                "metodo_competencia": "corregido_por_cobertura" if corregido else "observado",
            }
        )
    return pd.DataFrame(rows).set_index("zone_name")


def zone_accessibility(db, hours: int = DEFAULT_ROUTE_HOURS) -> pd.DataFrame:
    """Tiempo de viaje promedio de las rutas que tocan cada zona (como
    origen o como destino) — un proxy de qué tan conectada está. Se usa
    get_all_routes_statistics(), que ya existe y agrega en una sola
    consulta (ver la corrección de rendimiento de los dashboards)."""
    stats = db.get_all_routes_statistics(hours=hours)
    rows = []
    for zone in LOCATIONS:
        touching = stats[(stats.origin == zone) | (stats.destination == zone)]
        rows.append(
            {
                "zone_name": zone,
                "tiempo_viaje_prom": float(touching["avg_travel_time"].mean()) if len(touching) else float("nan"),
            }
        )
    return pd.DataFrame(rows).set_index("zone_name")


def _normalize_minmax(series: pd.Series) -> pd.Series:
    """0-1. Una columna sin variación (todas las zonas iguales, o ninguna
    zona con dato) no debe dividir por 0 y tampoco debe leerse como "todas
    en el peor caso" -> se deja en 0.5 para las zonas que sí tienen valor.
    Las zonas SIN dato (NaN) se conservan como NaN aquí — se resuelven en
    score_zones(), donde "no lo sabemos" se trata como neutral (0.5), no
    como el peor resultado posible (0)."""
    lo, hi = series.min(), series.max()
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return series.apply(lambda v: 0.5 if pd.notna(v) else v)
    return (series - lo) / (hi - lo)


def build_zone_features(
    db, category: str, radius_m: float = DEFAULT_POI_RADIUS_M, hours: int = DEFAULT_ROUTE_HOURS
) -> pd.DataFrame:
    """Una fila por zona con las 3 dimensiones crudas (sin normalizar)."""
    df = zone_demand(db).join(zone_competition(db, category, radius_m)).join(zone_accessibility(db, hours))
    df["categoria"] = category
    return df


def score_zones(features: pd.DataFrame, weights: Optional[Dict[str, float]] = None) -> pd.DataFrame:
    """Normaliza y combina. Competencia y tiempo de viaje se invierten
    (1 - normalizado) antes de ponderar: en las 3 dimensiones, "más alto
    después de invertir = mejor para el negocio", así los pesos son
    siempre positivos y se leen como "qué tanto importa cada cosa", sin
    tener que recordar convenciones de signo."""
    weights = weights or DEFAULT_WEIGHTS
    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise ValueError(f"Los pesos deben sumar 1.0 (suman {sum(weights.values())})")

    df = features.copy()
    df["demanda_norm"] = _normalize_minmax(df["demanda"])
    df["competencia_norm"] = 1 - _normalize_minmax(df["competencia"])
    df["accesibilidad_norm"] = 1 - _normalize_minmax(df["tiempo_viaje_prom"])

    df["score"] = (
        weights["demanda"] * df["demanda_norm"].fillna(0.5)
        + weights["competencia"] * df["competencia_norm"].fillna(0.5)
        + weights["accesibilidad"] * df["accesibilidad_norm"].fillna(0.5)
    )
    # Cuántas de las 3 dimensiones tenían dato real (no NaN) para esa zona,
    # para poder avisar si un score se apoya en menos información que otro.
    df["dimensiones_con_dato"] = df[["demanda", "competencia", "tiempo_viaje_prom"]].notna().sum(axis=1)

    return df.sort_values("score", ascending=False)


def recommend_for_category(
    db, category: str, weights: Optional[Dict[str, float]] = None, radius_m: float = DEFAULT_POI_RADIUS_M
) -> pd.DataFrame:
    """Features por zona y puntaje para una categoría ya decidida (ya sea interpretada del texto o elegida por el
    usuario)."""
    features = build_zone_features(db, category, radius_m)
    if features["demanda"].isna().all():
        logger.warning("Ninguna zona tiene demografía cargada — el score de demanda será neutral (0.5) para todas")
    return score_zones(features, weights)


def recommend_locations(
    db,
    business_type_text: str,
    weights: Optional[Dict[str, float]] = None,
    radius_m: float = DEFAULT_POI_RADIUS_M,
    modelo_texto=None,
) -> pd.DataFrame:
    """Punto de entrada de extremo a extremo: texto libre -> categoría ->
    features por zona -> puntaje. Lanza ValueError si el texto no se pudo
    interpretar (no adivina una categoría al azar).

    La categoría sale del sistema híbrido de src/ml/text_hibrido.py: palabras clave primero y, solo si no
    reconocen el negocio, el clasificador entrenado `modelo_texto` (si se da; sin él, solo palabras clave)."""
    interpretacion = interpretar(business_type_text, modelo_texto)
    category = interpretacion.categoria
    if category is None:
        raise ValueError(
            f"No pude identificar el tipo de negocio en: '{business_type_text}'. "
            "Prueba con una descripción más específica (ej. 'restaurante', 'farmacia', 'gimnasio')."
        )
    logger.info(f"'{business_type_text}' -> categoría: {category} ({interpretacion.fuente})")
    return recommend_for_category(db, category, weights, radius_m)
