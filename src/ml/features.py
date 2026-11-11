"""Variables por celda para el modelo de oferta esperada (fase 1), con CONTROL DE FUGA.

El modelo predice cuántos locales de una categoría objetivo hay en una celda a partir de su contexto. Si el contexto
incluyera la propia categoría objetivo (en la celda o en la vecindad), el modelo solo copiaría la etiqueta. Por eso
`build_features(counts, target)` EXCLUYE de todas las variables los POIs que cumplan el objetivo.

Variables (por celda):
  <categoria>_celda, <categoria>_anillo1, <categoria>_anillo2   POIs de cada categoría de Overpass en la celda y en
                                                                 los anillos 1 y 2 (sin el objetivo)
  dist_centro_m                    distancia al centro de zona más cercano
  pob_suavizada                    población de las zonas, promediada con un núcleo gaussiano (sigma 1.500 m)
  tiempo_viaje_suavizado           tiempo de viaje medio de las rutas de las zonas, promediado igual (accesibilidad)
Las dos últimas son NaN si no se pasa `zones` (demografía y rutas se leen con src.location_scoring).
"""

from typing import Optional, Sequence

import numpy as np
import pandas as pd

from src.locations import LOCATIONS
from src.ml import grid
from src.ml.cell_counts import CellCounts, Selector

CATEGORIAS = ("school", "hospital", "food_drink", "leisure", "sport", "mall", "business")
SIGMA_M = 1500.0


def target_counts(counts: CellCounts, target: Sequence[Selector], mask: Optional[np.ndarray] = None) -> pd.Series:
    """Número de POIs del objetivo EN cada celda (sin vecindad): la variable que el modelo intenta predecir."""
    if mask is None:
        mask = counts.active_mask()
    filas, cols = np.nonzero(mask)
    valores = counts.grid(target)[filas, cols]
    return pd.Series(
        valores, index=pd.Index([grid.cell_id(f, c) for f, c in zip(filas, cols)], name="cell_id"), name="objetivo"
    )


def _kernel_zonas(lat, lon, valores: pd.Series) -> np.ndarray:
    """Promedio de `valores` (indexado por zona) ponderado por un núcleo gaussiano de la distancia a cada zona.
    Las zonas sin valor se omiten y los pesos se renormalizan."""
    nombres = [z for z in LOCATIONS if z in valores.index and pd.notna(valores[z])]
    if not nombres:
        return np.full(len(lat), np.nan)
    pesos = np.stack(
        [
            np.exp(-(grid.haversine_m(LOCATIONS[z].latitude, LOCATIONS[z].longitude, lat, lon) ** 2) / (2 * SIGMA_M**2))
            for z in nombres
        ]
    )
    v = np.array([float(valores[z]) for z in nombres])[:, None]
    suma = pesos.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(suma > 0, (pesos * v).sum(axis=0) / suma, np.nan)


def build_features(
    counts: CellCounts,
    target: Sequence[Selector],
    zones: Optional[pd.DataFrame] = None,
    mask: Optional[np.ndarray] = None,
    categorias: Sequence[str] = CATEGORIAS,
) -> pd.DataFrame:
    """Variables de cada celda activa (o de `mask`), sin ningún POI del objetivo. Ver el docstring del módulo.

    `zones`: DataFrame indexado por nombre de zona con columnas `demanda` (población) y `tiempo_viaje_prom`
    (src.location_scoring.zone_demand / zone_accessibility).
    `categorias`: qué categorías se cuentan. Por defecto las 7 de Overpass; con el contexto de la fase 1b se pueden
    añadir `edificio`, `alojamiento`, `transporte` e `industria` (src.ml.osm_context.CONTEXTO)."""
    if mask is None:
        mask = counts.active_mask()
    filas, cols = np.nonzero(mask)
    cols_out = {}
    for categoria in categorias:
        matriz = counts.grid([Selector(categoria)], exclude=target)
        cols_out[f"{categoria}_celda"] = grid.ring_sum(matriz, 0)[filas, cols]
        cols_out[f"{categoria}_anillo1"] = grid.ring_sum(matriz, 1)[filas, cols]
        cols_out[f"{categoria}_anillo2"] = grid.ring_sum(matriz, 2)[filas, cols]
    lat, lon = grid.cell_center(filas, cols)
    distancias = np.stack([grid.haversine_m(z.latitude, z.longitude, lat, lon) for z in LOCATIONS.values()])
    cols_out["dist_centro_m"] = distancias.min(axis=0)
    if zones is not None and "demanda" in zones:
        cols_out["pob_suavizada"] = _kernel_zonas(lat, lon, zones["demanda"])
    else:
        cols_out["pob_suavizada"] = np.full(len(filas), np.nan)
    if zones is not None and "tiempo_viaje_prom" in zones:
        cols_out["tiempo_viaje_suavizado"] = _kernel_zonas(lat, lon, zones["tiempo_viaje_prom"])
    else:
        cols_out["tiempo_viaje_suavizado"] = np.full(len(filas), np.nan)
    return pd.DataFrame(cols_out, index=pd.Index([grid.cell_id(f, c) for f, c in zip(filas, cols)], name="cell_id"))
