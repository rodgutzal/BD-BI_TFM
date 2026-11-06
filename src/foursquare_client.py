"""Cliente de Foursquare Places API — fuente COMPLEMENTARIA a poi_client.py
(Overpass/OpenStreetMap), no un reemplazo.

Por qué existe si ya tenemos Overpass: Overpass agrupa cualquier tienda u
oficina bajo una sola categoría genérica "business" (viene de los tags
OSM shop=*/office=*, que no distinguen tipo de negocio). Foursquare tiene
una taxonomía de categorías mucho más rica (1500+ categorías) que sí
permite, por ejemplo, separar restaurantes de retail de servicios.

Trae TODOS los POIs que devuelva Foursquare dentro del radio de cada zona,
sin excluir ni descartar nada por categoría (a propósito, para poder ver y
comparar la cobertura completa de Foursquare, incluida la que se solape con
Overpass) — la categorización por baldes (`_CATEGORY_RULES`) es solo para
poder colorear/agrupar en el mapa, con "other" como respaldo para lo que no
matchea ningún balde específico; el nombre de categoría original de
Foursquare se conserva siempre en `subcategory`.

Tier usado: Pro (gratis, 500 llamadas/mes desde jun-2026). Solo se piden
campos Core/Pro (nombre, categoría, ubicación) — nunca campos Premium
(horarios, popularidad, rating, fotos), que tienen costo desde la primera
llamada.

Referencia: https://docs.foursquare.com/fsq-developers-places/reference/place-search
(API nueva, post-migración de v3 en mayo 2026 — base_url y headers
verificados en esa documentación, no en la v3 legacy ya deprecada).
"""

import logging
import math
import re
from typing import Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.locations import Location

logger = logging.getLogger(__name__)

BASE_URL = "https://places-api.foursquare.com"
API_VERSION = "2025-06-17"  # header obligatorio; fija la forma de la respuesta

# Distancia entre puntos de búsqueda intermedios a lo largo de un corredor,
# en km. Igual al radio de búsqueda (1.5km): cada punto nuevo se solapa ~50%
# con el círculo anterior, dando buena densidad sin puntos redundantes.
# Ajustado de 2.5km a 1.5km para más cobertura (~117 llamadas/mes con las
# rutas actuales — 23% del límite gratis de 500/mes, con margen amplio).
DEFAULT_CORRIDOR_SPACING_KM = 1.5


def build_search_points(
    locations: Dict[str, Location],
    routes: Optional[List[Tuple[str, str]]] = None,
    spacing_km: float = DEFAULT_CORRIDOR_SPACING_KM,
) -> Dict[str, Location]:
    """Zonas + puntos intermedios interpolados a lo largo de cada corredor
    ÚNICO entre ellas (sin duplicar reversas — Valletta↔Birkirkara y
    Birkirkara↔Valletta son el mismo tramo físico, no se buscan dos veces).

    Por qué existe: buscar solo en un radio de 1.5km alrededor de cada una
    de las 7 zonas deja sin cubrir el tramo intermedio de rutas largas (ej.
    Msida↔Marsaskala, ~9.5km) — un negocio a mitad de camino puede estar a
    más de 1.5km de AMBOS extremos y nunca aparecer. Se interpolan puntos
    en línea recta entre origen y destino (no la carretera real, que
    requeriría una llamada aparte a ORS/TomTom) — suficiente aproximación
    dada la escala de estas rutas urbanas cortas.

    Expuesta aparte de FoursquareClient.fetch_pois() para que quien
    orquesta (poi_extraction_foursquare.py) pueda saber cuántas llamadas
    HTTP se van a hacer antes de hacerlas (para el contador de presupuesto
    mensual), sin duplicar esta lógica en dos lugares.
    """
    search_points: Dict[str, Location] = dict(locations)
    if not routes:
        return search_points

    seen_corridors = set()
    for origin, dest in routes:
        corridor_key = frozenset([origin, dest])
        if corridor_key in seen_corridors:
            continue
        if origin not in locations or dest not in locations:
            continue
        seen_corridors.add(corridor_key)

        o, d = locations[origin], locations[dest]
        # Aproximación plana (grados * 111 km/grado): suficiente a la escala
        # de Malta, donde ningún corredor supera ~10km.
        dist_km = math.dist([o.latitude, o.longitude], [d.latitude, d.longitude]) * 111
        n_points = max(0, math.ceil(dist_km / spacing_km) - 1)

        for i in range(1, n_points + 1):
            t = i / (n_points + 1)
            lat = o.latitude + (d.latitude - o.latitude) * t
            lon = o.longitude + (d.longitude - o.longitude) * t
            point_name = f"{origin}↔{dest} km{i}"
            search_points[point_name] = Location(point_name, lat, lon)

    return search_points

# Categorización por NOMBRE de categoría devuelto (no por ID numérico): los
# IDs de la taxonomía de Foursquare son ~1500 y cambian de vez en cuando;
# emparejar por palabra completa es más simple de mantener y de auditar a
# ojo, al costo de ser algo menos preciso que un mapeo id-a-id exacto.
# Nada se descarta: lo que no matchea ninguna regla cae en "other" (ver
# _categorize) — que queda reservado a lugares NO comerciales (iglesias,
# parques, plazas, playas, edificios públicos), no a comercios sin clasificar.
#
# EL ORDEN IMPORTA: se evalúa de arriba hacia abajo y gana la primera regla
# que matchea. Por eso "retail" aparece dos veces:
#   - primero solo con la palabra "retail" ("Food and Beverage Retail" es una
#     tienda, no un restaurante, aunque contenga "food"),
#   - y al final con las palabras genéricas (store/shop/market...), para que
#     "Coffee Shop" o "Dessert Shop" ya hayan sido tomados como restaurant
#     antes de que "shop" los mande a retail, y para que "Department Store"
#     llegue al balde "mall" antes que al "store" genérico.
# Ajustado tras revisar nombres reales devueltos por Foursquare para Malta:
# la primera versión dejaba en "other" a Pizzeria, Bistro, Steakhouse,
# Burger Joint, Trattoria, etc. (~la mitad de "other" era comida).
_CATEGORY_RULES: List[Tuple[str, tuple]] = [
    ("retail", ("retail",)),
    ("restaurant", (
        "restaurant", "café", "cafe", "cafeteria", "coffee", "bar", "pub", "lounge",
        "speakeasy", "beer garden", "brewery", "winery", "gastropub", "bakery", "bistro",
        "pizzeria", "trattoria", "taverna", "steakhouse", "diner", "deli", "eatery",
        "joint", "grill", "sandwich", "burger", "snack", "breakfast", "creperie",
        "dessert", "ice cream", "gelato", "pastry", "pie", "donut", "smoothie", "juice",
        "food court", "food truck", "food stand", "fast food",
    )),
    ("entertainment", (
        "theater", "theatre", "cinema", "museum", "gym", "fitness", "nightlife",
        "night club", "nightclub", "casino", "betting", "arcade", "stadium",
        "art gallery", "concert", "jazz", "swimming pool", "sports and recreation",
        "entertainment",
    )),
    ("services", (
        "bank", "salon", "spa", "barber", "hair", "laundry", "insurance", "real estate",
        "financial", "atm", "post office", "veterinarian",
    )),
    ("health", ("hospital", "clinic", "doctor", "pharmacy", "drugstore", "medical", "emergency room")),
    ("school", ("school", "college", "university", "kindergarten", "elementary")),
    ("mall", ("shopping mall", "department store")),
    ("retail", ("store", "shop", "market", "boutique", "supermarket", "grocery", "butcher", "dealership")),
]


class FoursquareClient:
    """Cliente HTTP para Foursquare Places API (tier Pro/gratis) con
    reintentos. A diferencia de Overpass (una sola query con bbox que ya
    cubre toda la zona monitorizada), Foursquare Place Search toma un único
    punto (ll) + radio — hace falta una llamada por punto de búsqueda.
    Con las 7 zonas más los puntos intermedios de build_search_points()
    (~20 con las rutas actuales), son ~27 llamadas por ciclo de refresco,
    ~117/mes con refresco semanal — bien por debajo del límite gratis de
    500/mes del tier Pro."""

    def __init__(
        self,
        api_key: str,
        timeout: int = 30,
        max_retries: int = 2,
        radius_m: int = 1500,
        results_per_zone: int = 50,
    ):
        if not api_key:
            raise ValueError("FOURSQUARE_API_KEY vacía o no configurada")
        self.api_key = api_key
        self.timeout = timeout
        self.radius_m = radius_m
        # 50 es el máximo por página de Foursquare. Deliberadamente NO se
        # sigue paginación (aunque haya más resultados) para que el
        # presupuesto de llamadas por refresco sea predecible: siempre
        # exactamente 1 llamada por zona, nunca más.
        self.results_per_zone = results_per_zone
        self.session = self._create_session(max_retries)

    def _create_session(self, max_retries: int) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        session.mount("https://", HTTPAdapter(max_retries=retry_strategy))
        session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "X-Places-Api-Version": API_VERSION,
            "Accept": "application/json",
        })
        return session

    @staticmethod
    def _categorize(categories: List[dict]) -> str:
        """Mapea las categorías devueltas por Foursquare a uno de nuestros
        baldes (solo para colorear/agrupar en el mapa). Nunca descarta un
        POI: si no matchea ningún balde específico, devuelve "other" — el
        nombre de categoría real de Foursquare no se pierde, queda en
        `subcategory`.

        Usa `\\b` (límite de palabra) en vez de un simple `in`: un
        substring como "bar" adentro de "Barbershop" NO debe matchear la
        keyword "bar" (bares/pubs) — un `in` ingenuo sí lo haría, y
        terminaría categorizando una barbería como restaurante.
        """
        names = [c.get("name", "").lower() for c in (categories or [])]
        joined = " ".join(names)

        def _has_any(keywords: tuple) -> bool:
            return any(re.search(rf"\b{re.escape(kw)}\b", joined) for kw in keywords)

        for bucket, keywords in _CATEGORY_RULES:
            if _has_any(keywords):
                return bucket
        return "other"

    def _parse_results(self, results: List[dict]) -> List[dict]:
        pois = []
        for place in results:
            category = self._categorize(place.get("categories", []))

            # La documentación de Foursquare muestra dos formas de
            # respuesta segun la version/endpoint (fsq_place_id + lat/lon
            # planos en la API Places Pro nueva; fsq_id + geocodes.main en
            # paginas mas viejas de la misma documentacion). Se soportan
            # ambas variantes en vez de asumir una sola, para no romper si
            # la cuenta responde con el formato que no se probo primero.
            fsq_id = place.get("fsq_place_id") or place.get("fsq_id")
            if not fsq_id:
                continue

            lat = place.get("latitude")
            lon = place.get("longitude")
            if lat is None or lon is None:
                geocodes = place.get("geocodes", {}).get("main", {})
                lat, lon = geocodes.get("latitude"), geocodes.get("longitude")
            if lat is None or lon is None:
                continue

            category_names = [c.get("name") for c in place.get("categories", []) if c.get("name")]

            pois.append({
                "fsq_place_id": fsq_id,
                "category": category,
                "subcategory": category_names[0] if category_names else None,
                "name": place.get("name") or f"{category.capitalize()} (sin nombre)",
                "latitude": lat,
                "longitude": lon,
            })
        return pois

    def fetch_pois_for_zone(self, location: Location) -> List[dict]:
        """Una sola llamada a Places Search alrededor de `location`."""
        params = {
            "ll": f"{location.latitude},{location.longitude}",
            "radius": self.radius_m,
            "limit": self.results_per_zone,
        }
        response = self.session.get(
            f"{BASE_URL}/places/search", params=params, timeout=self.timeout
        )
        response.raise_for_status()
        payload = response.json()
        raw_results = payload.get("results", [])

        # Diagnóstico: cuántos resultados CRUDOS llegaron (antes de
        # categorizar) y qué nombres de categoría trae Foursquare de
        # verdad para esta zona. Si `raw_results` ya viene con pocas
        # categorías distintas, el problema es de cobertura de datos de
        # Foursquare para esta zona — no de la categorización de este
        # cliente. Si en cambio `raw_results` trae categorías variadas
        # pero el resultado final (tras _parse_results) queda concentrado
        # en pocos baldes, el problema sí estaría en _CATEGORY_RULES.
        raw_category_names = sorted({
            c.get("name", "?")
            for place in raw_results
            for c in place.get("categories", [])
        })
        logger.info(
            f"[{location.name}] Foursquare devolvió {len(raw_results)} resultados crudos, "
            f"con {len(raw_category_names)} nombres de categoría distintos: {raw_category_names}"
        )

        return self._parse_results(raw_results)

    def fetch_pois(
        self,
        locations: Dict[str, Location],
        routes: Optional[List[Tuple[str, str]]] = None,
    ) -> List[dict]:
        """Recorre las 7 zonas MÁS los puntos intermedios a lo largo de cada
        corredor único entre ellas (si se pasa `routes` — ver
        build_search_points). Sin `routes`, se comporta igual que antes
        (solo las zonas). Deduplica por fsq_place_id, ya que puntos vecinos
        pueden devolver el mismo lugar cerca del borde de ambos radios de
        búsqueda."""
        search_points = build_search_points(locations, routes)
        seen: Dict[str, dict] = {}
        for name, location in search_points.items():
            try:
                pois = self.fetch_pois_for_zone(location)
            except (requests.exceptions.RequestException, ValueError) as e:
                logger.warning(f"Foursquare search failed for point {name}: {e}")
                continue
            for poi in pois:
                seen[poi["fsq_place_id"]] = poi

        result = list(seen.values())

        # Resumen final (tras deduplicar entre zonas): cuántos POIs quedaron
        # en cada balde. Si algunas categorías salen en 0 aquí mismo aunque
        # el log por zona sí haya mostrado nombres de categoría variados,
        # el problema está en _CATEGORY_RULES (falta una palabra real); si
        # ya venían escasas desde el log por zona, es cobertura de Foursquare
        # para estas coordenadas, no un bug de este cliente.
        bucket_counts: Dict[str, int] = {}
        for poi in result:
            bucket_counts[poi["category"]] = bucket_counts.get(poi["category"], 0) + 1
        logger.info(f"Foursquare fetch_pois: {len(result)} POIs únicos tras deduplicar — por categoría: {bucket_counts}")

        return result

    def close(self):
        self.session.close()
