"""Cliente de Overpass API (OpenStreetMap) para infraestructura urbana
(escuelas, hospitales, restauración y bares, ocio, deporte, centros
comerciales y negocios/comercios en general).

A diferencia de ors_client.py/tomtom_client.py, Overpass no requiere API key
ni cuenta: es un servicio público sobre datos de OpenStreetMap. Se consulta
una única vez por refresco (no por ruta) usando un bounding box que cubre
todas las ubicaciones monitorizadas (src.locations.LOCATIONS), con reintento
sobre varios espejos públicos por si alguno está saturado.
"""

import logging
from typing import Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Categorías de interés y los tags OSM que las identifican.
#
# Sintaxis de cada especificación:
#   "clave"             -> la clave existe, con cualquier valor (ej. "shop"
#                          matchea shop=supermarket, shop=bakery, ...)
#   "clave=valor"       -> ese valor exacto
#   "clave=v1|v2|v3"    -> cualquiera de esos valores (se traduce a una sola
#                          expresión regular en la query, en vez de una
#                          cláusula por valor)
#
# EL ORDEN IMPORTA: es la prioridad de _classify() — gana la primera
# categoría cuyo tag matchee. Las específicas van antes que la genérica
# "business" (["shop", "office"]), para que un elemento con shop=bakery y
# amenity=cafe cuente como food_drink y shop=mall no caiga en "business"
# solo por tener también la clave "shop".
#
# Este diccionario es la ÚNICA fuente de verdad: tanto la query que se envía
# a Overpass como la clasificación de cada elemento salen de aquí (antes la
# clasificación tenía su propia copia de estas listas y podían desalinearse).
#
# Deliberadamente excluidos por ser ruido, no competencia: leisure=pitch,
# playground, park (espacios públicos) y swimming_pool (en OpenStreetMap
# incluye piscinas privadas de edificios residenciales).
CATEGORY_TAGS: Dict[str, List[str]] = {
    "school": ["amenity=school|college|university|kindergarten"],
    "hospital": ["amenity=hospital|clinic|doctors|pharmacy"],
    # Restauración y bares: la competencia más numerosa para casi cualquier
    # negocio de barrio, y que antes no se recolectaba en absoluto.
    "food_drink": ["amenity=restaurant|cafe|bar|pub|fast_food|food_court|ice_cream|biergarten"],
    "leisure": [
        "amenity=cinema|theatre|nightclub|casino|arts_centre",
        "leisure=amusement_arcade|bowling_alley|adult_gaming_centre|escape_game|miniature_golf|dance",
        "tourism=museum|gallery|theme_park|zoo|aquarium",
    ],
    "sport": ["leisure=fitness_centre|sports_centre|sports_hall|stadium|ice_rink"],
    "mall": ["shop=mall|department_store"],
    "business": ["shop", "office"],
}


def _parse_spec(tag_spec: str) -> Tuple[str, Optional[Tuple[str, ...]]]:
    """'amenity=cafe|bar' -> ('amenity', ('cafe', 'bar')); 'shop' -> ('shop', None)."""
    if "=" not in tag_spec:
        return tag_spec, None
    key, value = tag_spec.split("=", 1)
    return key, tuple(value.split("|"))


# Espejos públicos de Overpass, probados en orden hasta que uno responda.
DEFAULT_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]


class OverpassClient:
    """Cliente HTTP para Overpass API con reintentos y fallback entre espejos."""

    # La política de uso de Overpass/OSM pide un User-Agent descriptivo que
    # identifique la app — sin uno, algunos espejos (overpass-api.de
    # incluido) responden 406 Not Acceptable a nivel de Apache antes de
    # que la query siquiera llegue al motor de Overpass.
    USER_AGENT = "BD-BI-TFM-Urban-Mobility-POI-Collector/1.0 (proyecto academico MBDIB)"

    def __init__(
        self,
        endpoints: Optional[List[str]] = None,
        timeout: int = 90,
        max_retries: int = 2,
    ):
        self.endpoints = endpoints or DEFAULT_ENDPOINTS
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({"User-Agent": self.USER_AGENT})
        return session

    @staticmethod
    def _build_query(bbox: tuple, category_tags: Dict[str, List[str]], server_timeout: int) -> str:
        """Arma una query Overpass QL que trae nodos y ways para todas las
        categorías dentro del bbox (south,west,north,east) en una sola pasada.

        `out center` da lat/lon directos para nodos y el centroide para
        ways/relations, evitando tener que resolver la geometría completa.
        """
        south, west, north, east = bbox
        bbox_str = f"{south},{west},{north},{east}"
        clauses = []
        for tag_specs in category_tags.values():
            for tag_spec in tag_specs:
                key, values = _parse_spec(tag_spec)
                if values is None:
                    selector = f'["{key}"]'
                elif len(values) == 1:
                    selector = f'["{key}"="{values[0]}"]'
                else:
                    selector = f'["{key}"~"^({"|".join(values)})$"]'
                clauses.append(f"node{selector}({bbox_str});")
                clauses.append(f"way{selector}({bbox_str});")

        body = "\n  ".join(clauses)
        return f"[out:json][timeout:{server_timeout}];\n(\n  {body}\n);\nout center tags;"

    @staticmethod
    def _classify(tags: dict) -> Optional[Tuple[str, str]]:
        """Devuelve (categoría, subcategoría) del primer tag de CATEGORY_TAGS
        que matchee, o None si el elemento no encaja en ninguna categoría.

        La subcategoría es el VALOR del tag que definió la categoría (ej.
        amenity=cafe -> "cafe"; shop=bakery -> "bakery"). Antes se tomaba
        `amenity or shop or office`, lo que daba subcategorías equivocadas
        para categorías basadas en otras claves (un museo con tag
        `shop=gift` habría quedado como "gift" en vez de "museum").
        """
        for category, tag_specs in CATEGORY_TAGS.items():
            for tag_spec in tag_specs:
                key, values = _parse_spec(tag_spec)
                value = tags.get(key)
                if value is None:
                    continue
                if values is None or value in values:
                    return category, value
        return None

    @classmethod
    def _categorize(cls, tags: dict) -> Optional[str]:
        """Solo la categoría (ver _classify)."""
        result = cls._classify(tags)
        return result[0] if result else None

    def fetch_pois(self, locations: dict, margin_deg: float = 0.015) -> List[dict]:
        """Descarga POIs dentro del bbox que cubre `locations` (dict de
        src.locations.Location), con un margen en grados para no cortar
        infraestructura justo en el borde de la zona monitorizada.
        """
        lats = [loc.latitude for loc in locations.values()]
        lons = [loc.longitude for loc in locations.values()]
        bbox = (
            min(lats) - margin_deg,
            min(lons) - margin_deg,
            max(lats) + margin_deg,
            max(lons) + margin_deg,
        )
        # El timeout del servidor Overpass debe ser menor que el timeout
        # HTTP del cliente, para que sea Overpass quien corte la query (y
        # devuelva un 504 legible) antes de que requests aborte la
        # conexión sin respuesta.
        server_timeout = max(10, self.timeout - 15)
        query = self._build_query(bbox, CATEGORY_TAGS, server_timeout)

        last_error = None
        for endpoint in self.endpoints:
            try:
                response = self.session.post(
                    endpoint,
                    data={"data": query},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                return self._parse_elements(payload.get("elements", []))
            except (requests.exceptions.RequestException, ValueError) as e:
                logger.warning(f"Overpass endpoint {endpoint} failed: {e}")
                last_error = e
                continue

        raise RuntimeError(f"All Overpass endpoints failed. Last error: {last_error}")

    def _parse_elements(self, elements: List[dict]) -> List[dict]:
        pois = []
        for element in elements:
            tags = element.get("tags", {})
            classified = self._classify(tags)
            if classified is None:
                continue
            category, subcategory = classified

            if element.get("type") == "node":
                lat, lon = element.get("lat"), element.get("lon")
            else:
                center = element.get("center") or {}
                lat, lon = center.get("lat"), center.get("lon")

            if lat is None or lon is None:
                continue

            pois.append(
                {
                    "osm_type": element.get("type"),
                    "osm_id": element.get("id"),
                    "category": category,
                    "subcategory": subcategory,
                    "name": tags.get("name") or f"{category.replace('_', ' ').capitalize()} (sin nombre)",
                    "latitude": lat,
                    "longitude": lon,
                }
            )
        return pois

    def close(self):
        self.session.close()
