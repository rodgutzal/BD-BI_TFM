"""Entrenamiento y evaluación del clasificador de texto (fase 3). Usa scikit-learn: corre en la máquina de entrenamiento,
no en el dashboard (que solo carga el JSON con src/ml/text_classifier.py).

Candidatos (docs/DISENO_ML_RECOMENDACION.md §3.C):
  logistica   TF-IDF de n-gramas de caracteres + regresión logística. Exportable a JSON.
  mlp         una red MLP de scikit-learn sobre los mismos TF-IDF (promedio de varias semillas).
  palabras    el método actual de palabras clave (src/business_type_classifier.py): la línea base.
  hibrido     palabras clave primero y, SOLO si no responden, el clasificador entrenado.

Regla de decisión (fijada antes de ver los resultados): el híbrido se adopta si (a) su exactitud sobre el conjunto de
evaluación supera a la de las palabras clave con el intervalo de confianza (bootstrap pareado de frases) por encima de 0
y (b) su tasa de respuestas equivocadas no pasa de la de las palabras clave más 2 puntos. Se prefiere el híbrido a
sustituir las palabras clave porque estas, cuando responden, suelen acertar: el clasificador solo entra donde ellas se
abstienen.
"""

import warnings
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.neural_network import MLPClassifier

from src.business_type_classifier import classify_business_type
from src.ml.text_classifier import NINGUNA, ModeloTexto

NGRAMAS = (2, 5)
UMBRALES = tuple(round(x, 2) for x in np.arange(0.30, 0.951, 0.05))
TOLERANCIA_ERRORES = 0.02
MLP_SEMILLAS = 3


def vectorizador() -> TfidfVectorizer:
    return TfidfVectorizer(analyzer="char_wb", ngram_range=NGRAMAS, lowercase=True, strip_accents="unicode", sublinear_tf=True)


def entrenar_logistica(frases: Sequence[str], categorias: Sequence[str], C: float = 10.0, seed: int = 0) -> ModeloTexto:
    """Ajusta TF-IDF + regresión logística y devuelve el modelo de solo numpy (umbral por defecto 0,5)."""
    vec = vectorizador()
    X = vec.fit_transform(frases)
    lr = LogisticRegression(C=C, max_iter=3000, class_weight="balanced", random_state=seed)
    lr.fit(X, categorias)
    vocab = {t: int(i) for t, i in vec.vocabulary_.items()}
    return ModeloTexto(list(lr.classes_), vocab, vec.idf_, lr.coef_, lr.intercept_, NGRAMAS)


def probabilidades_sklearn(frases: Sequence[str], categorias: Sequence[str], nuevas: Sequence[str], C: float = 10.0,
                           seed: int = 0) -> Tuple[List[str], np.ndarray]:
    """Probabilidades de scikit-learn directamente (para comprobar que el modelo de numpy las reproduce)."""
    vec = vectorizador()
    lr = LogisticRegression(C=C, max_iter=3000, class_weight="balanced", random_state=seed)
    lr.fit(vec.fit_transform(frases), categorias)
    return list(lr.classes_), lr.predict_proba(vec.transform(nuevas))


def probabilidades_mlp(frases: Sequence[str], categorias: Sequence[str], nuevas: Sequence[str], seed: int = 0
                       ) -> Tuple[List[str], np.ndarray]:
    """Red MLP (64 neuronas) sobre los mismos TF-IDF, promediando `MLP_SEMILLAS` semillas."""
    vec = vectorizador()
    X = vec.fit_transform(frases)
    clases, acumulado = None, 0.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ConvergenceWarning)
        for k in range(MLP_SEMILLAS):
            red = MLPClassifier(hidden_layer_sizes=(64,), alpha=1e-3, max_iter=600, random_state=seed * 100 + k)
            red.fit(X, categorias)
            clases = list(red.classes_)
            acumulado = acumulado + red.predict_proba(vec.transform(nuevas))
    return clases, acumulado / MLP_SEMILLAS


def respuesta(clases: Sequence[str], p: np.ndarray, umbral: float) -> List[Optional[str]]:
    """Categoría elegida por fila, o None si gana `ninguna` o la probabilidad máxima no llega al umbral."""
    salida = []
    for fila in p:
        i = int(np.argmax(fila))
        salida.append(None if clases[i] == NINGUNA or fila[i] < umbral else clases[i])
    return salida


def probabilidades_oof(frases: Sequence[str], categorias: Sequence[str], metodo: Callable, n_folds: int = 5,
                       seed: int = 0) -> Tuple[List[str], np.ndarray]:
    """Probabilidades fuera de muestra por validación cruzada estratificada, para elegir el umbral sin tocar la
    evaluación."""
    frases, categorias = np.asarray(frases, dtype=object), np.asarray(categorias, dtype=object)
    clases = sorted(set(categorias))
    oof = np.zeros((len(frases), len(clases)))
    for entrenamiento, prueba in StratifiedKFold(n_folds, shuffle=True, random_state=seed).split(frases, categorias):
        cs, p = metodo(frases[entrenamiento], categorias[entrenamiento], frases[prueba])
        oof[np.ix_(prueba, [clases.index(c) for c in cs])] = p
    return clases, oof


def elegir_umbral(clases: Sequence[str], p: np.ndarray, categorias: Sequence[str]) -> float:
    """Umbral con mayor exactitud fuera de muestra sobre el entrenamiento (en empate, el más alto: más prudente)."""
    mejor, mejor_exactitud = UMBRALES[0], -1.0
    for u in UMBRALES:
        exactitud = float(np.mean([_acierta(r, c) for r, c in zip(respuesta(clases, p, u), categorias)]))
        if exactitud >= mejor_exactitud:
            mejor, mejor_exactitud = u, exactitud
    return mejor


# ---------------------------------------------------------------------------
# Métricas y decisión
# ---------------------------------------------------------------------------
def _acierta(respondida: Optional[str], real: str) -> bool:
    """Acierta si da la categoría correcta o, para una frase fuera de alcance, si no responde."""
    return respondida is None if real == NINGUNA else respondida == real


def palabras_clave(frases: Sequence[str]) -> List[Optional[str]]:
    return [classify_business_type(f) for f in frases]


def hibrido(palabras: Sequence[Optional[str]], aprendido: Sequence[Optional[str]]) -> List[Optional[str]]:
    """Palabras clave primero; solo si no responden, el clasificador entrenado."""
    return [a if a is not None else b for a, b in zip(palabras, aprendido)]


def aciertos(respuestas: Sequence[Optional[str]], categorias: Sequence[str]) -> np.ndarray:
    return np.array([_acierta(r, c) for r, c in zip(respuestas, categorias)], dtype=float)


def equivocadas(respuestas: Sequence[Optional[str]], categorias: Sequence[str]) -> np.ndarray:
    """1 si respondió una categoría que no es la correcta (incluye responder a una frase fuera de alcance): el peor
    fallo, porque lleva al usuario a un resultado que no pidió."""
    return np.array([r is not None and r != c for r, c in zip(respuestas, categorias)], dtype=float)


def perdidas(respuestas: Sequence[Optional[str]], categorias: Sequence[str]) -> np.ndarray:
    """1 si no respondió a una frase que sí describía un negocio (el usuario tiene que reformular)."""
    return np.array([r is None and c != NINGUNA for r, c in zip(respuestas, categorias)], dtype=float)


def resumen(respuestas: Sequence[Optional[str]], categorias: Sequence[str]) -> Dict[str, float]:
    return {"exactitud": float(aciertos(respuestas, categorias).mean()),
            "equivocadas": float(equivocadas(respuestas, categorias).mean()),
            "sin_respuesta": float(perdidas(respuestas, categorias).mean())}


def bootstrap_pareado(a: np.ndarray, b: np.ndarray, n_boot: int = 5000, seed: int = 0, nivel: float = 0.95) -> dict:
    """Diferencia media (a − b) con su intervalo por bootstrap pareado de frases."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    d = a - b
    rng = np.random.default_rng(seed)
    medias = d[rng.integers(0, len(d), (n_boot, len(d)))].mean(axis=1)
    alfa = (1 - nivel) / 2
    return {"diferencia": float(d.mean()), "ic_inf": float(np.quantile(medias, alfa)), "ic_sup": float(np.quantile(medias, 1 - alfa))}


def decidir(palabras: Sequence[Optional[str]], candidato: Sequence[Optional[str]], categorias: Sequence[str],
            n_boot: int = 5000, seed: int = 0) -> dict:
    """Aplica la regla fijada: el candidato (híbrido) se adopta si mejora la exactitud con el IC por encima de 0 y no
    sube la tasa de respuestas equivocadas más de TOLERANCIA_ERRORES."""
    mejora = bootstrap_pareado(aciertos(candidato, categorias), aciertos(palabras, categorias), n_boot, seed)
    err_c, err_p = float(equivocadas(candidato, categorias).mean()), float(equivocadas(palabras, categorias).mean())
    cumple_a = mejora["ic_inf"] > 0
    cumple_b = err_c <= err_p + TOLERANCIA_ERRORES
    return {"exactitud": mejora, "equivocadas_candidato": err_c, "equivocadas_palabras": err_p,
            "cumple_exactitud": cumple_a, "cumple_errores": cumple_b, "adoptar": bool(cumple_a and cumple_b)}


def por_tipo(respuestas: Sequence[Optional[str]], categorias: Sequence[str], tipos: Sequence[str]) -> pd.DataFrame:
    """Exactitud, respuestas equivocadas y sin respuesta por tipo de frase."""
    df = pd.DataFrame({"tipo": tipos, "acierta": aciertos(respuestas, categorias),
                       "equivocada": equivocadas(respuestas, categorias), "sin_respuesta": perdidas(respuestas, categorias)})
    out = df.groupby("tipo").agg(n=("acierta", "size"), exactitud=("acierta", "mean"), equivocadas=("equivocada", "mean"),
                                 sin_respuesta=("sin_respuesta", "mean"))
    return out
