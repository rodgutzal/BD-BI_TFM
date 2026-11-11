"""Tests de los clientes HTTP (TomTom, OpenRouteService, OpenWeather, Overpass).

Sin red: se sustituye `client.session` por una sesión falsa que devuelve respuestas fijas o lanza
excepciones de `requests`, y se comprueba la petición que se habría enviado y el parseo del resultado.
"""

import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ors_client import ORSClient  # noqa: E402
from src.poi_client import CATEGORY_TAGS, OverpassClient  # noqa: E402
from src.tomtom_client import TomTomClient  # noqa: E402
from src.weather_client import WeatherClient  # noqa: E402


class Respuesta:
    """Respuesta falsa de requests."""

    def __init__(self, payload=None, status=200, json_invalido=False):
        self._payload, self.status_code, self._json_invalido = payload, status, json_invalido

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")

    def json(self):
        if self._json_invalido:
            raise ValueError("no es JSON")
        return self._payload


class SesionFalsa:
    """Sesión falsa: devuelve (o lanza) lo siguiente de `respuestas` y guarda las peticiones."""

    def __init__(self, *respuestas):
        self.respuestas, self.llamadas, self.cerrada = list(respuestas), [], False

    def _siguiente(self, metodo, url, kwargs):
        self.llamadas.append({"metodo": metodo, "url": url, **kwargs})
        r = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        if isinstance(r, Exception):
            raise r
        return r

    def get(self, url, **kwargs):
        return self._siguiente("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._siguiente("POST", url, kwargs)

    def close(self):
        self.cerrada = True


def _con_sesion(cliente, *respuestas):
    cliente.session = SesionFalsa(*respuestas)
    return cliente


# ---------------------------------------------------------------------------
# Sesión con reintentos (común a los cuatro clientes)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cliente, metodo", [
    (TomTomClient("k", max_retries=4), "GET"),
    (WeatherClient("k", max_retries=4), "GET"),
    (ORSClient("k", max_retries=4), "POST"),
    (OverpassClient(max_retries=4), "POST"),
])
def test_la_sesion_reintenta_solo_errores_transitorios(cliente, metodo):
    """Cada cliente monta reintentos sobre https: 4 intentos, solo para 429/5xx y solo para su método HTTP."""
    estrategia = cliente.session.get_adapter("https://ejemplo.org").max_retries
    assert estrategia.total == 4
    assert set(estrategia.status_forcelist) == {429, 500, 502, 503, 504}
    assert metodo in estrategia.allowed_methods and len(estrategia.allowed_methods) == 1


def test_close_cierra_la_sesion():
    """`close()` cierra la sesión HTTP del cliente."""
    c = _con_sesion(TomTomClient("k"), Respuesta({}))
    c.close()
    assert c.session.cerrada


# ---------------------------------------------------------------------------
# TomTom
# ---------------------------------------------------------------------------

TOMTOM_OK = {"routes": [{
    "summary": {"lengthInMeters": 5000, "travelTimeInSeconds": 900, "trafficDelayInSeconds": 120,
                "noTrafficTravelTimeInSeconds": 780, "trafficLengthInMeters": 1500,
                "departureTime": "2026-11-01T10:00:00+01:00", "arrivalTime": "2026-11-01T10:15:00+01:00"},
    "legs": [{"points": [{"latitude": 35.9, "longitude": 14.5}]}],
}]}


def test_tomtom_parsea_la_ruta_y_envia_la_peticion_correcta():
    """TomTom interpreta la respuesta con todos sus campos y envía la URL, el timeout y los parámetros correctos."""
    c = _con_sesion(TomTomClient("CLAVE", timeout=7), Respuesta(TOMTOM_OK))
    r = c.calculate_route(35.90, 14.50, 35.88, 14.52, route_type="shortest")
    assert r == {
        "distance_km": 5.0, "travel_time_min": 15.0, "no_traffic_time_min": 13.0, "traffic_delay_min": 2.0,
        "traffic_length_km": 1.5, "average_speed_kmh": 20.0,
        "departure_time": "2026-11-01T10:00:00+01:00", "arrival_time": "2026-11-01T10:15:00+01:00",
        "polyline": [{"latitude": 35.9, "longitude": 14.5}],
    }
    llamada = c.session.llamadas[0]
    assert llamada["url"].endswith("calculateRoute/35.9,14.5:35.88,14.52/json")
    assert llamada["timeout"] == 7
    assert llamada["params"]["key"] == "CLAVE" and llamada["params"]["routeType"] == "shortest"


def test_tomtom_sin_campos_opcionales_deduce_el_tiempo_sin_trafico():
    """Sin trafico ni noTrafficTravelTime: retraso 0 y tiempo sin tráfico = tiempo de viaje; sin polyline."""
    payload = {"routes": [{"summary": {"lengthInMeters": 1000, "travelTimeInSeconds": 600}}]}
    r = _con_sesion(TomTomClient("k"), Respuesta(payload)).calculate_route(0, 0, 1, 1)
    assert r["traffic_delay_min"] == 0 and r["no_traffic_time_min"] == 10.0
    assert r["polyline"] is None and r["departure_time"] is None


def test_tomtom_con_tiempo_cero_no_divide_por_cero():
    """Con un tiempo de viaje de 0, TomTom da velocidad media 0 y no divide entre cero."""
    payload = {"routes": [{"summary": {"lengthInMeters": 1000, "travelTimeInSeconds": 0}}]}
    assert _con_sesion(TomTomClient("k"), Respuesta(payload)).calculate_route(0, 0, 1, 1)["average_speed_kmh"] == 0


@pytest.mark.parametrize("respuesta, error", [
    (requests.exceptions.Timeout("lento"), requests.exceptions.Timeout),
    (requests.exceptions.ConnectionError("sin red"), requests.exceptions.RequestException),
    (Respuesta(status=403), requests.exceptions.HTTPError),
    (Respuesta(json_invalido=True), ValueError),
    (Respuesta({"routes": []}), ValueError),
    (Respuesta({}), ValueError),
])
def test_tomtom_propaga_los_errores(respuesta, error):
    """Los errores de red y de estado HTTP de TomTom (parametrizado) se propagan al llamador."""
    with pytest.raises(error):
        _con_sesion(TomTomClient("k"), respuesta).calculate_route(0, 0, 1, 1)


# ---------------------------------------------------------------------------
# OpenRouteService
# ---------------------------------------------------------------------------

ORS_OK = {"routes": [{"summary": {"distance": 4200.0, "duration": 600.0}, "geometry": "abc123"}]}


def test_ors_parsea_la_ruta_con_las_mismas_claves_que_tomtom():
    """ORS devuelve las mismas claves que TomTom; los campos de tráfico que no informa quedan en `None`, no en 0."""
    c = _con_sesion(ORSClient("CLAVE"), Respuesta(ORS_OK))
    r = c.calculate_route(35.90, 14.50, 35.88, 14.52)
    assert r["distance_km"] == 4.2 and r["travel_time_min"] == 10.0 and r["average_speed_kmh"] == 25.2
    assert r["polyline"] == "abc123"
    # ORS no informa de tráfico: esos campos son None (y no 0), para no confundirse con "sin retraso".
    sin_trafico = ("no_traffic_time_min", "traffic_delay_min", "traffic_length_km", "departure_time", "arrival_time")
    assert all(r[k] is None for k in sin_trafico)
    tt = _con_sesion(TomTomClient("k"), Respuesta(TOMTOM_OK)).calculate_route(0, 0, 1, 1)
    assert set(r) == set(tt)


def test_ors_envia_longitud_antes_que_latitud_y_la_clave_en_la_cabecera():
    """ORS recibe las coordenadas como [longitud, latitud] y la clave de API en la cabecera `Authorization`."""
    c = _con_sesion(ORSClient("CLAVE"), Respuesta(ORS_OK))
    c.calculate_route(35.90, 14.50, 35.88, 14.52)
    llamada = c.session.llamadas[0]
    assert llamada["metodo"] == "POST" and llamada["url"] == ORSClient.ROUTE_URL
    assert llamada["json"] == {"coordinates": [[14.50, 35.90], [14.52, 35.88]]}     # [lon, lat]
    assert llamada["headers"]["Authorization"] == "CLAVE"


@pytest.mark.parametrize("respuesta, error", [
    (requests.exceptions.Timeout("lento"), requests.exceptions.Timeout),
    (Respuesta(status=401), requests.exceptions.HTTPError),
    (Respuesta(json_invalido=True), ValueError),
    (Respuesta({"routes": []}), ValueError),
])
def test_ors_propaga_los_errores(respuesta, error):
    """Los errores de red y de estado HTTP de ORS (parametrizado) se propagan al llamador."""
    with pytest.raises(error):
        _con_sesion(ORSClient("k"), respuesta).calculate_route(0, 0, 1, 1)


# ---------------------------------------------------------------------------
# OpenWeather
# ---------------------------------------------------------------------------

CLIMA_OK = {"main": {"temp": 21.5, "feels_like": 22.0, "humidity": 60}, "weather": [{"description": "cielo claro"}]}


def test_weather_parsea_y_pide_unidades_metricas():
    """El clima se interpreta correctamente y se pide en unidades métricas con la clave en los parámetros."""
    c = _con_sesion(WeatherClient("CLAVE"), Respuesta(CLIMA_OK))
    assert c.get_current_weather(35.9, 14.5) == {"temperature": 21.5, "feels_like": 22.0, "humidity": 60,
                                                 "weather": "cielo claro"}
    p = c.session.llamadas[0]["params"]
    assert p == {"lat": 35.9, "lon": 14.5, "appid": "CLAVE", "units": "metric"}


def test_weather_respuesta_incompleta_da_none_y_unknown():
    """Una respuesta de clima incompleta da valores `None` y la descripción «Unknown»."""
    r = _con_sesion(WeatherClient("k"), Respuesta({})).get_current_weather(0, 0)
    assert r == {"temperature": None, "feels_like": None, "humidity": None, "weather": "Unknown"}


def test_weather_usa_la_cache_por_ubicacion_y_caduca():
    """El clima se cachea por ubicación y caduca pasado el tiempo de vida; `clear_cache` vacía la caché."""
    c = _con_sesion(WeatherClient("k", cache_ttl=300), Respuesta(CLIMA_OK))
    c.get_current_weather(35.9, 14.5)
    c.get_current_weather(35.9, 14.5)                       # misma ubicación: cache
    assert len(c.session.llamadas) == 1
    c.get_current_weather(35.8, 14.4)                       # otra ubicación: nueva petición
    assert len(c.session.llamadas) == 2
    c._weather_cache[(35.9, 14.5)]["timestamp"] -= timedelta(seconds=301)
    c.get_current_weather(35.9, 14.5)                       # caducada: nueva petición
    assert len(c.session.llamadas) == 3
    c.clear_cache()
    assert c._weather_cache == {}


def test_weather_un_error_no_se_guarda_en_cache():
    """Un error al pedir el clima no se guarda en la caché: la siguiente petición vuelve a intentarlo."""
    c = _con_sesion(WeatherClient("k"), requests.exceptions.ConnectionError("sin red"), Respuesta(CLIMA_OK))
    with pytest.raises(requests.exceptions.RequestException):
        c.get_current_weather(35.9, 14.5)
    assert c.get_current_weather(35.9, 14.5)["temperature"] == 21.5       # el reintento sí llega a la red


@pytest.mark.parametrize("respuesta, error", [
    (requests.exceptions.Timeout("lento"), requests.exceptions.Timeout),
    (Respuesta(status=500), requests.exceptions.HTTPError),
    (Respuesta(json_invalido=True), ValueError),
])
def test_weather_propaga_los_errores(respuesta, error):
    """Los errores de red y de estado HTTP del clima (parametrizado) se propagan al llamador."""
    with pytest.raises(error):
        _con_sesion(WeatherClient("k"), respuesta).get_current_weather(0, 0)


# ---------------------------------------------------------------------------
# Overpass
# ---------------------------------------------------------------------------

def _zona():
    return {"a": SimpleNamespace(latitude=35.90, longitude=14.50), "b": SimpleNamespace(latitude=35.80, longitude=14.60)}


ELEMENTOS = [
    {"type": "node", "id": 1, "lat": 35.9, "lon": 14.5, "tags": {"amenity": "cafe", "name": "Café Uno"}},
    {"type": "way", "id": 2, "center": {"lat": 35.8, "lon": 14.6}, "tags": {"shop": "bakery"}},
    {"type": "node", "id": 3, "lat": 35.9, "lon": 14.5, "tags": {"highway": "bus_stop"}},        # sin categoría
    {"type": "way", "id": 4, "tags": {"amenity": "school"}},                                      # sin centro
]


def test_overpass_clasifica_por_prioridad_y_toma_el_valor_como_subcategoria():
    """Overpass clasifica cada elemento por prioridad entre categorías y toma el valor de la etiqueta como subcategoría; lo que no encaja da `None`."""
    clasificar = OverpassClient._classify
    assert clasificar({"amenity": "cafe"}) == ("food_drink", "cafe")
    assert clasificar({"shop": "bakery", "amenity": "cafe"}) == ("food_drink", "cafe")      # la específica gana
    assert clasificar({"shop": "mall"}) == ("mall", "mall")                                  # antes que "business"
    assert clasificar({"shop": "bakery"}) == ("business", "bakery")
    assert clasificar({"tourism": "museum", "shop": "gift"}) == ("leisure", "museum")
    assert clasificar({"highway": "bus_stop"}) is None
    assert OverpassClient._categorize({"office": "lawyer"}) == "business"
    assert OverpassClient._categorize({}) is None


def test_overpass_la_query_cubre_todas_las_categorias():
    """La consulta de Overpass cubre todas las categorías: cabecera con el timeout, regex para varios valores y una cláusula de nodo y otra de vía por etiqueta."""
    q = OverpassClient._build_query((35.7, 14.4, 36.0, 14.7), CATEGORY_TAGS, 75)
    assert q.startswith("[out:json][timeout:75];") and q.rstrip().endswith("out center tags;")
    assert '["amenity"~"^(school|college|university|kindergarten)$"]' in q       # varios valores: una regex
    assert '["shop"](35.7,14.4,36.0,14.7);' in q                                  # clave sin valor
    assert q.count("node[") == q.count("way[") == sum(len(v) for v in CATEGORY_TAGS.values())


def test_overpass_parsea_nodos_y_ways_y_descarta_lo_inutil():
    """Se interpretan nodos y vías y se descartan los elementos sin categoría o sin coordenadas; el que no tiene nombre recibe uno genérico."""
    pois = OverpassClient()._parse_elements(ELEMENTOS)
    assert [p["osm_id"] for p in pois] == [1, 2]                  # sin categoría (3) y sin coordenadas (4) fuera
    assert pois[0] == {"osm_type": "node", "osm_id": 1, "category": "food_drink", "subcategory": "cafe",
                       "name": "Café Uno", "latitude": 35.9, "longitude": 14.5}
    assert pois[1]["latitude"] == 35.8 and pois[1]["name"] == "Business (sin nombre)"


def test_overpass_fetch_calcula_el_bbox_con_margen_y_el_timeout_del_servidor():
    """`fetch_pois` calcula el rectángulo de búsqueda con el margen y envía el timeout del servidor y el del cliente."""
    c = _con_sesion(OverpassClient(timeout=90), Respuesta({"elements": ELEMENTOS}))
    pois = c.fetch_pois(_zona(), margin_deg=0.01)
    assert len(pois) == 2
    llamada = c.session.llamadas[0]
    assert "(35.79,14.49,35.91,14.61)" in llamada["data"]["data"]                  # sur, oeste, norte, este
    assert "[timeout:75]" in llamada["data"]["data"] and llamada["timeout"] == 90   # servidor < cliente


def test_overpass_prueba_el_siguiente_espejo_si_uno_falla():
    """Si un servidor espejo de Overpass falla (error de red o 504), se prueba el siguiente."""
    c = _con_sesion(OverpassClient(endpoints=["https://uno", "https://dos", "https://tres"]),
                    requests.exceptions.ConnectionError("caído"), Respuesta(status=504),
                    Respuesta({"elements": ELEMENTOS}))
    assert len(c.fetch_pois(_zona())) == 2
    assert [x["url"] for x in c.session.llamadas] == ["https://uno", "https://dos", "https://tres"]


def test_overpass_json_invalido_cuenta_como_fallo_del_espejo():
    """Un JSON inválido cuenta como fallo del espejo y se pasa al siguiente."""
    c = _con_sesion(OverpassClient(endpoints=["https://uno", "https://dos"]),
                    Respuesta(json_invalido=True), Respuesta({"elements": []}))
    assert c.fetch_pois(_zona()) == []
    assert len(c.session.llamadas) == 2


def test_overpass_si_todos_los_espejos_fallan_lanza_runtimeerror():
    """Si todos los espejos fallan, `fetch_pois` lanza `RuntimeError` tras probarlos todos."""
    c = _con_sesion(OverpassClient(endpoints=["https://uno", "https://dos"]), requests.exceptions.Timeout("lento"))
    with pytest.raises(RuntimeError, match="All Overpass endpoints failed"):
        c.fetch_pois(_zona())
    assert len(c.session.llamadas) == 2


def test_overpass_envia_un_user_agent_descriptivo():
    """El cliente de Overpass envía su `User-Agent` descriptivo."""
    assert OverpassClient().session.headers["User-Agent"] == OverpassClient.USER_AGENT
