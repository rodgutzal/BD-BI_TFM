"""Cliente de TomTom con reintentos y manejo avanzado de errores."""

import logging
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class TomTomClient:
    """Cliente HTTP para TomTom API con reintentos automáticos."""

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
            allowed_methods=["GET"]
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
        route_type: str = "fastest",
    ) -> dict:
        """
        Calcula una ruta entre dos puntos usando TomTom.

        Retorna datos de distancia, tiempo, tráfico y geometría.
        """
        url = (
            "https://api.tomtom.com/routing/1/"
            f"calculateRoute/{origin_lat},{origin_lon}:"
            f"{destination_lat},{destination_lon}/json"
        )

        params = {
            "key": self.api_key,
            "traffic": "true",
            "travelMode": "car",
            "routeType": route_type,
            "computeTravelTimeFor": "all",
        }

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error(f"TomTom timeout para ruta {origin_lat},{origin_lon} -> {destination_lat},{destination_lon}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"TomTom request error: {e}")
            raise

        try:
            payload = response.json()
        except ValueError as e:
            logger.error(f"Invalid JSON from TomTom: {e}")
            raise

        routes = payload.get("routes", [])
        if not routes:
            logger.warning("TomTom no retornó rutas")
            raise ValueError("TomTom did not return any route")

        route = routes[0]
        summary = route["summary"]

        distance_km = summary["lengthInMeters"] / 1000
        travel_time_min = summary["travelTimeInSeconds"] / 60
        traffic_delay_min = summary.get("trafficDelayInSeconds", 0) / 60

        no_traffic_seconds = summary.get(
            "noTrafficTravelTimeInSeconds",
            max(
                0,
                summary["travelTimeInSeconds"]
                - summary.get("trafficDelayInSeconds", 0),
            ),
        )
        no_traffic_time_min = no_traffic_seconds / 60

        average_speed_kmh = (
            distance_km / (travel_time_min / 60)
            if travel_time_min > 0
            else 0
        )

        traffic_length_km = summary.get("trafficLengthInMeters", 0) / 1000

        polyline = None
        if "legs" in route and route["legs"]:
            leg = route["legs"][0]
            if "points" in leg:
                polyline = leg["points"]

        return {
            "distance_km": round(distance_km, 2),
            "travel_time_min": round(travel_time_min, 2),
            "no_traffic_time_min": round(no_traffic_time_min, 2),
            "traffic_delay_min": round(traffic_delay_min, 2),
            "traffic_length_km": round(traffic_length_km, 2),
            "average_speed_kmh": round(average_speed_kmh, 2),
            "departure_time": summary.get("departureTime"),
            "arrival_time": summary.get("arrivalTime"),
            "polyline": polyline,
        }

    def close(self):
        """Cierra la sesión."""
        self.session.close()
