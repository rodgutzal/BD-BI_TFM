"""Cliente de OpenWeather con cache y reintentos."""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class WeatherClient:
    """Cliente HTTP para OpenWeather API con cache y reintentos."""

    def __init__(self, api_key: str, timeout: int = 30, max_retries: int = 3, cache_ttl: int = 300):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_ttl = cache_ttl
        self.session = self._create_session()
        self._weather_cache: dict = {}

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

    def _is_cache_valid(self, lat: float, lon: float) -> bool:
        """Verifica si el cache está válido para una ubicación."""
        key = (lat, lon)
        if key not in self._weather_cache:
            return False

        cached = self._weather_cache[key]
        elapsed = (datetime.now(timezone.utc) - cached["timestamp"]).total_seconds()
        return elapsed < self.cache_ttl

    def get_current_weather(self, latitude: float, longitude: float) -> dict:
        """
        Obtiene el clima actual para una ubicación.

        Usa cache interno para evitar solicitudes duplicadas en el mismo ciclo.
        """
        key = (latitude, longitude)

        if self._is_cache_valid(latitude, longitude):
            logger.debug(f"Weather cache hit para ({latitude}, {longitude})")
            return self._weather_cache[key]["data"]

        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": self.api_key,
            "units": "metric",
        }

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error(f"OpenWeather timeout para ({latitude}, {longitude})")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"OpenWeather request error: {e}")
            raise

        try:
            payload = response.json()
        except ValueError as e:
            logger.error(f"Invalid JSON from OpenWeather: {e}")
            raise

        main_data = payload.get("main", {})
        weather_items = payload.get("weather", [])

        weather_description = (
            weather_items[0].get("description", "Unknown")
            if weather_items
            else "Unknown"
        )

        data = {
            "temperature": main_data.get("temp"),
            "feels_like": main_data.get("feels_like"),
            "humidity": main_data.get("humidity"),
            "weather": weather_description,
        }

        self._weather_cache[key] = {
            "timestamp": datetime.now(timezone.utc),
            "data": data,
        }

        logger.debug(f"Weather fetched para ({latitude}, {longitude}): {data['temperature']}°C")
        return data

    def clear_cache(self):
        """Limpia el cache de clima."""
        self._weather_cache.clear()

    def close(self):
        """Cierra la sesión."""
        self.session.close()
