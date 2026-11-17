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
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

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

DEFAULT_POI_RADIUS_M = 1500  # mismo radio que ya se usa en foursquare_client.py
DEFAULT_ROUTE_HOURS = 24 * 365 * 10  # "todo el histórico" (ver analyst_dashboard.py)


@dataclass(frozen=True)
class Criterio:
    """Una dimensión del puntaje: de qué columna sale, hacia dónde es mejor y cómo se le explica al usuario.

    `invertir` dice que MENOS es mejor (competencia, tiempo de viaje). Al normalizar se le da la vuelta, así que las
    seis columnas acaban orientadas igual —más alto = mejor para el negocio— y los pesos se leen siempre como «cuánto
    me importa esto», sin convenciones de signo que recordar."""

    clave: str
    etiqueta: str  # para el deslizador, donde cabe el matiz
    corta: str  # para los encabezados de tabla, donde no
    columna: str
    invertir: bool
    peso_defecto: float
    ayuda: str


# Las tres primeras salen de la base (demografía, POIs, rutas). Las tres últimas son lentes del panorama por celda,
# agregadas por zona: existen solo si data/ml/ está disponible, y usan el perfil POR DEFECTO de la categoría.
CRITERIOS = (
    Criterio(
        "demanda",
        "Población (censo)",
        "Población",
        "demanda",
        False,
        0.30,
        "Habitantes de la zona, de las cifras oficiales ya reconciliadas a un año común.",
    ),
    Criterio(
        "competencia",
        "Evitar competencia",
        "Baja competencia",
        "competencia",
        True,
        0.25,
        "Negocios de la misma categoría a 1.500 m del centro de la zona. Menos es mejor.",
    ),
    Criterio(
        "accesibilidad",
        "Accesibilidad",
        "Accesibilidad",
        "tiempo_viaje_prom",
        True,
        0.20,
        "Tiempo de viaje medio de las rutas que tocan la zona. Menos es mejor.",
    ),
    Criterio(
        "mercado",
        "Mercado por segmento (proxy OSM)",
        "Mercado por segmento",
        "mercado_mediana",
        False,
        0.10,
        "Cuánto de lo que genera tus clientes (residentes, oficinistas, estudiantes, turistas, vida nocturna) hay en "
        "las celdas de la zona. Es un proxy de OpenStreetMap, NO el censo: mide otra cosa que la población.",
    ),
    Criterio(
        "proveedores",
        "Proveedores cerca",
        "Proveedores",
        "proveedores_mediana",
        False,
        0.10,
        "Proveedores del tipo que le importa a la categoría, en las celdas de la zona.",
    ),
    Criterio(
        "diversidad",
        "Diversidad de proveedores",
        "Diversidad",
        "diversidad_mediana",
        False,
        0.05,
        "Qué fracción de los tipos de proveedor están presentes. Distingue «muchos de lo mismo» de «surtido completo».",
    ),
)
POR_CLAVE = {c.clave: c for c in CRITERIOS}
DEFAULT_WEIGHTS = {c.clave: c.peso_defecto for c in CRITERIOS}


def criterios_disponibles(features: pd.DataFrame) -> Tuple[Criterio, ...]:
    """Los criterios que esta tabla puede puntuar: su columna existe y alguna zona tiene dato. Sin `data/ml/` quedan
    solo los tres de la base, y la pantalla ofrece esos."""
    return tuple(c for c in CRITERIOS if c.columna in features and features[c.columna].notna().any())


def pesos_por_defecto(criterios: Sequence[Criterio]) -> Dict[str, float]:
    """Los pesos de fábrica de esos criterios, renormalizados para sumar 1: si faltan las lentes del panorama, los tres
    de la base se reparten el total en la misma proporción."""
    total = sum(c.peso_defecto for c in criterios)
    if total <= 0:
        return {c.clave: 1 / len(criterios) for c in criterios} if criterios else {}
    return {c.clave: c.peso_defecto / total for c in criterios}


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
    db,
    category: str,
    radius_m: float = DEFAULT_POI_RADIUS_M,
    hours: int = DEFAULT_ROUTE_HOURS,
    medianas: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Una fila por zona con los criterios crudos (sin normalizar).

    `medianas`: las lentes del panorama ya agregadas por zona (ver panorama_view.zone_lens_medians). Sin ellas la tabla
    trae solo los tres criterios de la base y el puntaje usa esos."""
    df = zone_demand(db).join(zone_competition(db, category, radius_m)).join(zone_accessibility(db, hours))
    if medianas is not None:
        df = df.join(medianas)
    df["categoria"] = category
    return df


def score_zones(features: pd.DataFrame, weights: Optional[Dict[str, float]] = None) -> pd.DataFrame:
    """Normaliza y combina los criterios disponibles. Los de «menos es mejor» se invierten (1 - normalizado) antes de
    ponderar, así todos quedan orientados igual.

    Sin `weights` usa los de fábrica de los criterios disponibles, renormalizados: una tabla sin las lentes del
    panorama se puntúa con los tres de la base, sin que el usuario tenga que saberlo. Con `weights` explícitos, nombrar
    un criterio que esta tabla no puede puntuar es un error: callarlo daría un puntaje que no es el que se pidió.

    Añade, por cada criterio puntuado, `<clave>_norm` (0-1, ya orientado) y `aporte_<clave>` (peso × normalizado), para
    que la pantalla pueda enseñar de dónde sale cada puntaje en vez de un número suelto."""
    disponibles = criterios_disponibles(features)
    if weights is None:
        weights = pesos_por_defecto(disponibles)
    if not weights:
        raise ValueError("No hay ningún criterio con datos para puntuar las zonas")
    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise ValueError(f"Los pesos deben sumar 1.0 (suman {sum(weights.values())})")
    # Un criterio del que esta tabla no sabe nada (p. ej. accesibilidad sin rutas guardadas) se deja fuera y el resto se
    # reparte su peso: puntuarlo con 0,5 para todas las zonas sería inventarse un dato. Se anota en el log, y la
    # pantalla no llega aquí con criterios que no haya ofrecido.
    claves = {c.clave for c in disponibles}
    omitidos = sorted(k for k in weights if k not in claves)
    if omitidos:
        logger.warning("Criterios sin datos, se dejan fuera del puntaje: %s", ", ".join(omitidos))
        weights = {k: v for k, v in weights.items() if k in claves}
    if not weights:
        raise ValueError("Ningún criterio de los pedidos tiene datos en esta tabla")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("Todos los pesos son cero: no hay nada que puntuar")
    weights = {k: v / total for k, v in weights.items()}

    df = features.copy()
    df["score"] = 0.0
    for clave, peso in weights.items():
        criterio = POR_CLAVE[clave]
        norm = _normalize_minmax(df[criterio.columna])
        if criterio.invertir:
            norm = 1 - norm
        df[f"{clave}_norm"] = norm
        # «No lo sabemos» entra como neutral (0.5), no como el peor caso: una zona sin dato no debe hundirse por eso.
        df[f"aporte_{clave}"] = peso * norm.fillna(0.5)
        df["score"] = df["score"] + df[f"aporte_{clave}"]
    # Cuántos de los criterios puntuados tenían dato real para esa zona, para avisar si un puntaje se apoya en menos
    # información que otro.
    columnas = [POR_CLAVE[k].columna for k in weights]
    df["dimensiones_con_dato"] = df[columnas].notna().sum(axis=1)
    df["criterios_puntuados"] = len(weights)

    return df.sort_values("score", ascending=False)


def filter_zones(scored: pd.DataFrame, zonas: Optional[Sequence[str]]) -> pd.DataFrame:
    """Deja solo las zonas elegidas. Se aplica DESPUÉS de puntuar, a propósito: así el puntaje de cada zona sigue
    midiendo lo mismo (su posición entre las 7) y filtrar solo quita filas. Si normalizáramos sobre el subconjunto, el
    mismo sitio cambiaría de nota según con quién se le compare, que es justo lo que confunde. `None` o vacío no
    filtra."""
    if not zonas:
        return scored
    elegidas = [z for z in zonas if z in scored.index]
    return scored.loc[elegidas].sort_values("score", ascending=False)


def recommend_for_category(
    db,
    category: str,
    weights: Optional[Dict[str, float]] = None,
    radius_m: float = DEFAULT_POI_RADIUS_M,
    medianas: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Features por zona y puntaje para una categoría ya decidida (ya sea interpretada del texto o elegida por el
    usuario). `medianas`: las lentes del panorama por zona, si están disponibles."""
    features = build_zone_features(db, category, radius_m, medianas=medianas)
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
    if interpretacion.fuera is not None:
        # No es que no se entienda: se entiende y no se puede analizar. Decir «sé más específico» mandaría al usuario
        # a reformular algo que nunca va a funcionar, así que se devuelve el porqué.
        actividad = interpretacion.fuera
        raise ValueError(
            f"{actividad.nombre} es una actividad del sector {actividad.sector}, y este sistema no puede recomendar "
            f"dónde ubicarla. {actividad.motivo} Haría falta: {actividad.haria_falta}"
        )
    if category is None:
        raise ValueError(
            f"No pude identificar el tipo de negocio en: '{business_type_text}'. "
            "Prueba con una descripción más específica (ej. 'restaurante', 'farmacia', 'gimnasio')."
        )
    logger.info(f"'{business_type_text}' -> categoría: {category} ({interpretacion.fuente})")
    return recommend_for_category(db, category, weights, radius_m)
