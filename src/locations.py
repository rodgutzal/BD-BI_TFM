"""Configuración centralizada de ubicaciones y rutas en Malta.

Fusiona las ubicaciones/rutas de BD_BI_TFM (hub Msida + Valletta, vía
OpenRouteService) y de urban-mobility-analytics1 (hub Msida, vía TomTom).
Todas las coordenadas usan como referencia el dataclass `Location` del
segundo repo (más centralizado y consistente); las rutas son la UNIÓN de
ambos proyectos para no perder histórico ni cobertura de ninguno de los dos.
"""

from dataclasses import dataclass


@dataclass
class Location:
    """Representa una ubicación geográfica."""
    name: str
    latitude: float
    longitude: float


LOCATIONS = {
    "Msida": Location("Msida", 35.8970, 14.4890),
    "Gzira": Location("Gzira", 35.9059, 14.4950),
    "Sliema": Location("Sliema", 35.9122, 14.5040),
    "Valletta": Location("Valletta", 35.8989, 14.5146),
    "St Julian's": Location("St Julian's", 35.9181, 14.4898),
    "Birkirkara": Location("Birkirkara", 35.8972, 14.4611),
    "Marsaskala": Location("Marsaskala", 35.8620, 14.5670),
}


# Rutas de urban-mobility-analytics1 (hub Msida, todas cubiertas por TomTom)
_ROUTES_URBAN_MOBILITY = [
    ("Msida", "Gzira"),
    ("Msida", "Sliema"),
    ("Msida", "Valletta"),
    ("Msida", "St Julian's"),
    ("Msida", "Birkirkara"),
    ("Msida", "Marsaskala"),
]

# Rutas adicionales de BD_BI_TFM (hub Msida/Valletta, originalmente ORS)
# que no estaban ya cubiertas por la lista anterior.
_ROUTES_BD_BI_TFM_EXTRA = [
    ("Valletta", "Marsaskala"),
    ("Valletta", "Sliema"),
    ("Valletta", "Birkirkara"),
    ("Sliema", "St Julian's"),
    ("Birkirkara", "Valletta"),
    ("Marsaskala", "Valletta"),
]

# Unión de ambos proyectos, sin duplicados, preservando orden.
ROUTES = _ROUTES_URBAN_MOBILITY + _ROUTES_BD_BI_TFM_EXTRA


def get_location(name: str) -> Location:
    """Obtiene una ubicación por nombre."""
    if name not in LOCATIONS:
        raise ValueError(f"Unknown location: {name}")
    return LOCATIONS[name]


def get_all_unique_locations() -> dict[str, Location]:
    """Retorna todas las ubicaciones únicas usadas en las rutas."""
    unique = {}
    for origin_name, destination_name in ROUTES:
        if origin_name not in unique:
            unique[origin_name] = get_location(origin_name)
        if destination_name not in unique:
            unique[destination_name] = get_location(destination_name)
    return unique
