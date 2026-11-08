"""Rejilla geográfica de ~250 m sobre el área de Malta que cubren las zonas monitorizadas.

Es la unidad del asistente de recomendación (ver docs/DISENO_ML_RECOMENDACION.md): cada celda recibe indicadores
de competencia, mercado y proveedores. La rejilla es FIJA (constantes, no depende de los datos) para que los
identificadores de celda sean estables entre ejecuciones y entre máquinas.

Geometría: 250 m en latitud son 250 / 111 320 grados; en longitud se corrige por el coseno de la latitud de
referencia (centro del área), así que las celdas son casi cuadradas. Fila 0 = sur, columna 0 = oeste.
"""

import math
from typing import Tuple

import numpy as np
import pandas as pd
from scipy import ndimage

CELL_SIZE_M = 250.0

# Extensión de la rejilla: abarca los POIs conocidos (lat 35,847-35,932; lon 14,446-14,572) con margen.
SOUTH, NORTH = 35.840, 35.940
WEST, EAST = 14.440, 14.580

_M_PER_DEG_LAT = 111_320.0
_REF_LAT = (SOUTH + NORTH) / 2
DLAT = CELL_SIZE_M / _M_PER_DEG_LAT
DLON = CELL_SIZE_M / (_M_PER_DEG_LAT * math.cos(math.radians(_REF_LAT)))
N_ROWS = math.ceil((NORTH - SOUTH) / DLAT)
N_COLS = math.ceil((EAST - WEST) / DLON)
SHAPE: Tuple[int, int] = (N_ROWS, N_COLS)

# Peso de cada anillo de vecindad al sumar indicadores: la celda cuenta entera, su vecindad inmediata (8 celdas
# alrededor, hasta ~250-350 m) a la mitad y el siguiente anillo (16 celdas, hasta ~500-700 m) a la cuarta parte.
RING_WEIGHTS = (1.0, 0.5, 0.25)


def cell_index(lat, lon):
    """(fila, columna) de cada punto; (-1, -1) si cae fuera de la rejilla o no tiene coordenadas válidas.

    Acepta escalares o arrays; devuelve arrays de enteros."""
    lat = np.atleast_1d(np.asarray(lat, dtype=float))
    lon = np.atleast_1d(np.asarray(lon, dtype=float))
    with np.errstate(invalid="ignore"):
        fila = np.floor((lat - SOUTH) / DLAT)
        col = np.floor((lon - WEST) / DLON)
        dentro = np.isfinite(fila) & np.isfinite(col) & (fila >= 0) & (fila < N_ROWS) & (col >= 0) & (col < N_COLS)
    return np.where(dentro, fila, -1).astype(int), np.where(dentro, col, -1).astype(int)


def cell_id(fila: int, col: int) -> str:
    """Identificador legible y estable: r{fila}c{columna}, p. ej. 'r23c20'."""
    return f"r{int(fila):02d}c{int(col):02d}"


def parse_cell_id(identificador: str) -> Tuple[int, int]:
    """Inversa de cell_id()."""
    if not (identificador.startswith("r") and "c" in identificador):
        raise ValueError(f"Identificador de celda no válido: {identificador!r}")
    fila, col = identificador[1:].split("c")
    return int(fila), int(col)


def cell_center(fila, col):
    """(latitud, longitud) del centro de la celda."""
    return SOUTH + (np.asarray(fila) + 0.5) * DLAT, WEST + (np.asarray(col) + 0.5) * DLON


def cells_frame() -> pd.DataFrame:
    """Todas las celdas de la rejilla: cell_id, fila, col, lat y lon del centro (una fila por celda)."""
    filas, cols = np.meshgrid(np.arange(N_ROWS), np.arange(N_COLS), indexing="ij")
    filas, cols = filas.ravel(), cols.ravel()
    lat, lon = cell_center(filas, cols)
    return pd.DataFrame({"cell_id": [cell_id(f, c) for f, c in zip(filas, cols)], "fila": filas, "col": cols,
                         "lat": lat, "lon": lon})


def count_grid(filas, cols) -> np.ndarray:
    """Matriz (N_ROWS, N_COLS) con cuántos puntos caen en cada celda. Ignora los índices -1 (fuera)."""
    filas, cols = np.asarray(filas), np.asarray(cols)
    ok = (filas >= 0) & (cols >= 0)
    contador = np.zeros(SHAPE, dtype=float)
    np.add.at(contador, (filas[ok], cols[ok]), 1.0)
    return contador


def ring_kernel(anillo: int) -> np.ndarray:
    """Núcleo de 1 y 0 que selecciona exactamente las celdas a distancia de Chebyshev `anillo`
    (0 = la propia celda, 1 = las 8 vecinas, 2 = las 16 siguientes)."""
    lado = 2 * anillo + 1
    idx = np.abs(np.arange(lado) - anillo)
    distancia = np.maximum(idx[:, None], idx[None, :])
    return (distancia == anillo).astype(float)


def ring_sum(grid: np.ndarray, anillo: int) -> np.ndarray:
    """Suma, para cada celda, de los valores de `grid` en el anillo `anillo` (los bordes cuentan como 0)."""
    return ndimage.convolve(grid, ring_kernel(anillo), mode="constant", cval=0.0)


def neighborhood_sum(grid: np.ndarray, weights=RING_WEIGHTS) -> np.ndarray:
    """Suma ponderada por anillos: weights[0] * celda + weights[1] * anillo 1 + weights[2] * anillo 2 ..."""
    total = np.zeros_like(grid, dtype=float)
    for anillo, peso in enumerate(weights):
        total += peso * ring_sum(grid, anillo)
    return total


def active_mask(total_grid: np.ndarray, anillo: int = 1) -> np.ndarray:
    """Celdas con algún POI (de cualquier categoría) en la celda o en su vecindad de `anillo` anillos.

    Sirve para dejar fuera el mar y el interior despoblado: sin edificios cartografiados (fase 1b) es la mejor
    aproximación a 'celda donde podría haber un negocio'."""
    activo = np.zeros(total_grid.shape, dtype=float)
    for a in range(anillo + 1):
        activo += ring_sum(total_grid, a)
    return activo > 0


def haversine_m(lat1, lon1, lat2, lon2):
    """Distancia en metros (vectorizable)."""
    p = math.pi / 180
    a = (np.sin((np.asarray(lat2) - lat1) * p / 2) ** 2
         + np.cos(np.asarray(lat1) * p) * np.cos(np.asarray(lat2) * p) * np.sin((np.asarray(lon2) - lon1) * p / 2) ** 2)
    return 2 * 6371000 * np.arcsin(np.sqrt(a))
