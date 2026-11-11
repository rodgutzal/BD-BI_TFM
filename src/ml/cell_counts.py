"""Conteos de POIs por celda y por (categoría, subcategoría) de OpenStreetMap.

Es la tabla base del asistente: todo indicador (competencia, mercado, proveedores) y toda variable del modelo
sale de sumar subcategorías sobre esta tabla. Como son sumas sobre matrices precalculadas, recalcular un
indicador cuando el usuario ajusta su perfil de negocio es barato (no hay que volver a leer la base).
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.ml import grid
from src.ml.osm_context import CONTEXTO


@dataclass(frozen=True)
class Selector:
    """Qué POIs cuentan: una categoría de Overpass y, opcionalmente, un subconjunto de sus subcategorías.

    `Selector("food_drink")` = cualquier subcategoría de food_drink; `Selector("business", frozenset({"bakery"}))`
    = solo las panaderías; `Selector("business", None, frozenset({"company"}))` = todo `business` salvo `company`."""

    category: str
    subcategories: Optional[FrozenSet[str]] = None
    excluding: Optional[FrozenSet[str]] = None

    def matches(self, category: str, subcategory: str) -> bool:
        return (
            category == self.category
            and (self.subcategories is None or subcategory in self.subcategories)
            and (self.excluding is None or subcategory not in self.excluding)
        )


def selector(category: str, *subcategories: str) -> Selector:
    """Atajo: selector('business', 'bakery', 'pastry')."""
    return Selector(category, frozenset(subcategories) if subcategories else None)


def selector_except(category: str, *excluidas: str) -> Selector:
    """Atajo: toda la categoría salvo las subcategorías indicadas."""
    return Selector(category, None, frozenset(excluidas))


class CellCounts:
    """Matrices (N_ROWS, N_COLS) de conteos, una por (categoría, subcategoría) presente en los datos."""

    def __init__(self, arrays: Dict[Tuple[str, str], np.ndarray], n_fuera: int = 0, n_total: int = 0):
        self.arrays = arrays
        self.n_fuera = n_fuera  # POIs con coordenadas fuera de la rejilla (auditoría)
        self.n_total = n_total

    @classmethod
    def from_pois(cls, pois: pd.DataFrame) -> "CellCounts":
        """Construye los conteos desde un DataFrame con columnas category, subcategory, latitude y longitude
        (el que devuelve RouteDatabase.get_pois()). Filas sin categoría o sin coordenadas se descartan; una
        subcategoría vacía se cuenta como ''."""
        if pois is None or pois.empty:
            return cls({}, 0, 0)
        df = pois.dropna(subset=["category"]).copy()
        df["subcategory"] = df["subcategory"].fillna("").astype(str) if "subcategory" in df else ""
        filas, cols = grid.cell_index(df["latitude"].to_numpy(), df["longitude"].to_numpy())
        dentro = filas >= 0
        arrays: Dict[Tuple[str, str], np.ndarray] = {}
        clave = list(zip(df["category"].astype(str), df["subcategory"]))
        por_clave: Dict[Tuple[str, str], list] = {}
        for i, k in enumerate(clave):
            if dentro[i]:
                por_clave.setdefault(k, []).append(i)
        for k, indices in por_clave.items():
            arrays[k] = grid.count_grid(filas[indices], cols[indices])
        return cls(arrays, int((~dentro).sum()), len(df))

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> "CellCounts":
        """Inversa de `to_frame`: reconstruye los conteos desde la tabla celda × (categoría|subcategoría). Las celdas
        que no están en la tabla quedan en 0. Es lo que permite al dashboard recalcular las lentes con el perfil que
        ajuste el usuario sin la base de datos."""
        arrays: Dict[Tuple[str, str], np.ndarray] = {}
        posiciones = [grid.parse_cell_id(i) for i in frame.index]
        filas = np.array([p[0] for p in posiciones], dtype=int)
        cols = np.array([p[1] for p in posiciones], dtype=int)
        for columna in frame.columns:
            categoria, _, subcategoria = str(columna).partition("|")
            matriz = np.zeros(grid.SHAPE, dtype=float)
            matriz[filas, cols] = frame[columna].to_numpy(dtype=float)
            arrays[(categoria, subcategoria)] = matriz
        return cls(arrays, 0, int(sum(m.sum() for m in arrays.values())))

    def pairs(self):
        return sorted(self.arrays)

    def grid(self, selectors: Iterable[Selector], exclude: Sequence[Selector] = ()) -> np.ndarray:
        """Suma de las matrices de todo (categoría, subcategoría) que cumpla algún selector de `selectors` y
        ningún selector de `exclude`. Sin coincidencias devuelve una matriz de ceros."""
        selectors, exclude = tuple(selectors), tuple(exclude)
        total = np.zeros(grid.SHAPE, dtype=float)
        for (cat, sub), arr in self.arrays.items():
            if any(s.matches(cat, sub) for s in selectors) and not any(e.matches(cat, sub) for e in exclude):
                total += arr
        return total

    def total_grid(self) -> np.ndarray:
        return self.grid([Selector(c) for c in {cat for cat, _ in self.arrays}])

    def active_mask(self, anillo: int = 1) -> np.ndarray:
        """Celdas activas: con algún POI de Overpass en la celda o su vecindad. NO cuentan las categorías de contexto
        (edificio, alojamiento, transporte, industria): así el conjunto de celdas es el mismo con o sin ese contexto y
        los resultados de antes y después son comparables."""
        pois = CellCounts({k: v for k, v in self.arrays.items() if k[0] not in CONTEXTO})
        return grid.active_mask(pois.total_grid(), anillo)

    def count_in_area(self, selectors: Iterable[Selector], exclude: Sequence[Selector] = ()) -> int:
        """Cuántos POIs hay en toda la rejilla que cumplan los selectores (y ninguno de `exclude`), para saber si
        una lente tiene datos."""
        return int(self.grid(selectors, exclude).sum())

    def to_frame(self, mask: Optional[np.ndarray] = None) -> pd.DataFrame:
        """Tabla celda × (categoría|subcategoría): una fila por celda (solo las de `mask` si se da) y una columna
        por par. Es la 'tabla precalculada' que consumirá el dashboard."""
        seleccion = np.ones(grid.SHAPE, dtype=bool) if mask is None else mask
        filas, cols = np.nonzero(seleccion)
        datos = {f"{cat}|{sub}": self.arrays[(cat, sub)][filas, cols] for cat, sub in self.pairs()}
        out = pd.DataFrame(datos, index=[grid.cell_id(f, c) for f, c in zip(filas, cols)])
        out.index.name = "cell_id"
        return out.astype(int) if not out.empty else out
