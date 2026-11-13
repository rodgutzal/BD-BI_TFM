"""Interpretación del texto libre del tipo de negocio: el sistema HÍBRIDO adoptado en la fase 3 (docs/DISENO_ML_RECOMENDACION.md
§3.L2).

    1. Palabras clave (src/business_type_classifier.py): si reconocen el negocio, esa es la respuesta.
    2. Solo si se abstienen, el clasificador entrenado (src/ml/text_classifier.py).
    3. Si tampoco responde (gana `ninguna` o no llega al umbral), no se adivina: no hay categoría.

Es exactamente el sistema que se evaluó (`text_training.hibrido`): un test comprueba que da la misma respuesta que la
evaluación para cada frase del conjunto. Solo usa numpy: no hace falta scikit-learn en el dashboard.

El modelo se carga de data/ml/ con su manifiesto y se VERIFICA: solo se usa si el manifiesto dice que se adoptó y si el
hash del archivo coincide. Si falta o no cuadra, se avisa en el log y se vuelve a las palabras clave solas (el
comportamiento anterior), sin romper la pantalla.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.business_type_classifier import classify_business_type
from src.ml.text_classifier import ModeloTexto

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DIRECTORIO_MODELO = ROOT_DIR / "data" / "ml"
ARCHIVO_MODELO = "text_classifier.json"
ARCHIVO_MANIFIESTO = "text_classifier_manifest.json"

FUENTE_PALABRAS = "palabras"
FUENTE_MODELO = "modelo"
# Las siete categorías que sabe interpretar el sistema (las mismas del método de palabras clave y del modelo).
CATEGORIAS = ("food_drink", "hospital", "school", "sport", "leisure", "mall", "business")


@dataclass(frozen=True)
class Interpretacion:
    """Qué categoría se entendió, quién la decidió y, si fue el modelo, con qué confianza (0-1)."""

    categoria: Optional[str]
    fuente: Optional[str] = None
    confianza: Optional[float] = None


def interpretar(texto: str, modelo: Optional[ModeloTexto] = None) -> Interpretacion:
    """Híbrido: palabras clave primero; solo si se abstienen, el modelo. Sin modelo, solo las palabras clave."""
    categoria = classify_business_type(texto or "")
    if categoria is not None:
        return Interpretacion(categoria, FUENTE_PALABRAS)
    if modelo is None:
        return Interpretacion(None)
    categoria, probabilidad = modelo.clasificar(texto or "")
    if categoria is None:
        return Interpretacion(None)
    return Interpretacion(categoria, FUENTE_MODELO, probabilidad)


def cargar_modelo_adoptado(directorio=DIRECTORIO_MODELO) -> Optional[ModeloTexto]:
    """El modelo de texto verificado, o None (con un aviso en el log) si falta, no se adoptó o su hash no coincide."""
    directorio = Path(directorio)
    ruta, ruta_manifiesto = directorio / ARCHIVO_MODELO, directorio / ARCHIVO_MANIFIESTO
    if not ruta.exists() or not ruta_manifiesto.exists():
        logger.warning("No hay modelo de texto en %s: se usan solo las palabras clave.", directorio)
        return None
    try:
        manifiesto = json.loads(ruta_manifiesto.read_text(encoding="utf-8"))
        if manifiesto.get("adoptado") is not True:
            logger.warning("El manifiesto del modelo de texto no lo da por adoptado: se usan solo las palabras clave.")
            return None
        esperado = manifiesto["modelo"]["sha256"]
        real = hashlib.sha256(ruta.read_bytes()).hexdigest()
        if real != esperado:
            logger.warning("El hash de %s no coincide con su manifiesto: no se usa el modelo.", ARCHIVO_MODELO)
            return None
        return ModeloTexto.load(ruta)
    except (OSError, ValueError, KeyError) as e:  # JSON roto, formato desconocido, manifiesto incompleto...
        logger.warning("No se pudo cargar el modelo de texto (%s): se usan solo las palabras clave.", e)
        return None
