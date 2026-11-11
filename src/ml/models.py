"""Modelos de oferta esperada: cuántos locales de la categoría objetivo debería haber en una celda según su contexto.

Candidatos (los dos 'reales') y líneas base (lo que el ML tiene que superar, ver docs/DISENO_ML_RECOMENDACION.md §4):

  boosting         HistGradientBoostingRegressor con pérdida de Poisson, sobre todas las variables.
  mlp              Red neuronal MLP de scikit-learn (32-16) sobre las mismas variables, promediando varias semillas.
                   scikit-learn NO ofrece pérdida de Poisson en la red: se entrena sobre log(1 + conteo) con error
                   cuadrático, y se deshace la transformación. Es una limitación conocida (la comparación con el
                   boosting es justa en datos y variables, no en la función de pérdida).
  media            promedio de entrenamiento, constante.
  solo_distancia   regresión de Poisson con la distancia al centro de zona.
  solo_poblacion   regresión de Poisson con la población suavizada (≈ la dimensión 'demanda' del MCDA actual).
  solo_densidad    regresión de Poisson con la densidad urbana (POIs de OTRAS categorías en la celda y su vecindad).
                   Es la línea base clave: las tres lentes miden sobre todo densidad (ver §3.F), y un modelo solo
                   merece usarse si aporta algo más que 'donde hay más de todo, hay más de esto'.

Todas devuelven conteos esperados > 0 (la desviación de Poisson lo exige).
"""

import warnings
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import PoissonRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.ml.features import CATEGORIAS
from src.ml.osm_context import CONTEXTO

MIN_ESPERADO = 1e-3
BASELINES = ("media", "solo_distancia", "solo_poblacion", "solo_densidad")
CANDIDATOS = ("boosting", "mlp")
TODOS = BASELINES + CANDIDATOS
# Solo con el contexto de la fase 1b (edificios, alojamiento, transporte, industria):
#   solo_edificios  línea base: regresión de Poisson con la densidad de edificios (proxy de superficie construida).
#   boosting_poi    el mismo boosting SIN las variables de contexto: permite medir si el contexto aporta algo.
OPCIONALES = ("solo_edificios", "boosting_poi")
MLP_SEMILLAS = 3
_PREFIJOS_CONTEXTO = tuple(f"{c}_" for c in CONTEXTO)


def densidad(X: pd.DataFrame) -> pd.DataFrame:
    """Densidad urbana: POIs de todas las categorías (el objetivo ya viene excluido de X) en la celda y los anillos
    1 y 2, en log(1 + n)."""
    return pd.DataFrame(
        {
            f"densidad_{zona}": np.log1p(sum(X[f"{cat}_{zona}"] for cat in CATEGORIAS))
            for zona in ("celda", "anillo1", "anillo2")
        },
        index=X.index,
    )


def columnas_de(nombre: str, X: pd.DataFrame) -> pd.DataFrame:
    """Subconjunto de variables que usa cada modelo."""
    if nombre == "solo_distancia":
        return X[["dist_centro_m"]]
    if nombre == "solo_poblacion":
        return X[["pob_suavizada"]]
    if nombre == "solo_densidad":
        return densidad(X)
    if nombre == "solo_edificios":
        return pd.DataFrame(
            {f"edificios_{z}": np.log1p(X[f"edificio_{z}"]) for z in ("celda", "anillo1", "anillo2")}, index=X.index
        )
    if nombre == "boosting_poi":
        return X[[c for c in X.columns if not c.startswith(_PREFIJOS_CONTEXTO)]]
    if nombre in CANDIDATOS:
        return X
    raise ValueError(f"Modelo desconocido: {nombre!r}. Disponibles: {list(TODOS + OPCIONALES)}")


def _poisson_lineal(Xa: pd.DataFrame, y, Xb: pd.DataFrame) -> np.ndarray:
    modelo = make_pipeline(
        SimpleImputer(strategy="median"), StandardScaler(), PoissonRegressor(alpha=1e-3, max_iter=500)
    )
    modelo.fit(Xa, y)
    return modelo.predict(Xb)


def _boosting(Xa: pd.DataFrame, y, Xb: pd.DataFrame, seed: int) -> np.ndarray:
    modelo = HistGradientBoostingRegressor(
        loss="poisson",
        learning_rate=0.05,
        max_iter=200,
        max_depth=3,
        min_samples_leaf=20,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=seed,
    )
    modelo.fit(Xa, y)
    return modelo.predict(Xb)


def _mlp(Xa: pd.DataFrame, y, Xb: pd.DataFrame, seed: int) -> np.ndarray:
    imputador, escala = SimpleImputer(strategy="median"), StandardScaler()
    A = escala.fit_transform(imputador.fit_transform(Xa))
    B = escala.transform(imputador.transform(Xb))
    objetivo = np.log1p(np.asarray(y, dtype=float))
    predicciones: List[np.ndarray] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ConvergenceWarning)
        for k in range(MLP_SEMILLAS):
            red = MLPRegressor(
                hidden_layer_sizes=(32, 16),
                alpha=1e-2,
                learning_rate_init=1e-3,
                max_iter=600,
                early_stopping=True,
                validation_fraction=0.15,
                n_iter_no_change=20,
                random_state=seed * 100 + k,
            )
            red.fit(A, objetivo)
            predicciones.append(np.expm1(red.predict(B)))
    return np.mean(predicciones, axis=0)


def fit_predict(nombre: str, X_train: pd.DataFrame, y_train, X_test: pd.DataFrame, seed: int = 0) -> np.ndarray:
    """Ajusta el modelo `nombre` con el conjunto de entrenamiento y devuelve el conteo esperado (> 0) de cada fila de
    `X_test`. Determinista para una semilla.

    Las variables que en el entrenamiento son TODO NaN (por ejemplo, la accesibilidad cuando la base no tiene datos de
    rutas) se descartan: no aportan nada y el boosting falla al discretizarlas."""
    vacias = X_train.columns[X_train.isna().all()]
    if len(vacias):
        X_train, X_test = X_train.drop(columns=vacias), X_test.drop(columns=vacias, errors="ignore")
    y = np.asarray(y_train, dtype=float)
    if nombre in ("solo_distancia", "solo_poblacion", "solo_densidad", "solo_edificios"):
        try:
            A, B = columnas_de(nombre, X_train), columnas_de(nombre, X_test)
        except KeyError:
            nombre = "media"  # su única variable no tiene datos (p. ej. sin demografía cargada): sin información
    if nombre == "media":
        esperado = np.full(len(X_test), y.mean())
    elif nombre in ("solo_distancia", "solo_poblacion", "solo_densidad", "solo_edificios"):
        esperado = _poisson_lineal(A, y, B)
    elif nombre in ("boosting", "boosting_poi"):
        esperado = _boosting(columnas_de(nombre, X_train), y, columnas_de(nombre, X_test), seed)
    elif nombre == "mlp":
        esperado = _mlp(X_train, y, X_test, seed)
    else:
        raise ValueError(f"Modelo desconocido: {nombre!r}. Disponibles: {list(TODOS + OPCIONALES)}")
    return np.clip(np.asarray(esperado, dtype=float), MIN_ESPERADO, None)


def fit_predict_ensemble(
    nombre: str, X_train: pd.DataFrame, y_train, X_test: pd.DataFrame, n: int = 10, seed: int = 0
) -> Dict[str, np.ndarray]:
    """Conjunto de `n` modelos entrenados sobre remuestreos bootstrap del entrenamiento (con semillas distintas).
    Devuelve el esperado medio y su dispersión: la incertidumbre que verá el usuario como intervalo de la 'brecha'."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y_train, dtype=float)
    preds = []
    for k in range(n):
        idx = rng.integers(0, len(X_train), len(X_train))
        preds.append(fit_predict(nombre, X_train.iloc[idx], y[idx], X_test, seed=seed + k))
    preds = np.stack(preds)
    return {
        "esperado": preds.mean(axis=0),
        "desv": preds.std(axis=0, ddof=1) if n > 1 else np.zeros(preds.shape[1]),
        "p10": np.percentile(preds, 10, axis=0),
        "p90": np.percentile(preds, 90, axis=0),
    }
