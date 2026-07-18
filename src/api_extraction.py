from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

try:
    from src.config import get_openweather_api_key, get_tomtom_api_key
except ModuleNotFoundError:
    from config import get_openweather_api_key, get_tomtom_api_key

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_CSV_PATH = RAW_DATA_DIR / "traffic_weather_data.csv"
DEFAULT_LATITUDE = 35.5333
DEFAULT_LONGITUDE = 14.2858

TOMTOM_GEOCODE_URL = "https://api.tomtom.com/search/2/geocode/{query}.json"
TOMTOM_FLOW_URL = (
    "https://api.tomtom.com/traffic/services/4/flowSegmentData/{style}/{zoom}/json"
)
OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "snapshot"


def _request_json(
    url: str,
    *,
    params: dict[str, Any],
    session: requests.Session | None = None,
) -> dict[str, Any]:
    client = session or requests.Session()
    response = client.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _validate_coordinates(latitude: float, longitude: float) -> None:
    if not -90 <= latitude <= 90:
        raise ValueError(f"Latitude must be between -90 and 90. Received: {latitude}")
    if not -180 <= longitude <= 180:
        raise ValueError(f"Longitude must be between -180 and 180. Received: {longitude}")


def geocode_location(
    query: str,
    *,
    limit: int = 1,
    country_set: str | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Resolve a place name into coordinates using the TomTom Geocoding API."""
    params: dict[str, Any] = {
        "key": get_tomtom_api_key(),
        "limit": limit,
    }
    if country_set:
        params["countrySet"] = country_set

    payload = _request_json(
        TOMTOM_GEOCODE_URL.format(query=requests.utils.quote(query)),
        params=params,
        session=session,
    )
    results = payload.get("results", [])
    if not results:
        raise ValueError(f"No geocoding results found for query: {query}")
    return payload


def fetch_tomtom_flow_segment(
    latitude: float,
    longitude: float,
    *,
    zoom: int = 10,
    style: str = "absolute",
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch real-time traffic flow details for a single point."""
    _validate_coordinates(latitude, longitude)
    params = {
        "key": get_tomtom_api_key(),
        "point": f"{latitude},{longitude}",
    }
    return _request_json(
        TOMTOM_FLOW_URL.format(style=style, zoom=zoom),
        params=params,
        session=session,
    )


def fetch_openweather_current(
    latitude: float,
    longitude: float,
    *,
    units: str = "metric",
    language: str = "en",
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch current weather conditions for a coordinate pair."""
    _validate_coordinates(latitude, longitude)
    params = {
        "appid": get_openweather_api_key(),
        "lat": latitude,
        "lon": longitude,
        "units": units,
        "lang": language,
    }
    return _request_json(
        OPENWEATHER_CURRENT_URL,
        params=params,
        session=session,
    )


def extract_traffic_weather_record(
    traffic_data: dict[str, Any],
    weather_data: dict[str, Any],
    *,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Flatten the API payloads into a single analytics-ready record."""
    flow_segment = traffic_data["flowSegmentData"]
    weather_main = weather_data["main"]
    weather_conditions = weather_data["weather"][0]

    return {
        "timestamp": (timestamp or datetime.now(UTC)).isoformat(),
        "speed": flow_segment["currentSpeed"],
        "free_flow_speed": flow_segment["freeFlowSpeed"],
        "confidence": flow_segment["confidence"],
        "temperature": weather_main["temp"],
        "humidity": weather_main["humidity"],
        "weather": weather_conditions["description"],
    }


def save_raw_snapshot(payload: dict[str, Any], source_name: str, query: str) -> Path:
    """Persist raw API output to the project's data/raw directory."""
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    file_path = RAW_DATA_DIR / f"{timestamp}_{source_name}_{_slugify(query)}.json"
    file_path.write_text(json.dumps(payload, indent=2))
    return file_path


def save_records_to_csv(
    records: list[dict[str, Any]],
    output_path: Path | None = None,
) -> Path:
    """Write one or more flattened records to CSV."""
    csv_path = output_path or DEFAULT_CSV_PATH
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = pd.DataFrame(records)
    dataframe.to_csv(csv_path, index=False)
    return csv_path


def collect_point_snapshot(
    latitude: float,
    longitude: float,
    *,
    zoom: int = 10,
    weather_units: str = "metric",
    persist: bool = False,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Collect raw traffic and weather payloads for a coordinate pair."""
    traffic_payload = fetch_tomtom_flow_segment(
        latitude,
        longitude,
        zoom=zoom,
        session=session,
    )
    weather_payload = fetch_openweather_current(
        latitude,
        longitude,
        units=weather_units,
        session=session,
    )

    snapshot = {
        "collected_at_utc": datetime.now(UTC).isoformat(),
        "location": {
            "lat": latitude,
            "lon": longitude,
        },
        "tomtom_traffic_flow": traffic_payload,
        "openweather_current": weather_payload,
    }

    if persist:
        file_path = save_raw_snapshot(snapshot, "mobility_snapshot", f"{latitude}_{longitude}")
        snapshot["saved_to"] = str(file_path)

    return snapshot


def collect_point_dataframe(
    latitude: float,
    longitude: float,
    *,
    zoom: int = 10,
    weather_units: str = "metric",
    output_path: Path | None = None,
    session: requests.Session | None = None,
) -> tuple[pd.DataFrame, Path]:
    """
    Fetch traffic and weather for a point, then save the flattened result as CSV.
    """
    traffic_payload = fetch_tomtom_flow_segment(
        latitude,
        longitude,
        zoom=zoom,
        session=session,
    )
    weather_payload = fetch_openweather_current(
        latitude,
        longitude,
        units=weather_units,
        session=session,
    )
    record = extract_traffic_weather_record(traffic_payload, weather_payload)
    csv_path = save_records_to_csv([record], output_path=output_path)
    return pd.DataFrame([record]), csv_path


def collect_city_snapshot(
    query: str,
    *,
    country_set: str | None = None,
    zoom: int = 10,
    weather_units: str = "metric",
    persist: bool = True,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """
    Collect geocoding, traffic, and weather data for a single place query.

    The returned payload is ready to save to data/raw or pass into downstream
    cleaning and feature engineering steps.
    """
    geocode_payload = geocode_location(
        query,
        limit=1,
        country_set=country_set,
        session=session,
    )
    top_result = geocode_payload["results"][0]
    position = top_result["position"]
    latitude = position["lat"]
    longitude = position["lon"]

    traffic_payload = fetch_tomtom_flow_segment(
        latitude,
        longitude,
        zoom=zoom,
        session=session,
    )
    weather_payload = fetch_openweather_current(
        latitude,
        longitude,
        units=weather_units,
        session=session,
    )

    snapshot = {
        "query": query,
        "collected_at_utc": datetime.now(UTC).isoformat(),
        "location": {
            "formatted_address": top_result.get("address", {}).get("freeformAddress"),
            "lat": latitude,
            "lon": longitude,
        },
        "tomtom_geocode": geocode_payload,
        "tomtom_traffic_flow": traffic_payload,
        "openweather_current": weather_payload,
    }

    if persist:
        file_path = save_raw_snapshot(snapshot, "mobility_snapshot", query)
        snapshot["saved_to"] = str(file_path)

    return snapshot


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch TomTom traffic and OpenWeather data for a place query."
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Place name or address to geocode.",
    )
    parser.add_argument(
        "--country-set",
        help="Optional comma-separated country codes for TomTom geocoding.",
    )
    parser.add_argument(
        "--lat",
        type=float,
        help=f"Latitude for direct point-based extraction. Default: {DEFAULT_LATITUDE}.",
    )
    parser.add_argument(
        "--lon",
        type=float,
        help=f"Longitude for direct point-based extraction. Default: {DEFAULT_LONGITUDE}.",
    )
    parser.add_argument(
        "--zoom",
        type=int,
        default=10,
        help="TomTom traffic flow zoom level (0-22). Default: 10.",
    )
    parser.add_argument(
        "--weather-units",
        default="metric",
        choices=["standard", "metric", "imperial"],
        help="Units for OpenWeather current conditions. Default: metric.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Return the combined JSON without writing a file to data/raw.",
    )
    parser.add_argument(
        "--csv-output",
        default=str(DEFAULT_CSV_PATH),
        help="CSV path for flattened traffic-weather rows.",
    )
    return parser


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()

    if (args.lat is None) != (args.lon is None):
        parser.error("--lat and --lon must be provided together.")

    if args.lat is not None and args.lon is not None:
        dataframe, csv_path = collect_point_dataframe(
            args.lat,
            args.lon,
            zoom=args.zoom,
            weather_units=args.weather_units,
            output_path=Path(args.csv_output),
        )
        print(dataframe)
        print(f"Data saved successfully to {csv_path}.")
        return

    if not args.query:
        dataframe, csv_path = collect_point_dataframe(
            DEFAULT_LATITUDE,
            DEFAULT_LONGITUDE,
            zoom=args.zoom,
            weather_units=args.weather_units,
            output_path=Path(args.csv_output),
        )
        print(dataframe)
        print(f"Data saved successfully to {csv_path}.")
        return

    snapshot = collect_city_snapshot(
        args.query,
        country_set=args.country_set,
        zoom=args.zoom,
        weather_units=args.weather_units,
        persist=not args.no_save,
    )
    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
