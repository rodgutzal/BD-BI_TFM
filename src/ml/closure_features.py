"""Variables de entrada del estudio de riesgo de cierre (fase 4). Protocolo: sección 3.M, «Variables principales», de
`docs/DISENO_ML_RECOMENDACION.md`.

TODAS salen de la foto del instante de partida (2022; 2024 en el control): **ninguna del estado actual**, ni el tiempo de
viaje, ni la población por zona, ni el contexto estático actual (es posterior al resultado). Funciones puras sobre listas de
elementos de OpenStreetMap, sin leer archivos (la lectura verificada es `tools/build_closure_labels.fotos_verificadas`).

Variables por local:
- categoría (7, una columna por categoría: `cat_<categoria>`);
- número de locales de la MISMA categoría y TOTALES a 250 m y a 500 m (sin contar el propio local) sobre todos los elementos
  de las siete categorías del instante de partida, con o sin nombre, excluidos los locales vacíos (`shop=vacant`,
  `disused=yes`, `abandoned=yes`, `vacant=yes`): `n_misma_250`, `n_total_250`, `n_misma_500`, `n_total_500`;
- distancia (m) al más cercano de la misma categoría, con máximo de 1.000 (`dist_misma_m`);
- si el nombre normalizado se repite ≥ 3 veces en esa foto (`cadena`, 0/1).

Interpretaciones de detalle (fijadas al escribir el código, antes de ejecutar el estudio; se declaran en el protocolo): los radios
son inclusivos (≤ 250 m, ≤ 500 m, igual que el ≤ 60 m de las etiquetas); «el más cercano de la misma categoría» es el elemento
más cercano distinto del propio y, si no hay ninguno a ≤ 1.000 m, vale 1.000; «se repite ≥ 3 veces» cuenta los elementos del
universo con ese nombre normalizado, incluido el propio.
"""

from typing import Dict, Iterable, Tuple

import numpy as np
import pandas as pd

from src.ml import closure_labels as cl
from src.ml import grid
from src.poi_client import CATEGORY_TAGS

CATEGORIAS = tuple(CATEGORY_TAGS)  # las siete, en el orden del recolector
RADIOS_M = (250.0, 500.0)
DISTANCIA_MAXIMA_M = 1000.0
MIN_REPETICIONES_CADENA = 3

COLUMNAS_CATEGORIA = tuple(f"cat_{c}" for c in CATEGORIAS)
COLUMNAS_DENSIDAD = ("n_misma_250", "n_total_250", "n_misma_500", "n_total_500")
COLUMNAS_NUMERICAS = COLUMNAS_DENSIDAD + ("dist_misma_m",)
COLUMNA_CADENA = "cadena"
COLUMNAS = COLUMNAS_CATEGORIA + COLUMNAS_NUMERICAS + (COLUMNA_CADENA,)


def universo(elementos: Iterable[dict]) -> pd.DataFrame:
    """Todos los elementos únicos del instante en las siete categorías, con coordenadas y que no sean locales vacíos (con o
    sin nombre): lo que cuenta como «competencia y densidad» en el entorno de un local."""
    filas = []
    for k, e in cl._unicos(elementos).items():
        tags = e.get("tags") if isinstance(e.get("tags"), dict) else {}
        cat, p = cl.categoria(tags), cl.punto(e)
        if cat is None or p is None or cl.es_local_vacio(tags):
            continue
        filas.append(
            {
                "tipo": k[0],
                "id": k[1],
                "lat": p[0],
                "lon": p[1],
                "categoria": cat,
                "nombre_norm": cl.normalizar_nombre(tags.get("name")),
            }
        )
    return pd.DataFrame(filas, columns=["tipo", "id", "lat", "lon", "categoria", "nombre_norm"])


def variables(poblacion: pd.DataFrame, elementos_del_instante: Iterable[dict]) -> pd.DataFrame:
    """Variables de cada local de `poblacion` (tabla de `closure_labels.poblacion_2022`/`etiquetar`), en el mismo orden. Los
    locales de la población deben pertenecer al universo (pasan los mismos filtros)."""
    u = universo(elementos_del_instante)
    posicion_en_u: Dict[Tuple[str, int], int] = {(t, i): n for n, (t, i) in enumerate(zip(u["tipo"], u["id"]))}
    faltan = [(t, i) for t, i in zip(poblacion["tipo"], poblacion["id"]) if (t, i) not in posicion_en_u]
    if faltan:
        raise ValueError(
            f"{len(faltan)} locales de la población no están en el universo del instante: p. ej. {faltan[:3]}"
        )
    propio = np.array([posicion_en_u[(t, i)] for t, i in zip(poblacion["tipo"], poblacion["id"])], dtype=int)
    n_p = len(poblacion)
    d = np.asarray(
        grid.haversine_m(
            poblacion["lat"].to_numpy()[:, None],
            poblacion["lon"].to_numpy()[:, None],
            u["lat"].to_numpy()[None, :],
            u["lon"].to_numpy()[None, :],
        ),
        dtype=float,
    )
    d[np.arange(n_p), propio] = np.inf  # el propio local no cuenta
    misma = poblacion["categoria"].to_numpy()[:, None] == u["categoria"].to_numpy()[None, :]
    out = pd.DataFrame(index=range(n_p))
    for c, columna in zip(CATEGORIAS, COLUMNAS_CATEGORIA):
        out[columna] = (poblacion["categoria"].to_numpy() == c).astype(float)
    for r in RADIOS_M:
        dentro = d <= r
        out[f"n_misma_{int(r)}"] = (dentro & misma).sum(axis=1).astype(float)
        out[f"n_total_{int(r)}"] = dentro.sum(axis=1).astype(float)
    out["dist_misma_m"] = np.minimum(np.where(misma, d, np.inf).min(axis=1), DISTANCIA_MAXIMA_M)
    repeticiones = u.loc[u["nombre_norm"] != "", "nombre_norm"].value_counts()
    out[COLUMNA_CADENA] = (
        poblacion["nombre_norm"].map(repeticiones).fillna(0).to_numpy() >= MIN_REPETICIONES_CADENA
    ).astype(float)
    return out[list(COLUMNAS)]
