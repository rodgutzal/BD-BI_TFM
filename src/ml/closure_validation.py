"""Validación del estudio de riesgo de cierre (fase 4). Implementa, SIN ninguna decisión nueva, la sección 3.M de
`docs/DISENO_ML_RECOMENDACION.md`: modelos y líneas base fijados, validación espacial por bloques (la de la fase 1), AUC por
repetición, intervalos por remuestreo de bloques y la regla de decisión.

- **Candidatos:** `logistica` (variables numéricas estandarizadas, categoría una-columna-por-categoría, L2 por defecto, `C=1,0`,
  `max_iter=2000`) y `boosting` (`GradientBoostingClassifier`, 150 árboles, profundidad 2, tasa 0,05, `subsample=0,8`,
  `min_samples_leaf=10`, `random_state` = la semilla de la repetición). Sin ajuste de hiperparámetros.
- **Líneas base triviales:** `solo_categoria` (tasa de cierre de cada categoría en el entrenamiento de cada pliegue) y
  `solo_densidad` (logística con solo los cuatro recuentos a 250/500 m, con `log(1+n)`); la constante vale AUC 0,5.
- **Validación:** 10 repeticiones; en cada una, la cuadrícula de bloques de 1 km se desplaza al azar y los bloques se reparten
  al azar en 5 pliegues (`validation.block_labels` y `validation.assign_folds`, con el mismo patrón de semillas que la fase 1:
  `default_rng(semilla + r)`, dos desplazamientos con `integers(0, 4)` y el mismo `rng` para los pliegues). **El AUC se calcula
  en cada repetición con todas las probabilidades fuera de muestra de esa repetición y después se promedia**; no se promedian
  las predicciones.
- **Intervalo:** remuestreo de BLOQUES de la cuadrícula SIN desplazar (2.000 réplicas); en cada réplica se recalcula el AUC de
  cada repetición con los locales de los bloques remuestreados y se promedia. Nivel 97,5 % (Bonferroni, dos candidatos):
  percentiles 1,25 y 98,75. La mejor línea base trivial se elige UNA vez con todos los datos (mayor AUC medio; empate → la
  de categoría) y la diferencia se mide pareada, con el mismo remuestreo.
- **Regla de decisión:** una señal es utilizable si AL MENOS UN candidato cumple (a) límite inferior del IC del AUC > 0,5 y
  (b) límite inferior del IC de la diferencia con la mejor línea base trivial > 0.

Interpretaciones de detalle (fijadas al escribir el código, antes de ejecutar el estudio; se declaran en el protocolo): las
cinco variables numéricas (cuatro recuentos y la distancia) se estandarizan y la de cadena (0/1) y las de categoría no; la
línea base de densidad estandariza `log(1+n)` y usa los mismos hiperparámetros que la logística; una categoría que no aparece
en el entrenamiento de un pliegue recibe la tasa global de ese entrenamiento; el remuestreo usa la semilla 0.
"""

from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.ml import closure_features as cf
from src.ml import validation

CANDIDATOS = ("logistica", "boosting")
LINEAS_BASE = ("solo_categoria", "solo_densidad")
MODELOS = CANDIDATOS + LINEAS_BASE

N_REPETICIONES = 10
N_PLIEGUES = 5
N_REMUESTREOS = 2000
NIVEL = 0.975  # 97,5 % por candidato (Bonferroni con dos candidatos)
SEMILLA = 0
MIN_POSITIVOS_DESCRIPTIVOS = 30  # las sensibilidades y el control solo se ejecutan con al menos 30 positivos

PARAMETROS_LOGISTICA = {"C": 1.0, "max_iter": 2000}  # NO se pasa `penalty` (deprecado en scikit-learn 1.8)
PARAMETROS_BOOSTING = {
    "n_estimators": 150,
    "max_depth": 2,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "min_samples_leaf": 10,
}


def _estandarizar(entrenamiento: np.ndarray, prueba: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    escala = StandardScaler().fit(entrenamiento)
    return escala.transform(entrenamiento), escala.transform(prueba)


def ajustar_predecir(nombre: str, X_ent: pd.DataFrame, y_ent, X_prueba: pd.DataFrame, semilla: int) -> np.ndarray:
    """Probabilidad de cierre de cada fila de `X_prueba` con el modelo `nombre` entrenado en `X_ent`."""
    y_ent = np.asarray(y_ent, dtype=int)
    if nombre == "logistica":
        num_e, num_p = _estandarizar(
            X_ent[list(cf.COLUMNAS_NUMERICAS)].to_numpy(), X_prueba[list(cf.COLUMNAS_NUMERICAS)].to_numpy()
        )
        resto = list(cf.COLUMNAS_CATEGORIA) + [cf.COLUMNA_CADENA]
        Z_e = np.hstack([num_e, X_ent[resto].to_numpy()])
        Z_p = np.hstack([num_p, X_prueba[resto].to_numpy()])
        return LogisticRegression(**PARAMETROS_LOGISTICA).fit(Z_e, y_ent).predict_proba(Z_p)[:, 1]
    if nombre == "boosting":
        modelo = GradientBoostingClassifier(random_state=semilla, **PARAMETROS_BOOSTING)
        return modelo.fit(X_ent[list(cf.COLUMNAS)].to_numpy(), y_ent).predict_proba(
            X_prueba[list(cf.COLUMNAS)].to_numpy()
        )[:, 1]
    if nombre == "solo_categoria":
        global_ = float(y_ent.mean())
        tasas = []
        for c in cf.COLUMNAS_CATEGORIA:
            en_c = X_ent[c].to_numpy() == 1
            tasas.append(float(y_ent[en_c].mean()) if en_c.any() else global_)
        return X_prueba[list(cf.COLUMNAS_CATEGORIA)].to_numpy() @ np.array(tasas)
    if nombre == "solo_densidad":
        logs_e = np.log1p(X_ent[list(cf.COLUMNAS_DENSIDAD)].to_numpy())
        logs_p = np.log1p(X_prueba[list(cf.COLUMNAS_DENSIDAD)].to_numpy())
        Z_e, Z_p = _estandarizar(logs_e, logs_p)
        return LogisticRegression(**PARAMETROS_LOGISTICA).fit(Z_e, y_ent).predict_proba(Z_p)[:, 1]
    raise ValueError(f"Modelo desconocido: {nombre!r}")


def validar(
    X: pd.DataFrame,
    y,
    filas,
    cols,
    nombres: Sequence[str] = MODELOS,
    repeticiones: int = N_REPETICIONES,
    pliegues: int = N_PLIEGUES,
    semilla: int = SEMILLA,
) -> Dict[str, np.ndarray]:
    """Validación cruzada espacial por bloques, repetida: `{modelo: matriz (repeticiones × n locales)}` de probabilidades FUERA
    de muestra. `filas`/`cols` son la celda de cada local. Mismo patrón de semillas y de bloques que la fase 1."""
    y = np.asarray(y, dtype=int)
    if len(y) != len(X):
        raise ValueError("X e y tienen longitudes distintas")
    X = X.reset_index(drop=True)
    oof = {n: np.full((repeticiones, len(y)), np.nan) for n in nombres}
    for r in range(repeticiones):
        rng = np.random.default_rng(semilla + r)
        desplazamiento = (int(rng.integers(0, validation.BLOCK_CELLS)), int(rng.integers(0, validation.BLOCK_CELLS)))
        pliegue_de = validation.assign_folds(validation.block_labels(filas, cols, desplazamiento), pliegues, rng)
        for f in range(pliegues):
            prueba = pliegue_de == f
            ent = ~prueba
            if prueba.sum() == 0 or ent.sum() == 0:
                continue
            if len(np.unique(y[ent])) < 2:
                raise ValueError("Un pliegue de entrenamiento tiene una sola clase: no se puede ajustar")
            for n in nombres:
                oof[n][r, prueba] = ajustar_predecir(n, X[ent], y[ent], X[prueba], semilla + r)
    for n in nombres:
        if np.isnan(oof[n]).any():
            raise ValueError(f"Faltan predicciones fuera de muestra del modelo {n}")
    return oof


def auc_por_filas(y, P: np.ndarray) -> np.ndarray:
    """AUC de cada fila de `P` (una repetición) contra `y`, con la fórmula de rangos (empates con rango medio). Devuelve NaN
    si `y` tiene una sola clase."""
    y = np.asarray(y, dtype=int)
    positivos = y == 1
    n1, n0 = int(positivos.sum()), int((~positivos).sum())
    P = np.atleast_2d(P)
    if n1 == 0 or n0 == 0:
        return np.full(P.shape[0], np.nan)
    rangos = rankdata(P, axis=1)
    return (rangos[:, positivos].sum(axis=1) - n1 * (n1 + 1) / 2) / (n1 * n0)


def auc_medio(y, P: np.ndarray) -> float:
    """AUC calculado en cada repetición y DESPUÉS promediado (no se promedian las predicciones)."""
    return float(np.mean(auc_por_filas(y, P)))


def remuestrear_por_bloques(
    y, oof: Dict[str, np.ndarray], bloques, n_remuestreos: int = N_REMUESTREOS, semilla: int = SEMILLA
) -> Tuple[Dict[str, np.ndarray], int]:
    """AUC medio de cada modelo en cada réplica de bloques remuestreados (con reemplazo; cuadrícula SIN desplazar). Devuelve
    ({modelo: array de n_remuestreos}, réplicas descartadas por tener una sola clase)."""
    y = np.asarray(y, dtype=int)
    bloques = np.asarray(bloques)
    unicos, inverso = np.unique(bloques, return_inverse=True)
    indices = [np.flatnonzero(inverso == k) for k in range(len(unicos))]
    rng = np.random.default_rng(semilla)
    salida = {n: np.full(n_remuestreos, np.nan) for n in oof}
    for b in range(n_remuestreos):
        elegidos = rng.integers(0, len(unicos), len(unicos))
        idx = np.concatenate([indices[k] for k in elegidos])
        for n, P in oof.items():
            salida[n][b] = auc_medio(y[idx], P[:, idx])
    validas = ~np.isnan(next(iter(salida.values())))
    return {n: v[validas] for n, v in salida.items()}, int((~validas).sum())


def intervalo(valores: np.ndarray, nivel: float = NIVEL) -> Tuple[float, float]:
    """Intervalo percentil de las réplicas (nivel 0,975 → percentiles 1,25 y 98,75)."""
    return (
        float(np.percentile(valores, 100 * (1 - nivel) / 2)),
        float(np.percentile(valores, 100 * (1 + nivel) / 2)),
    )


def mejor_linea_base(y, oof: Dict[str, np.ndarray]) -> str:
    """La línea base trivial de mayor AUC medio con todos los datos, elegida UNA vez (empate → `solo_categoria`)."""
    auc = {n: auc_medio(y, oof[n]) for n in LINEAS_BASE}
    return max(LINEAS_BASE, key=lambda n: (auc[n], -LINEAS_BASE.index(n)))


def decidir(auc: Dict[str, dict], diferencia: Dict[str, dict]) -> Dict[str, dict]:
    """Regla de decisión fijada: (a) límite inferior del IC del AUC > 0,5 y (b) límite inferior del IC de la diferencia con la
    mejor línea base trivial > 0. Devuelve, por candidato, `{a, b, cumple}`."""
    salida = {}
    for c in CANDIDATOS:
        a = auc[c]["ic"][0] > 0.5
        b = diferencia[c]["ic"][0] > 0.0
        salida[c] = {"a": bool(a), "b": bool(b), "cumple": bool(a and b)}
    return salida


def evaluar(
    X: pd.DataFrame,
    y,
    filas,
    cols,
    repeticiones: int = N_REPETICIONES,
    pliegues: int = N_PLIEGUES,
    n_remuestreos: int = N_REMUESTREOS,
    semilla: int = SEMILLA,
) -> dict:
    """Validación completa de una etiqueta: AUC medio con IC de los cuatro modelos, mejor línea base, diferencias pareadas de
    los candidatos y decisión. Todo agregado (ningún dato por local)."""
    y = np.asarray(y, dtype=int)
    oof = validar(X, y, filas, cols, MODELOS, repeticiones, pliegues, semilla)
    bloques = validation.block_labels(filas, cols)  # cuadrícula SIN desplazar
    mejor = mejor_linea_base(y, oof)
    replicas, descartadas = remuestrear_por_bloques(y, oof, bloques, n_remuestreos, semilla)
    auc = {n: {"media": auc_medio(y, oof[n]), "ic": list(intervalo(replicas[n]))} for n in MODELOS}
    dif = {}
    for c in CANDIDATOS:
        d = replicas[c] - replicas[mejor]
        dif[c] = {"media": auc[c]["media"] - auc[mejor]["media"], "ic": list(intervalo(d))}
    decision = decidir(auc, dif)
    return {
        "n": int(len(y)),
        "positivos": int(y.sum()),
        "bloques": int(len(np.unique(bloques))),
        "auc": auc,
        "mejor_linea_base": mejor,
        "diferencia_con_la_mejor_linea_base": dif,
        "decision": decision,
        "utilizable": bool(any(v["cumple"] for v in decision.values())),
        "remuestreos": {"pedidos": int(n_remuestreos), "descartados_por_una_sola_clase": descartadas},
    }


def tasa_por_categoria(poblacion: pd.DataFrame, y) -> List[dict]:
    """Descriptivo: locales, cierres y tasa de cierre por categoría (sin modelo)."""
    y = np.asarray(y, dtype=int)
    salida = []
    for c in cf.CATEGORIAS:
        en_c = poblacion["categoria"].to_numpy() == c
        n = int(en_c.sum())
        cierres = int(y[en_c].sum())
        salida.append({"categoria": c, "locales": n, "cierres": cierres, "tasa": (cierres / n) if n else None})
    return salida
