"""Sector económico de cada categoría, y qué actividades este sistema NO puede analizar.

Dos cosas que van juntas:

1. **El sector de lo que se busca.** Las 7 categorías de Overpass son todas del sector TERCIARIO (servicios y
   comercio). Saberlo importa porque explica el límite del sistema: todo lo que mide —competencia entre comercios,
   mercado consumidor a pie, proveedores minoristas— son variables de servicios urbanos.

2. **Las actividades fuera de alcance.** Alguien puede querer poner una granja o un invernadero. Reconocer la frase y
   mandarla a la categoría «más parecida» daría un puntaje con criterios que no deciden nada de eso: el sistema
   respondería con seguridad y se equivocaría. Reconocerla y explicar POR QUÉ no se puede es más útil y más honesto,
   y es lo que hace `actividad_fuera_de_alcance`.

Por qué no se puede, en concreto (medido sobre los datos de este repositorio):
  - Las tres lentes del panorama son competencia, mercado consumidor y proveedores, todas de comercio urbano.
  - El puntaje por zona combina población, competencia de comercios y tiempo de viaje entre las 7 zonas.
  - La rejilla cubre ~141 km² del este urbano de Malta; la isla tiene 316 km² y el campo está al oeste.
  - De agricultura solo hay, como contexto, 94 invernaderos y 35 edificios de granja: no sostienen un análisis.
"""

import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from src.business_type_classifier import _normalize, patron_palabra

PRIMARIO, SECUNDARIO, TERCIARIO = "primario", "secundario", "terciario"

SECTORES: Dict[str, Dict[str, str]] = {
    PRIMARIO: {
        "nombre": "Sector primario",
        "descripcion": "Obtiene recursos directamente de la naturaleza: agricultura, ganadería, pesca, extracción.",
    },
    SECUNDARIO: {
        "nombre": "Sector secundario",
        "descripcion": "Transforma esos recursos: manufactura, construcción, talleres.",
    },
    TERCIARIO: {
        "nombre": "Sector terciario",
        "descripcion": "Presta servicios y vende al consumidor: comercio, hostelería, salud, educación, ocio.",
    },
}

# Las 9 categorías de Overpass son todas terciarias. Está escrito una por una, y no con un valor por defecto, para que
# añadir una categoría de otro sector obligue a decidir cuál es en vez de heredar «terciario» sin pensarlo.
#
# «taller» obliga a pararse a pensarlo, y por eso está escrito aquí: reparar un coche puede sonar a industria, pero es
# un SERVICIO prestado al cliente final, no transformación de materia prima para venderla. Un taller es terciario; una
# planta de montaje de coches sería secundaria, y esa sigue estando en el catálogo de lo que no se puede analizar
# (`manufactura`). La frontera es si se produce un bien o se presta un servicio.
SECTOR_POR_CATEGORIA: Dict[str, str] = {
    "food_drink": TERCIARIO,
    "business": TERCIARIO,
    "hospital": TERCIARIO,
    "school": TERCIARIO,
    "sport": TERCIARIO,
    "leisure": TERCIARIO,
    "mall": TERCIARIO,
    "belleza": TERCIARIO,
    "taller": TERCIARIO,
}


@dataclass(frozen=True)
class ActividadFueraDeAlcance:
    """Una actividad que se reconoce pero no se puede analizar, con el porqué y con qué haría falta para poder."""

    clave: str
    nombre: str
    sector: str
    palabras: Tuple[str, ...]
    motivo: str
    haria_falta: str


# Solo términos de PRODUCCIÓN, nunca de venta: «invernadero» está aquí, pero «centro de jardinería» es una tienda y se
# queda en `business`. Cuando una frase nombra las dos cosas, `interpretar` desempata por POSICIÓN: gana la que aparece
# antes, que en castellano es la que nombra el negocio («fábrica de muebles» es una fábrica; «restaurante con huerto
# propio» es un restaurante).
FUERA_DE_ALCANCE: Tuple[ActividadFueraDeAlcance, ...] = (
    ActividadFueraDeAlcance(
        "agricultura",
        "Agricultura",
        PRIMARIO,
        (
            "granja",
            "invernadero",
            "huerto",
            "huerta",
            "cultivo",
            "sembradio",
            "plantacion",
            "vinedo",
            "olivar",
            "campo de cultivo",
            "parcela agricola",
            "explotacion agricola",
        ),
        "Dónde va una explotación agrícola lo deciden el suelo cultivable, el agua, la pendiente y el acceso a la "
        "distribución. Nada de eso está en estos datos, que miden comercio urbano.",
        "Catastro de suelo agrícola, derechos de agua, pendiente del terreno, zonas protegidas y distancia al mercado "
        "mayorista. Y ampliar la rejilla al oeste de Malta, donde está el campo.",
    ),
    ActividadFueraDeAlcance(
        "ganaderia",
        "Ganadería",
        PRIMARIO,
        ("ganaderia", "establo", "criadero", "apiario", "colmenar", "corral", "porqueriza", "avicola"),
        "Una explotación ganadera se decide por superficie, distancia mínima a viviendas por normativa, agua y gestión "
        "de residuos. El sistema no conoce ninguna de esas cosas.",
        "Normativa de distancias a núcleos habitados, superficie disponible, puntos de agua y plantas de tratamiento.",
    ),
    ActividadFueraDeAlcance(
        "pesca",
        "Pesca y acuicultura",
        PRIMARIO,
        ("piscifactoria", "acuicultura", "pesquera", "criadero de peces", "cofradia de pescadores", "almadraba"),
        "Depende del mar, no del suelo: calidad del agua, corrientes, profundidad y concesiones marítimas. La rejilla "
        "solo cubre tierra firme.",
        "Batimetría, calidad del agua, concesiones de acuicultura y acceso a puerto.",
    ),
    ActividadFueraDeAlcance(
        "extraccion",
        "Extracción",
        PRIMARIO,
        ("cantera", "mina", "salinas", "gravera", "yacimiento"),
        "La localización la impone el recurso geológico, no el mercado: donde está la piedra, está la cantera.",
        "Mapa geológico, permisos de extracción y zonas protegidas.",
    ),
    ActividadFueraDeAlcance(
        "manufactura",
        "Manufactura",
        SECUNDARIO,
        ("fabrica", "planta de produccion", "maquiladora", "aserradero", "fundicion", "refineria", "ensambladora"),
        "Una fábrica se decide por suelo industrial, energía, logística y mano de obra. El sistema mide clientes a pie "
        "y comercios competidores, que para esto no dicen nada.",
        "Suelo industrial calificado, potencia eléctrica disponible, acceso a puerto y carretera, y coste del suelo. "
        "Parte de esto ya se recolecta como contexto (`industria`), pero no basta para recomendar.",
    ),
)


_FUERA_COMPILADAS: Tuple[Tuple[ActividadFueraDeAlcance, Tuple[re.Pattern, ...]], ...] = tuple(
    (actividad, tuple(re.compile(patron_palabra(p)) for p in actividad.palabras)) for actividad in FUERA_DE_ALCANCE
)


def sector_de(categoria: Optional[str]) -> Optional[str]:
    """Sector de una categoría de Overpass, o None si no se conoce."""
    return SECTOR_POR_CATEGORIA.get(categoria) if categoria else None


def nombre_sector(sector: Optional[str]) -> str:
    return SECTORES[sector]["nombre"] if sector in SECTORES else ""


def buscar_fuera_de_alcance(texto: str) -> Tuple[Optional[ActividadFueraDeAlcance], Optional[int]]:
    """(actividad no analizable, posición del acierto), o (None, None).

    Compara igual que las palabras clave de las categorías (límite de palabra y plural castellano, ver
    `patron_palabra`): «granja» no matchea dentro de otra palabra, pero «dos granjas» sí se reconoce. Devuelve el
    acierto MÁS TEMPRANO del catálogo, porque quien llama desempata por posición.

    A igual posición gana la coincidencia MÁS LARGA, es decir la más específica. Si no, el catálogo se tapa a sí
    mismo: «un criadero de peces» empata «criadero» (ganadería) con «criadero de peces» (pesca) en la misma
    posición, y el usuario recibía el motivo de la ganadería —normativa de distancias y residuos— para una
    piscifactoría, cuyo motivo real es el mar. Lo señaló un code-review."""
    if not texto or not texto.strip():
        return None, None
    normalizado = _normalize(texto)
    mejor, donde, hasta = None, None, None
    for actividad, patrones in _FUERA_COMPILADAS:
        for patron in patrones:
            encontrado = patron.search(normalizado)
            if encontrado is None:
                continue
            inicio, fin = encontrado.start(), encontrado.end()
            if donde is None or inicio < donde or (inicio == donde and fin > hasta):
                mejor, donde, hasta = actividad, inicio, fin
    return mejor, donde


def actividad_fuera_de_alcance(texto: str) -> Optional[ActividadFueraDeAlcance]:
    """La actividad no analizable que nombra el texto, o None."""
    return buscar_fuera_de_alcance(texto)[0]
