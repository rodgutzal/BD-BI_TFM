"""Interpretación del texto libre del tipo de negocio: el sistema HÍBRIDO (docs/DISENO_ML_RECOMENDACION.md §3.L2 y §3.L3).

    1. Palabras clave (src/business_type_classifier.py): si reconocen el negocio, esa es la respuesta.
    2. Solo si se abstienen, el clasificador entrenado (src/ml/text_classifier.py).
    3. Si tampoco responde (gana `ninguna` o no llega al umbral), no se adivina: no hay categoría.

ESTADO ACTUAL (19-nov-2026): el paso 2 NO se ejecuta. Al pasar el sistema de 7 a 10 categorías se reentrenó a 11
clases y se midió con un tercer conjunto (§3.L3); la regla de decisión, fijada antes de ver los datos, lo rechazó por
0,3 puntos de respuestas equivocadas, así que `data/ml/text_classifier_manifest.json` dice `adoptado: false` y
`cargar_modelo_adoptado` devuelve None. La aplicación responde solo con palabras clave. El artefacto se conserva como
evidencia de lo que se midió, no como código muerto: el camino del paso 2 sigue probado con dobles en los tests y se
reactivaría solo si una evaluación futura lo adoptara.

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

from src.business_type_classifier import buscar_categoria
from src.ml.text_classifier import ModeloTexto
from src.sectores import ActividadFueraDeAlcance, buscar_fuera_de_alcance, sector_de

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DIRECTORIO_MODELO = ROOT_DIR / "data" / "ml"
ARCHIVO_MODELO = "text_classifier.json"
ARCHIVO_MANIFIESTO = "text_classifier_manifest.json"

FUENTE_PALABRAS = "palabras"
FUENTE_MODELO = "modelo"
FUENTE_FUERA = "fuera_de_alcance"
# Las diez categorías que sabe analizar el sistema, y las que ofrece el selector de la pantalla.
#
# Hoy estas diez son exactamente las que reconocen las PALABRAS CLAVE, que es lo único que responde: el modelo se
# reentrenó a once clases en la fase 4 y la regla preregistrada no lo adoptó (§3.L3), así que no participa. La
# consecuencia práctica es que una frase sin ninguna palabra conocida («busco local para cortar el pelo») se queda
# SIN categoría en vez de caer en la más parecida: el sistema prefiere no responder a adivinar.
CATEGORIAS = (
    "food_drink",
    "hospital",
    "school",
    "sport",
    "leisure",
    "mall",
    "business",
    "belleza",
    "taller",
    "alojamiento",
)


@dataclass(frozen=True)
class Interpretacion:
    """Qué categoría se entendió, quién la decidió y, si fue el modelo, con qué confianza (0-1).

    `sector` es el sector económico de lo entendido. `fuera` solo viene cuando el texto nombra una actividad que este
    sistema NO puede analizar (una granja, una cantera): entonces `categoria` es None a propósito, y `fuera` trae el
    porqué para poder explicarlo en vez de dar un puntaje con criterios que no vienen al caso."""

    categoria: Optional[str]
    fuente: Optional[str] = None
    confianza: Optional[float] = None
    sector: Optional[str] = None
    fuera: Optional[ActividadFueraDeAlcance] = None


def interpretar(texto: str, modelo: Optional[ModeloTexto] = None) -> Interpretacion:
    """Palabras clave y catálogo de actividades no analizables a la vez, y gana **el que aparezca antes en la frase**;
    solo si ninguno acierta, el modelo.

    Por qué la posición y no un orden fijo: las dos listas pueden acertar en la misma frase, y cualquiera de los dos
    órdenes fijos se equivoca en la mitad de los casos. «Una fábrica de muebles» es una fábrica (y «mueble» es palabra
    de comercio); «un restaurante con huerto propio» es un restaurante (y «huerto» es palabra de agricultura). Lo que
    los distingue es cuál de los dos nombra el negocio, y en castellano ese va primero.

    Hoy ninguna frase de los conjuntos versionados —las 467 de entrenamiento ni las de evaluación— nombra una actividad
    del catálogo (hay un test que lo comprueba), así que este paso no cambia ninguna respuesta medida: la aplicación
    sigue siendo exactamente el sistema que se evaluó."""
    texto = texto or ""
    categoria, pos_categoria = buscar_categoria(texto)
    fuera, pos_fuera = buscar_fuera_de_alcance(texto)
    if fuera is not None and (categoria is None or pos_fuera < pos_categoria):
        return Interpretacion(None, FUENTE_FUERA, sector=fuera.sector, fuera=fuera)
    if categoria is not None:
        return Interpretacion(categoria, FUENTE_PALABRAS, sector=sector_de(categoria))
    if modelo is None:
        return Interpretacion(None)
    categoria, probabilidad = modelo.clasificar(texto)
    if categoria is None:
        return Interpretacion(None)
    return Interpretacion(categoria, FUENTE_MODELO, probabilidad, sector=sector_de(categoria))


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
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ) as e:  # JSON roto, formato desconocido, manifiesto incompleto o de otra forma
        logger.warning("No se pudo cargar el modelo de texto (%s): se usan solo las palabras clave.", e)
        return None
