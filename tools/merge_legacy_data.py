#!/usr/bin/env python
"""
Script de integración (one-off): fusiona el histórico de datos de
BD_BI_TFM (ORS, data/raw/legacy_ors_traffic_weather_data.csv) y de
urban-mobility-analytics1 (TomTom, data/raw/legacy_tomtom_route_weather_data.csv)
en el esquema unificado de BD_BI_TFM (data/raw/route_weather_data.csv +
data/mobility.db).

Se documenta y se deja en el repo por transparencia/reproducibilidad, pero
NO hace falta volver a ejecutarlo: BD_BI_TFM ya se entrega con los datos
fusionados.

Decisiones de mapeo (ver INTEGRATION_NOTES.md para el detalle completo):
  - ORS no reporta tráfico en tiempo real -> no_traffic_time_min,
    traffic_delay_min, traffic_length_km quedan en NULL para esas filas.
  - ORS sólo pedía UNA lectura de clima por ciclo (no por ubicación) -> se
    replica ese mismo valor en origin_* y destination_*.
  - Los `polyline` del histórico TomTom (2.664 filas) se descartan en la
    fusión para mantener el tamaño del dataset manejable; no afecta al
    dashboard actual (no se usan en el mapa) y las mediciones nuevas que
    recolecte el collector sí siguen guardando su polyline normalmente.
  - Los timestamps del CSV de BD_BI_TFM eran naive (sin timezone). Se
    asumen como UTC por simplicidad; el desfase real con Malta (UTC+1/+2)
    es de 1-2h y no afecta al análisis a nivel de tendencias/patrones.
"""

import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase  # noqa: E402

LEGACY_ORS_CSV = ROOT_DIR / "data" / "raw" / "legacy_ors_traffic_weather_data.csv"
LEGACY_TOMTOM_CSV = ROOT_DIR / "data" / "raw" / "legacy_tomtom_route_weather_data.csv"
UNIFIED_CSV = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"
UNIFIED_DB = ROOT_DIR / "data" / "mobility.db"

HIGH_DELAY_THRESHOLD_MIN = 20

UNIFIED_COLUMNS = [
    "timestamp", "origin", "destination", "data_source",
    "distance_km", "travel_time_min", "no_traffic_time_min", "traffic_delay_min",
    "traffic_length_km", "average_speed_kmh", "departure_time", "arrival_time",
    "origin_temperature", "origin_feels_like", "origin_humidity", "origin_weather",
    "destination_temperature", "destination_feels_like", "destination_humidity",
    "destination_weather", "mobility_level", "polyline",
]


def load_ors_legacy() -> pd.DataFrame:
    df = pd.read_csv(LEGACY_ORS_CSV)
    out = pd.DataFrame()
    out["timestamp"] = pd.to_datetime(df["datetime"]).dt.tz_localize("UTC").dt.strftime(
        "%Y-%m-%dT%H:%M:%S.%f+00:00"
    )
    out["origin"] = df["origin"]
    out["destination"] = df["destination"]
    out["data_source"] = "ors"
    out["distance_km"] = df["distance_km"]
    out["travel_time_min"] = df["duration_min"]
    out["no_traffic_time_min"] = None
    out["traffic_delay_min"] = None
    out["traffic_length_km"] = None
    out["average_speed_kmh"] = (df["distance_km"] / (df["duration_min"] / 60)).round(2)
    out["departure_time"] = None
    out["arrival_time"] = None
    out["origin_temperature"] = df["temperature"]
    out["origin_feels_like"] = None
    out["origin_humidity"] = df["humidity"]
    out["origin_weather"] = df["weather_description"]
    out["destination_temperature"] = df["temperature"]
    out["destination_feels_like"] = None
    out["destination_humidity"] = df["humidity"]
    out["destination_weather"] = df["weather_description"]
    out["mobility_level"] = df["mobility_level"]
    out["polyline"] = None
    return out[UNIFIED_COLUMNS]


def load_tomtom_legacy() -> pd.DataFrame:
    df = pd.read_csv(LEGACY_TOMTOM_CSV)
    out = pd.DataFrame()
    out["timestamp"] = df["timestamp"]
    out["origin"] = df["origin"]
    out["destination"] = df["destination"]
    out["data_source"] = "tomtom"
    out["distance_km"] = df["distance_km"]
    out["travel_time_min"] = df["travel_time_min"]
    out["no_traffic_time_min"] = df["no_traffic_time_min"]
    out["traffic_delay_min"] = df["traffic_delay_min"]
    out["traffic_length_km"] = df["traffic_length_km"]
    out["average_speed_kmh"] = df["average_speed_kmh"]
    out["departure_time"] = df["departure_time"]
    out["arrival_time"] = df["arrival_time"]
    out["origin_temperature"] = df["origin_temperature"]
    out["origin_feels_like"] = df["origin_feels_like"]
    out["origin_humidity"] = df["origin_humidity"]
    out["origin_weather"] = df["origin_weather"]
    out["destination_temperature"] = df["destination_temperature"]
    out["destination_feels_like"] = df["destination_feels_like"]
    out["destination_humidity"] = df["destination_humidity"]
    out["destination_weather"] = df["destination_weather"]
    out["mobility_level"] = df["travel_time_min"].apply(
        lambda t: "Alta demora" if pd.notna(t) and t > HIGH_DELAY_THRESHOLD_MIN else "Movilidad normal"
    )
    out["polyline"] = None  # descartado en la fusión histórica, ver docstring
    return out[UNIFIED_COLUMNS]


def main():
    print("Fusionando histórico ORS (BD_BI_TFM) + TomTom (urban-mobility-analytics1)...")
    ors_df = load_ors_legacy()
    print(f"  ORS:    {len(ors_df)} filas")
    tomtom_df = load_tomtom_legacy()
    print(f"  TomTom: {len(tomtom_df)} filas")

    unified = pd.concat([ors_df, tomtom_df], ignore_index=True)
    unified = unified.sort_values("timestamp").reset_index(drop=True)
    print(f"  Total unificado: {len(unified)} filas")

    UNIFIED_CSV.parent.mkdir(parents=True, exist_ok=True)
    unified.to_csv(UNIFIED_CSV, index=False)
    print(f"CSV unificado escrito en: {UNIFIED_CSV}")

    records = unified.where(pd.notnull(unified), None).to_dict(orient="records")
    db = RouteDatabase(UNIFIED_CSV, UNIFIED_DB)
    if UNIFIED_DB.exists():
        UNIFIED_DB.unlink()
    db.init_sqlite()

    batch_size = 500
    for i in range(0, len(records), batch_size):
        db.save_records_to_sqlite(records[i:i + batch_size])
        print(f"  Insertadas {min(i + batch_size, len(records))}/{len(records)} filas en SQLite...")

    print(f"SQLite unificado escrito en: {UNIFIED_DB}")
    print("Listo.")


if __name__ == "__main__":
    main()
