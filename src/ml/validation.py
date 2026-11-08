"""Validación espacial de los modelos de oferta esperada (protocolo fijado en docs/DISENO_ML_RECOMENDACION.md §4).

POR QUÉ ESPACIAL: celdas vecinas se parecen mucho (comparten POIs en sus vecindades). Una validación al azar pondría
celdas casi idénticas a ambos lados de la partición y daría números falsamente buenos. Aquí las celdas se agrupan en
BLOQUES de ~1 km (4×4 celdas) y todas las celdas de un bloque van juntas al entrenamiento o a la prueba. La
partición en bloques se repite varias veces con desplazamientos y asignaciones distintas.

QUÉ SE COMPARA: la desviación de Poisson media por celda (menos es mejor) de cada candidato frente a la MEJOR línea
base. La diferencia lleva un intervalo de confianza por *bootstrap de bloques* (se remuestrean bloques enteros, no
celdas, para respetar la dependencia espacial).

REGLA DE DECISIÓN (fijada de antemano): un candidato solo se publica si su desviación es MENOR que la de la mejor línea
base con el intervalo completo por debajo de 0. Si ninguno lo logra, no se publica puntaje de ML y se queda el MCDA
(resultado válido para el TFM).
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score

from src.ml import grid, models

BLOCK_CELLS = 4


def positions(index: Sequence[str]):
    """(filas, columnas) de una lista de cell_id."""
    pares = [grid.parse_cell_id(c) for c in index]
    return np.array([p[0] for p in pares], dtype=int), np.array([p[1] for p in pares], dtype=int)


def block_labels(filas, cols, offset=(0, 0), size: int = BLOCK_CELLS) -> np.ndarray:
    """Etiqueta entera del bloque (size × size celdas) de cada celda; `offset` desplaza la cuadrícula de bloques."""
    f = (np.asarray(filas) + offset[0]) // size
    c = (np.asarray(cols) + offset[1]) // size
    return (f * 1000 + c).astype(int)


def assign_folds(labels: np.ndarray, n_folds: int, rng: np.random.Generator) -> np.ndarray:
    """Pliegue (0..n_folds-1) de cada celda. Todas las celdas de un mismo bloque caen en el mismo pliegue y los
    bloques se reparten al azar de forma equilibrada."""
    unicos = np.unique(labels)
    orden = rng.permutation(len(unicos))
    pliegue_de = {b: int(orden[i] % n_folds) for i, b in enumerate(unicos)}
    return np.array([pliegue_de[b] for b in labels], dtype=int)


def poisson_deviance(y, mu) -> np.ndarray:
    """Desviación de Poisson de cada celda: 2·(y·ln(y/μ) − (y − μ)). Con y = 0 vale 2μ."""
    y, mu = np.asarray(y, dtype=float), np.clip(np.asarray(mu, dtype=float), models.MIN_ESPERADO, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        termino = np.where(y > 0, y * np.log(y / mu), 0.0)
    return 2.0 * (termino - (y - mu))


def precision_at_k(y_true, y_pred, k: int) -> float:
    """Fracción de las k celdas con más locales predichos que están entre las k con más locales reales."""
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    k = min(k, len(y_true))
    reales = set(np.argsort(-y_true, kind="stable")[:k])
    predichas = set(np.argsort(-y_pred, kind="stable")[:k])
    return len(reales & predichas) / k


def spearman(y_true, y_pred) -> float:
    if np.std(y_true) == 0 or np.std(y_pred) == 0:
        return float("nan")
    return float(stats.spearmanr(y_true, y_pred).statistic)


@dataclass
class Evaluation:
    """Resultado de una validación: predicciones fuera de muestra (R repeticiones × n celdas) por modelo."""
    nombres: List[str]
    y: np.ndarray
    oof: Dict[str, np.ndarray]
    bloques: np.ndarray                  # bloques de la cuadrícula SIN desplazar, para el bootstrap
    metricas: pd.DataFrame               # una fila por (modelo, repetición)
    k_top: int


def evaluate(X: pd.DataFrame, y, nombres: Sequence[str] = models.TODOS, repeats: int = 10, n_folds: int = 5,
             seed: int = 0, k_top: int = 50, progress: Optional[Callable[[int, int], None]] = None) -> Evaluation:
    """Validación cruzada espacial por bloques, repetida. `X` está indexada por cell_id; `y` es el conteo real."""
    y = np.asarray(y, dtype=float)
    filas, cols = positions(X.index)
    oof = {n: np.zeros((repeats, len(y))) for n in nombres}
    for r in range(repeats):
        rng = np.random.default_rng(seed + r)
        desplazamiento = (int(rng.integers(0, BLOCK_CELLS)), int(rng.integers(0, BLOCK_CELLS)))
        pliegues = assign_folds(block_labels(filas, cols, desplazamiento), n_folds, rng)
        for f in range(n_folds):
            test = pliegues == f
            train = ~test
            if test.sum() == 0 or train.sum() == 0:
                continue
            for n in nombres:
                oof[n][r, test] = models.fit_predict(n, X[train], y[train], X[test], seed=seed + r)
        if progress:
            progress(r + 1, repeats)
    filas_m = []
    for n in nombres:
        for r in range(repeats):
            filas_m.append({"modelo": n, "repeticion": r,
                            "desviacion": float(poisson_deviance(y, oof[n][r]).mean()),
                            "spearman": spearman(y, oof[n][r]), "precision_k": precision_at_k(y, oof[n][r], k_top)})
    return Evaluation(list(nombres), y, oof, block_labels(filas, cols), pd.DataFrame(filas_m), k_top)


def summarize(ev: Evaluation) -> pd.DataFrame:
    """Media y desviación entre repeticiones de cada métrica, por modelo, ordenado por desviación (mejor primero)."""
    g = ev.metricas.groupby("modelo")
    out = pd.DataFrame({
        "desviacion": g["desviacion"].mean(), "desviacion_sd": g["desviacion"].std(ddof=1),
        "spearman": g["spearman"].mean(), "precision_k": g["precision_k"].mean(),
    })
    return out.sort_values("desviacion")


def block_bootstrap_diff(y, mu_a, mu_b, bloques, n_boot: int = 2000, seed: int = 0, nivel: float = 0.95) -> dict:
    """Diferencia media por celda de la desviación de Poisson entre A y B (A − B; negativa = A es mejor), con
    intervalo por bootstrap de bloques: se remuestrean BLOQUES enteros con reemplazo."""
    return block_bootstrap_mean(poisson_deviance(y, mu_a) - poisson_deviance(y, mu_b), bloques, n_boot, seed, nivel)


def block_bootstrap_mean(d, bloques, n_boot: int = 2000, seed: int = 0, nivel: float = 0.95) -> dict:
    """Media por celda de `d` (diferencia de desviación por celda) con intervalo por bootstrap de bloques."""
    d = np.asarray(d, dtype=float)
    bloques = np.asarray(bloques)
    ids = np.unique(bloques)
    suma = np.array([d[bloques == b].sum() for b in ids])
    n_celdas = np.array([(bloques == b).sum() for b in ids])
    rng = np.random.default_rng(seed)
    medias = np.empty(n_boot)
    for i in range(n_boot):
        s = rng.integers(0, len(ids), len(ids))
        medias[i] = suma[s].sum() / n_celdas[s].sum()
    alfa = (1 - nivel) / 2
    return {"diferencia": float(d.mean()), "ic_inf": float(np.quantile(medias, alfa)),
            "ic_sup": float(np.quantile(medias, 1 - alfa))}


def deviance_per_cell(ev: Evaluation, nombre: str) -> np.ndarray:
    """Desviación de Poisson de cada celda para un modelo, calculada en CADA repetición y luego promediada (un modelo
    honesto cada vez; ver decide())."""
    return np.mean([poisson_deviance(ev.y, ev.oof[nombre][r]) for r in range(ev.oof[nombre].shape[0])], axis=0)


def compare_models(ev: Evaluation, a: str, b: str, n_boot: int = 2000, seed: int = 0) -> dict:
    """Diferencia de desviación por celda entre dos modelos (a − b; negativa = a es mejor), con IC por bootstrap de
    bloques y veredicto. Sirve para preguntas como '¿aporta algo el contexto?' (boosting frente a boosting_poi)."""
    r = block_bootstrap_mean(deviance_per_cell(ev, a) - deviance_per_cell(ev, b), ev.bloques, n_boot, seed)
    r["veredicto"] = "mejora" if r["ic_sup"] < 0 else ("peor" if r["ic_inf"] > 0 else "indistinguible")
    return r


def decide(ev: Evaluation, candidatos: Sequence[str] = models.CANDIDATOS, baselines: Sequence[str] = models.BASELINES,
           n_boot: int = 2000, seed: int = 0) -> dict:
    """Aplica la regla de decisión: ¿algún candidato supera a la mejor línea base con el intervalo por debajo de 0?

    Devuelve {mejor_baseline, comparaciones: {candidato: {diferencia, ic_inf, ic_sup, veredicto}}, ganador}.
    `ganador` es el candidato con menor desviación entre los que mejoran, o None (entonces NO se publica ML).

    IMPORTANTE: la desviación de cada celda se calcula en CADA repetición por separado (un modelo entrenado sin ver
    el bloque de esa celda) y después se promedia. NO se promedian antes las predicciones de varias repeticiones:
    eso convertiría a cada candidato en un conjunto de modelos, favorecería a los de alta varianza (el boosting)
    frente a las líneas base y haría depender el veredicto del número de repeticiones."""
    por_celda = {n: deviance_per_cell(ev, n) for n in ev.nombres}
    bases = [b for b in baselines if b in por_celda]
    mejor = min(bases, key=lambda b: por_celda[b].mean())
    comparaciones = {}
    for c in candidatos:
        if c not in por_celda:
            continue
        r = block_bootstrap_mean(por_celda[c] - por_celda[mejor], ev.bloques, n_boot, seed)
        r["veredicto"] = "mejora" if r["ic_sup"] < 0 else ("peor" if r["ic_inf"] > 0 else "indistinguible")
        comparaciones[c] = r
    mejoran = [c for c, r in comparaciones.items() if r["veredicto"] == "mejora"]
    ganador = min(mejoran, key=lambda c: por_celda[c].mean()) if mejoran else None
    return {"mejor_baseline": mejor, "comparaciones": comparaciones, "ganador": ganador}


def brecha_relativa(esperado, observado) -> np.ndarray:
    """Brecha de oferta en unidades de desviación típica: (esperado − observado) / √(esperado + 1).

    La brecha ABSOLUTA (esperado − observado) crece con el tamaño de la celda: en el centro más saturado, 18 locales
    observados frente a 62 esperados dan una brecha de +44, mayor que la de cualquier barrio tranquilo, aunque ahí
    haya competencia de sobra. La relativa (residuo de Pearson de un modelo de Poisson, con +1 para no explotar con
    esperados pequeños) compara celdas de tamaño distinto."""
    esperado, observado = np.asarray(esperado, dtype=float), np.asarray(observado, dtype=float)
    return (esperado - observado) / np.sqrt(esperado + 1.0)


# ---------------------------------------------------------------------------
# Contraste con una fuente independiente (Foursquare)
# ---------------------------------------------------------------------------

def auc_presence(score, presencia) -> float:
    """AUC de `score` para distinguir las celdas donde la fuente independiente tiene al menos un local. NaN si todas
    las celdas son iguales (no hay nada que distinguir)."""
    presencia = np.asarray(presencia).astype(bool)
    if presencia.all() or (~presencia).all():
        return float("nan")
    return float(roc_auc_score(presencia, np.asarray(score, dtype=float)))


def gap_artifact_share(brecha, osm, fsq, k: int) -> dict:
    """¿Cuántas de las k celdas con mayor brecha (esperado − observado en OSM) lo son porque OSM está INCOMPLETO?

    Se consideran 'posible artefacto de cartografía' las celdas donde la fuente independiente tiene más locales que
    OSM (`fsq > osm`): el supuesto déficit podría ser solo falta de mapeo. Se compara con la proporción de referencia
    entre todas las celdas que tienen algún local en alguna de las dos fuentes."""
    brecha, osm, fsq = (np.asarray(a, dtype=float) for a in (brecha, osm, fsq))
    k = min(k, len(brecha))
    top = np.argsort(-brecha, kind="stable")[:k]
    con_locales = (osm > 0) | (fsq > 0)
    return {"top_k": float((fsq[top] > osm[top]).mean()),
            "referencia": float((fsq[con_locales] > osm[con_locales]).mean()) if con_locales.any() else float("nan")}
