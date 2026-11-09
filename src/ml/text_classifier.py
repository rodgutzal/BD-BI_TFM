"""Clasificador de texto del tipo de negocio (fase 3): inferencia con SOLO numpy, sin scikit-learn.

El modelo se entrena en la máquina de entrenamiento (src/ml/text_training.py) y se guarda como JSON: vocabulario,
idf, coeficientes y los parámetros del analizador. Aquí se reproduce, paso a paso, lo que hace scikit-learn:

    texto → minúsculas y sin tildes → n-gramas de caracteres por palabra (`char_wb`) → frecuencia sublineal (1 + ln f)
          → × idf → norma L2 → regresión logística multinomial (softmax)

Por qué JSON y no un `.pkl`: un pickle de scikit-learn depende de la versión exacta que lo escribió, y el dashboard
no entrena. El JSON es legible, verificable con un hash y no se rompe al actualizar librerías. Un test comprueba que
las probabilidades coinciden con las de scikit-learn en todas las frases del proyecto.

ABSTENCIÓN: el modelo tiene una clase `ninguna` (frases que no describen un negocio) y un umbral de confianza. Si gana
`ninguna` o la probabilidad máxima no llega al umbral, no se elige categoría (igual que el método de palabras clave,
que nunca adivina).
"""

import json
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

import numpy as np

NINGUNA = "ninguna"
_ESPACIOS = re.compile(r"\s\s+")


def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos, como `lowercase=True, strip_accents="unicode"` de scikit-learn (la ñ pasa a n)."""
    texto = texto.lower()
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def char_wb_ngrams(texto: str, n_min: int, n_max: int) -> List[str]:
    """n-gramas de caracteres dentro de cada palabra, rellenada con un espacio a cada lado. Es la misma lógica que el
    analizador `char_wb` de scikit-learn, incluida la regla de las palabras más cortas que n."""
    texto = _ESPACIOS.sub(" ", normalizar(texto))
    out: List[str] = []
    for palabra in texto.split():
        w = " " + palabra + " "
        largo = len(w)
        for n in range(n_min, n_max + 1):
            desplazamiento = 0
            out.append(w[desplazamiento:desplazamiento + n])
            while desplazamiento + n < largo:
                desplazamiento += 1
                out.append(w[desplazamiento:desplazamiento + n])
            if desplazamiento == 0:             # palabra más corta que n: no tiene sentido seguir con n mayores
                break
    return out


class ModeloTexto:
    """Regresión logística multinomial sobre TF-IDF de n-gramas de caracteres, con abstención."""

    FORMATO = 1

    def __init__(self, clases: List[str], vocabulario: Dict[str, int], idf: np.ndarray, coef: np.ndarray,
                 intercepto: np.ndarray, ngramas: Tuple[int, int], umbral: float = 0.5):
        self.clases = list(clases)
        self.vocabulario = dict(vocabulario)
        self.idf = np.asarray(idf, dtype=float)
        self.coef = np.asarray(coef, dtype=float)
        self.intercepto = np.asarray(intercepto, dtype=float)
        self.ngramas = (int(ngramas[0]), int(ngramas[1]))
        self.umbral = float(umbral)
        if self.coef.shape != (len(self.clases), len(self.vocabulario)) or self.idf.shape != (len(self.vocabulario),):
            raise ValueError("dimensiones incoherentes entre clases, vocabulario, idf y coeficientes")

    # -- inferencia --------------------------------------------------------------------------------------------------
    def vectorizar(self, texto: str) -> Tuple[np.ndarray, np.ndarray]:
        """(índices, valores) del vector TF-IDF normalizado del texto; vacío si ningún n-grama está en el vocabulario."""
        frecuencias: Dict[int, int] = {}
        for g in char_wb_ngrams(texto, *self.ngramas):
            i = self.vocabulario.get(g)
            if i is not None:
                frecuencias[i] = frecuencias.get(i, 0) + 1
        if not frecuencias:
            return np.array([], dtype=int), np.array([], dtype=float)
        indices = np.fromiter(frecuencias, dtype=int, count=len(frecuencias))
        valores = (1.0 + np.log(np.fromiter(frecuencias.values(), dtype=float, count=len(frecuencias)))) * self.idf[indices]
        return indices, valores / np.linalg.norm(valores)

    def probabilidades(self, texto: str) -> Dict[str, float]:
        """Probabilidad de cada clase. Un texto sin ningún n-grama conocido da solo el intercepto."""
        indices, valores = self.vectorizar(texto or "")
        logits = self.intercepto + (self.coef[:, indices] @ valores if len(indices) else 0.0)
        logits = logits - np.max(logits)
        p = np.exp(logits)
        p = p / p.sum()
        return dict(zip(self.clases, (float(x) for x in p)))

    def clasificar(self, texto: str, umbral: Optional[float] = None) -> Tuple[Optional[str], float]:
        """(categoría o None, probabilidad de la clase ganadora). Devuelve None si gana `ninguna`, si la probabilidad no
        llega al umbral o si el texto está vacío."""
        if not texto or not texto.strip():
            return None, 0.0
        p = self.probabilidades(texto)
        clase = max(p, key=p.get)
        if clase == NINGUNA or p[clase] < (self.umbral if umbral is None else umbral):
            return None, p[clase]
        return clase, p[clase]

    # -- (de)serialización -------------------------------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"formato": self.FORMATO, "clases": self.clases, "ngramas": list(self.ngramas), "umbral": self.umbral,
                "vocabulario": self.vocabulario, "idf": self.idf.tolist(), "coef": self.coef.tolist(),
                "intercepto": self.intercepto.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> "ModeloTexto":
        if d.get("formato") != cls.FORMATO:
            raise ValueError(f"formato {d.get('formato')!r}, se esperaba {cls.FORMATO}")
        return cls(d["clases"], d["vocabulario"], np.array(d["idf"]), np.array(d["coef"]), np.array(d["intercepto"]),
                   tuple(d["ngramas"]), d["umbral"])

    def save(self, ruta) -> None:
        with open(ruta, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, sort_keys=True)
            f.write("\n")

    @classmethod
    def load(cls, ruta) -> "ModeloTexto":
        with open(ruta, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
