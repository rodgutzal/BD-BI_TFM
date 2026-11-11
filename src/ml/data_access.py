"""Lectura de los datos que necesita el modelo, en SOLO LECTURA.

Abre la base con `immutable=1`: no crea archivos ni escribe (ni siquiera tablas vacías, que sí haría
RouteDatabase al inicializarse), y puede leerla aunque otro proceso la tenga abierta. Con el stack apagado.
"""

import sqlite3
from pathlib import Path

import pandas as pd

from src.locations import LOCATIONS


def _connect(db_path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(db_path).as_posix()}?immutable=1", uri=True)


def _read(db_path, sql: str) -> pd.DataFrame:
    conn = _connect(db_path)
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()


def load_pois(db_path) -> pd.DataFrame:
    """POIs de Overpass: category, subcategory, latitude, longitude."""
    return _read(db_path, "SELECT category, subcategory, latitude, longitude FROM pois")


def load_pois_foursquare(db_path) -> pd.DataFrame:
    """POIs de Foursquare (fuente independiente de OSM): category, subcategory, name, latitude, longitude."""
    try:
        return _read(db_path, "SELECT category, subcategory, name, latitude, longitude FROM pois_foursquare")
    except Exception:  # la tabla es opcional (requiere FOURSQUARE_API_KEY)
        return pd.DataFrame(columns=["category", "subcategory", "name", "latitude", "longitude"])


def load_context(db_path, directorio=None) -> pd.DataFrame:
    """Contexto de OSM (fase 1b) como POIs. Si se da `directorio` (JSON de tools/download_osm_context.py) se lee de
    ahí; si no, de la tabla `osm_context` del paquete de entrada (src/ml/inputs_bundle.py). Con la base completa y sin
    directorio no hay contexto y el resultado es un DataFrame vacío."""
    from src.ml import inputs_bundle, osm_context

    if directorio:
        return osm_context.load_context(directorio)
    return inputs_bundle.load_context_table(db_path)


def load_zone_table(db_path) -> pd.DataFrame:
    """Tabla por zona para las variables del modelo, indexada por nombre de zona:
      demanda            población (zone_demographics)
      tiempo_viaje_prom  tiempo de viaje medio de las rutas que tocan la zona (route_measurements), como una zona
                         'bien conectada' en src.location_scoring.zone_accessibility
    Una zona sin dato queda con NaN (no con 0)."""
    demografia = _read(db_path, "SELECT zone_name, population FROM zone_demographics")
    rutas = _read(
        db_path,
        "SELECT origin, destination, AVG(travel_time_min) AS tiempo FROM route_measurements "
        "GROUP BY origin, destination",
    )
    zonas = pd.DataFrame(index=pd.Index(list(LOCATIONS), name="zona"))
    zonas["demanda"] = demografia.set_index("zone_name")["population"].reindex(zonas.index).astype(float)
    tiempos = {}
    for zona in zonas.index:
        tocan = rutas[(rutas["origin"] == zona) | (rutas["destination"] == zona)]
        tiempos[zona] = float(tocan["tiempo"].mean()) if len(tocan) else float("nan")
    zonas["tiempo_viaje_prom"] = pd.Series(tiempos)
    return zonas
