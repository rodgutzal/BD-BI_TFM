"""Cliente de OpenRouteService (ORS) con reintentos, con la misma interfaz que TomTomClient.

Extraído y refactorizado del script original `src/api_extraction.py` de
BD_BI_TFM (que hacía la llamada HTTP inline). Se mantiene como fuente de
datos alternativa a TomTom: no requiere clave de pago y es la que ya usaba
el proyecto base.
"""

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class ORSClient:
    """Cliente HTTP para OpenRouteService (directions API) con reintentos automáticos."""

    ROUTE_URL = "https://api.openrouteservice.org/v2/directions/driving-car"

    def __init__(self, api_key: str, timeout: int = 30, max_retries: int = 3):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Crea una sesión con reintentos configurados."""
        session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def calculate_route(
        self,
        origin_lat: float,
        origin_lon: float,
        destination_lat: float,
        destination_lon: float,
    ) -> dict:
        """
        Calcula una ruta entre dos puntos usando OpenRouteService.

        ORS (a diferencia de TomTom) no reporta tráfico en tiempo real, por
        lo que los campos de tráfico (no_traffic_time_min, traffic_delay_min,
        traffic_length_km) se retornan como None. El resultado usa las
        mismas claves que TomTomClient.calculate_route() para que el
        collector pueda tratar ambas fuentes de forma intercambiable.
        """
        headers = {
            "Authorization": self.api_key,
            "Accept": "application/json, application/geo+json",
            "Content-Type": "application/json",
        }
        body = {"coordinates": [[origin_lon, origin_lat], [destination_lon, destination_lat]]}

        try:
            response = self.session.post(
                self.ROUTE_URL,
                json=body,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error(
                f"ORS timeout para ruta {origin_lat},{origin_lon} -> "
                f"{destination_lat},{destination_lon}"
            )
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"ORS request error: {e}")
            raise

        try:
            payload = response.json()
        except ValueError as e:
            logger.error(f"Invalid JSON from ORS: {e}")
            raise

        routes = payload.get("routes", [])
        if not routes:
            logger.warning("ORS no retornó rutas")
            raise ValueError("ORS did not return any route")

        summary = routes[0]["summary"]
        distance_km = summary["distance"] / 1000
        travel_time_min = summary["duration"] / 60

        average_speed_kmh = (
            distance_km / (travel_time_min / 60) if travel_time_min > 0 else 0
        )

        geometry = routes[0].get("geometry")

        return {
            "distance_km": round(distance_km, 2),
            "travel_time_min": round(travel_time_min, 2),
            "no_traffic_time_min": None,
            "traffic_delay_min": None,
            "traffic_length_km": None,
            "average_speed_kmh": round(average_speed_kmh, 2),
            "departure_time": None,
            "arrival_time": None,
            "polyline": geometry,
        }

    def close(self):
        """Cierra la sesión."""
        self.session.close()
