"""Contexto de OpenStreetMap descargado con tools/download_osm_context.py (fase 1b): edificios, alojamiento turístico,
transporte público e industria. Se lee de archivos JSON (NO de la base de datos) y se convierte al mismo formato que
los POIs (category, subcategory, latitude, longitude) para sumarlo a los conteos por celda.

Categorías nuevas (no son de `poi_client.CATEGORY_TAGS`):
  edificio     subcategoría = valor de la etiqueta `building` (yes, apartments, house, industrial...)
  alojamiento  subcategoría = valor de `tourism` (hotel, guest_house, hostel, apartment, ...)
  transporte   bus_stop, ferry, station y platform (las 'stop_position' se descartan: duplican la parada)
  industria    suelo industrial y mayoristas (industrial, wholesale)

LÍMITES que hay que declarar: la mayor parte de los edificios es `building=yes` (en Malta, ~78 %), así que no se
puede distinguir vivienda de comercio con precisión; 'residentes' se aproxima con los edificios que NO son claramente
no residenciales. El número de edificios es un proxy de superficie construida y población, no una medida de población.
"""

from pathlib import Path
from typing import List

import pandas as pd

CONTEXTO = ("edificio", "alojamiento", "transporte", "industria")

# Valores de `building` que claramente NO son vivienda (se excluyen al aproximar 'residentes').
NO_RESIDENCIALES = frozenset(
    {
        "industrial",
        "warehouse",
        "factory",
        "commercial",
        "retail",
        "office",
        "supermarket",
        "school",
        "kindergarten",
        "university",
        "college",
        "hospital",
        "clinic",
        "church",
        "chapel",
        "cathedral",
        "mosque",
        "synagogue",
        "temple",
        "religious",
        "civic",
        "public",
        "government",
        "fire_station",
        "police",
        "prison",
        "military",
        "roof",
        "garage",
        "garages",
        "carport",
        "shed",
        "service",
        "storage_tank",
        "transformer_tower",
        "greenhouse",
        "farm_auxiliary",
        "barn",
        "hangar",
        "parking",
        "train_station",
        "transportation",
        "toilets",
        "construction",
        "ruins",
        "fuel_station",
        "kiosk",
        "stable",
        "cowshed",
        "bunker",
        "tower",
        "silo",
        "water_tower",
    }
)

_TRANSPORTE_VALIDO = {"bus_stop", "ferry", "station", "platform"}


def _posicion(e: dict):
    if e.get("type") == "node":
        return e.get("lat"), e.get("lon")
    centro = e.get("center") or {}
    return centro.get("lat"), centro.get("lon")


def _tipo_transporte(tags: dict) -> str:
    if tags.get("highway") == "bus_stop":
        return "bus_stop"
    if tags.get("amenity") == "ferry_terminal":
        return "ferry"
    if tags.get("railway") in ("station", "halt", "tram_stop"):
        return "station"
    valor = tags.get("public_transport")
    return "platform" if valor in ("platform", "station") else "stop_position"


def _fila(categoria: str, subcategoria: str, elemento: dict):
    lat, lon = _posicion(elemento)
    if lat is None or lon is None:
        return None
    return {"category": categoria, "subcategory": subcategoria, "latitude": float(lat), "longitude": float(lon)}


def elements_to_pois(tema: str, elementos: List[dict]) -> pd.DataFrame:
    """Convierte los elementos de Overpass de un tema al formato de POIs. Descarta los que no tienen coordenadas."""
    filas = []
    for e in elementos:
        tags = e.get("tags", {})
        if tema == "edificios":
            fila = _fila("edificio", str(tags.get("building", "yes")), e)
        elif tema == "alojamiento":
            fila = _fila("alojamiento", str(tags.get("tourism", "")), e)
        elif tema == "transporte":
            tipo = _tipo_transporte(tags)
            fila = _fila("transporte", tipo, e) if tipo in _TRANSPORTE_VALIDO else None
        elif tema == "industria":
            fila = _fila("industria", "wholesale" if tags.get("shop") == "wholesale" else "industrial", e)
        else:
            fila = None  # p. ej. suelo_residencial: no se usa (los edificios lo cubren mejor)
        if fila:
            filas.append(fila)
    return pd.DataFrame(filas, columns=["category", "subcategory", "latitude", "longitude"])


def load_context(directorio) -> pd.DataFrame:
    """Lee todos los JSON de `directorio` (los que escribe tools/download_osm_context.py) y devuelve el contexto como
    POIs. Un directorio sin archivos válidos da un DataFrame vacío."""
    import json

    partes = []
    for archivo in sorted(Path(directorio).glob("*.json")):
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        partes.append(elements_to_pois(datos.get("tema", ""), datos.get("elements", [])))
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame(columns=["category", "subcategory", "latitude", "longitude"])
    return pd.concat(partes, ignore_index=True)
