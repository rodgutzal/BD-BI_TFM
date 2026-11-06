"""Interpreta texto libre en español ("quiero poner una pizzería") y lo
mapea a una de las 7 categorías de `src/poi_client.CATEGORY_TAGS`
(school, hospital, food_drink, leisure, sport, mall, business).

Por qué existe: el usuario final describe su negocio con sus propias
palabras, no elige de un catálogo fijo — así que hace falta el mismo tipo
de clasificador por palabras clave que ya se construyó dos veces en este
proyecto (Overpass, Foursquare), ahora en la dirección inversa: de una
frase en español a una categoría, no de una categoría de una API a un
balde propio.

Mismo cuidado que en foursquare_client.py: se usa `\\b` (límite de palabra)
en vez de un simple `in`, para que "barbería" no matchee la palabra clave
"bar" (comida y bebida) — ese bug ya ocurrió una vez con datos reales, no
es hipotético.
"""

import re
import unicodedata
from typing import Dict, Optional, Tuple


def _normalize(text: str) -> str:
    """minúsculas, sin tildes/ñ->n, solo letras/números/espacios, espacios
    colapsados — para no tener que listar cada palabra clave con y sin
    acento, y para que una frase de varias palabras ("salon de belleza")
    siga matcheando aunque el usuario escriba espacios de más."""
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Orden = prioridad (gana la primera categoría que matchee). Las palabras ya
# están sin tildes porque se comparan contra texto normalizado con
# _normalize(); no hace falta listar variantes acentuadas.
#
# "business" es la categoría residual (comercio/oficina genérico, igual que
# en Overpass) y va al final para no atrapar palabras que en realidad
# describen algo más específico (ej. "tienda de mascotas" no debe ganarle a
# una futura categoría de mascotas si se agrega).
BUSINESS_TYPE_RULES: Dict[str, Tuple[str, ...]] = {
    "hospital": (
        "farmacia", "clinica", "consultorio", "dentista", "dental", "veterinaria",
        "veterinario", "laboratorio clinico", "optica", "fisioterapia", "psicologia",
        "medico", "doctor", "hospital", "policlinico", "nutriologo", "nutricionista",
    ),
    "school": (
        "escuela", "colegio", "academia", "guarderia", "kinder", "jardin infantil",
        "universidad", "instituto educativo", "centro educativo", "clases particulares",
        "tutoria", "preescolar", "primaria", "secundaria", "idiomas",
    ),
    "sport": (
        "gimnasio", "gym", "yoga", "pilates", "crossfit", "artes marciales", "spinning",
        "centro deportivo", "cancha", "piscina", "natacion", "fitness", "boxeo",
        "escalada", "padel", "danza", "box",
    ),
    "leisure": (
        "cine", "teatro", "museo", "galeria de arte", "discoteca", "club nocturno",
        "casino", "salon de fiestas", "arcade", "boliche", "bolera",
        "parque de diversiones", "sala de juegos", "karaoke",
    ),
    "mall": (
        "centro comercial", "mall", "plaza comercial", "galeria comercial",
    ),
    "food_drink": (
        "restaurante", "restaurant", "cafeteria", "cafe", "bar", "pizzeria",
        "panaderia", "pasteleria", "heladeria", "taqueria", "marisqueria", "asador",
        "parrilla", "sushi", "hamburgueseria", "pub", "cerveceria", "comida rapida",
        "food truck", "reposteria", "jugueria", "smoothie", "brunch", "bistro", "taberna",
        "cantina", "churrasqueria", "creperia", "rosticeria", "fonda", "comedor",
        "cocina economica", "antojitos",
    ),
    # Residual: comercio y oficinas en general (igual definición que en Overpass).
    "business": (
        "tienda", "boutique", "ropa", "zapateria", "libreria", "papeleria",
        "ferreteria", "mueble", "joyeria", "peluqueria", "salon de belleza",
        "barberia", "spa", "estetica", "lavanderia", "tintoreria", "oficina",
        "despacho", "agencia", "taller mecanico", "banco", "inmobiliaria",
        "aseguradora", "seguros", "supermercado", "minimarket", "abarrotes",
        "electronica", "celulares", "computadoras", "floreria", "mascotas",
        "petshop", "jugueteria", "bazar", "ferreteria", "cerrajeria", "imprenta",
        "fotografia", "notaria", "consultoria",
    ),
}


def classify_business_type(text: str) -> Optional[str]:
    """Texto libre -> una de las 7 categorías de Overpass, o None si ninguna
    palabra clave matchea (el llamador decide qué hacer: pedir que
    reformule, usar una categoría por defecto, etc. — esta función nunca
    adivina)."""
    if not text or not text.strip():
        return None
    normalized = _normalize(text)

    for category, keywords in BUSINESS_TYPE_RULES.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", normalized):
                return category
    return None
