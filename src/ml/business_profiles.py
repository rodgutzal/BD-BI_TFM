"""Perfiles de negocio: qué cuenta como competencia, mercado y proveedor para cada tipo de negocio.

Esta información NO se deduce de los datos (ningún dato dice si un supermercado compite con una panadería): es
conocimiento de negocio. Por eso cada categoría de Overpass tiene un PERFIL POR DEFECTO (este archivo; borrador
del autor, a revisar) y el usuario puede AJUSTARLO (apply_overrides) en vez de partir de una pantalla en blanco.
Ver docs/DISENO_ML_RECOMENDACION.md, sección E.

Reglas del diseño, implementadas aquí:
  - Un ajuste no puede dejar sin ningún elemento una lente que por defecto tiene (se avisa y se conserva el
    valor por defecto de esa lente).
  - Se mide cuánto se aparta el perfil de la competencia por defecto (desviacion_competencia) para avisar al
    usuario cuando la define de forma muy distinta: quitar competencia hace el panorama más optimista sin que
    los datos lo respalden.
"""

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

from src.ml.cell_counts import Selector, selector, selector_except
from src.ml.osm_context import NO_RESIDENCIALES

# Umbral de aviso (decisión pendiente nº 6 del diseño: se empieza en la mitad y se ajusta con las pruebas).
UMBRAL_DESVIACION = 0.5

SEGMENTOS = ("residentes", "oficinistas", "estudiantes", "turistas", "vida_nocturna")

# Etiquetas de OSM que se tratan como 'oficina': la subcategoría de la categoría `business` (shop/office).
_OFICINAS = (
    "company",
    "government",
    "insurance",
    "estate_agent",
    "lawyer",
    "accountant",
    "financial",
    "consulting",
    "coworking",
    "it",
    "architect",
    "notary",
    "employment_agency",
    "property_management",
    "telecommunication",
    "engineer",
)

# Segmentos de mercado → qué POIs los generan.
# `residentes` se aproxima con los EDIFICIOS que no son claramente no residenciales (categoría `edificio`, que solo
# existe si se cargó el contexto de la fase 1b: tools/download_osm_context.py). Es un proxy de superficie construida,
# no población (78 % de los edificios de Malta son `building=yes`). Sin ese contexto la lente da 'sin datos'.
# `turistas`: museos, galerías, teatros, casinos, zoo y parques + alojamiento turístico (categoría `alojamiento`, también
# de la fase 1b; sin ella solo cuentan los atractivos).
SEGMENTOS_POI: Dict[str, Tuple[Selector, ...]] = {
    "residentes": (selector_except("edificio", *NO_RESIDENCIALES),),
    "oficinistas": (selector("business", *_OFICINAS),),
    "estudiantes": (selector("school"),),
    "turistas": (
        selector("leisure", "museum", "gallery", "theatre", "casino", "zoo", "aquarium", "theme_park"),
        selector("alojamiento"),
    ),
    "vida_nocturna": (selector("leisure", "nightclub", "casino"), selector("food_drink", "bar", "pub", "biergarten")),
}

# Tipos de proveedor → qué POIs los representan. Son comercios MINORISTAS salvo 'mayoristas': hoy hay un solo
# mayorista cartografiado, así que esa lente casi no tiene datos (la lente lo declara).
PROVEEDORES_POI: Dict[str, Tuple[Selector, ...]] = {
    "mayoristas": (selector("business", "wholesale", "trade"),),
    "carnicerias": (selector("business", "butcher"),),
    "pescaderias": (selector("business", "seafood"),),
    "verdulerias": (selector("business", "greengrocer"),),
    "panaderias": (selector("business", "bakery", "pastry"),),
    "bebidas": (selector("business", "beverages", "alcohol", "wine"),),
    "supermercados": (selector("business", "supermarket"),),
    "tiendas_de_barrio": (selector("business", "convenience"),),
    "ferreteria": (selector("business", "hardware", "doityourself"),),
    "papeleria": (selector("business", "stationery", "copyshop"),),
    "equipamiento_deportivo": (selector("business", "sports", "outdoor"),),
    "droguerias": (selector("business", "chemist"),),
    "distribuidores_sanitarios": (),  # no hay etiqueta en OSM para esto: sin datos
}


@dataclass(frozen=True)
class BusinessProfile:
    """Perfil de un tipo de negocio (una de las 7 categorías de Overpass)."""

    key: str
    nombre: str
    competencia_directa: Tuple[Selector, ...]
    competencia_indirecta: Tuple[Selector, ...]
    segmentos: Tuple[str, ...]  # a quién le vende (claves de SEGMENTOS_POI)
    proveedores: Tuple[str, ...]  # qué proveedores le importan (claves de PROVEEDORES_POI)
    personalizado: bool = False


def _perfil(key, nombre, directa, indirecta, segmentos, proveedores) -> BusinessProfile:
    return BusinessProfile(key, nombre, tuple(directa), tuple(indirecta), tuple(segmentos), tuple(proveedores))


DEFAULT_PROFILES: Dict[str, BusinessProfile] = {
    p.key: p
    for p in [
        # Supermercados y panaderías son PROVEEDORES (el local compra ahí), no sustitutos: un POI cuenta en una sola lente.
        _perfil(
            "food_drink",
            "Restaurante, café o bar",
            [selector("food_drink")],
            [selector("business", "convenience", "deli", "confectionery")],
            ["residentes", "oficinistas", "estudiantes", "turistas", "vida_nocturna"],
            ["mayoristas", "carnicerias", "pescaderias", "verdulerias", "panaderias", "bebidas", "supermercados"],
        ),
        # Comercio GENÉRICO: las oficinas no son competencia (son mercado: 'oficinistas'). Para un comercio concreto
        # (panadería, peluquería...) hará falta elegir la subcategoría; el proveedor típico de un comercio genérico es el mayorista.
        _perfil(
            "business",
            "Comercio u oficina",
            [selector_except("business", *_OFICINAS)],
            [selector("mall")],
            ["residentes", "oficinistas", "turistas", "estudiantes"],
            ["mayoristas"],
        ),
        _perfil(
            "hospital",
            "Farmacia, clínica o consulta",
            [selector("hospital")],
            [selector("business", "chemist", "optician", "health_food")],
            ["residentes", "oficinistas", "estudiantes"],
            ["distribuidores_sanitarios", "droguerias"],
        ),
        _perfil(
            "school",
            "Colegio o centro educativo",
            [selector("school")],
            [selector("business", "educational_institution")],
            ["residentes"],
            ["papeleria"],
        ),
        _perfil(
            "sport",
            "Gimnasio o centro deportivo",
            [selector("sport")],
            [],  # sin sustitutos cartografiados en OSM (probado: ni 'dance' ni 'miniature_golf' tienen POIs)
            ["residentes", "oficinistas", "estudiantes"],
            ["equipamiento_deportivo"],
        ),
        _perfil(
            "leisure",
            "Ocio y cultura",
            [selector("leisure")],
            [selector("food_drink", "bar", "pub")],
            ["turistas", "residentes", "vida_nocturna"],
            [],
        ),
        _perfil(
            "mall",
            "Centro comercial",
            [selector("mall")],
            [selector("business", "clothes", "shoes", "electronics", "jewelry", "furniture")],
            ["residentes", "turistas", "oficinistas"],
            ["mayoristas"],
        ),
    ]
}


def get_default_profile(categoria: str) -> BusinessProfile:
    """Perfil por defecto de una de las 7 categorías. Lanza ValueError si no existe."""
    if categoria not in DEFAULT_PROFILES:
        raise ValueError(f"Categoría sin perfil: {categoria!r}. Disponibles: {sorted(DEFAULT_PROFILES)}")
    return DEFAULT_PROFILES[categoria]


def segment_selectors(profile: BusinessProfile) -> Dict[str, Tuple[Selector, ...]]:
    """Selectores de cada segmento de mercado del perfil (vacío = sin datos)."""
    return {s: SEGMENTOS_POI[s] for s in profile.segmentos}


def supplier_selectors(profile: BusinessProfile) -> Dict[str, Tuple[Selector, ...]]:
    """Selectores de cada tipo de proveedor del perfil (vacío = sin datos)."""
    return {p: PROVEEDORES_POI[p] for p in profile.proveedores}


def apply_overrides(
    profile: BusinessProfile,
    *,
    competencia_directa: Optional[Tuple[Selector, ...]] = None,
    competencia_indirecta: Optional[Tuple[Selector, ...]] = None,
    segmentos: Optional[Tuple[str, ...]] = None,
    proveedores: Optional[Tuple[str, ...]] = None,
) -> Tuple[BusinessProfile, List[str]]:
    """Aplica los ajustes del usuario a un perfil y devuelve (perfil nuevo, avisos).

    Un ajuste que dejaría VACÍA una lente que el perfil original sí tiene se ignora y se avisa (la lente conserva
    su valor anterior). Los nombres de segmento o proveedor desconocidos se descartan con aviso. Un ajuste que
    quita más de UMBRAL_DESVIACION de la competencia por defecto genera un aviso aparte."""
    avisos: List[str] = []

    def conservar_si_vacio(nuevo, anterior, nombre):
        if nuevo is not None and len(nuevo) == 0 and len(anterior) > 0:
            avisos.append(f"La lente '{nombre}' no puede quedar vacía: se conserva el valor por defecto.")
            return anterior
        return anterior if nuevo is None else tuple(nuevo)

    def solo_conocidos(nombres, validos, nombre):
        if nombres is None:
            return None
        conocidos = tuple(n for n in nombres if n in validos)
        if len(conocidos) != len(tuple(nombres)):
            descartados = [n for n in nombres if n not in validos]
            avisos.append(f"Se ignoran {nombre} desconocidos: {descartados}")
        return conocidos

    nuevo = replace(
        profile,
        competencia_directa=conservar_si_vacio(competencia_directa, profile.competencia_directa, "competencia directa"),
        competencia_indirecta=(
            tuple(competencia_indirecta) if competencia_indirecta is not None else profile.competencia_indirecta
        ),
        segmentos=conservar_si_vacio(
            solo_conocidos(segmentos, SEGMENTOS_POI, "segmentos"), profile.segmentos, "mercado"
        ),
        proveedores=conservar_si_vacio(
            solo_conocidos(proveedores, PROVEEDORES_POI, "proveedores"), profile.proveedores, "proveedores"
        ),
        personalizado=True,
    )
    base = DEFAULT_PROFILES.get(profile.key)
    if base is not None and desviacion_competencia(nuevo, base) > UMBRAL_DESVIACION:
        avisos.append(
            f"Has quitado más de la mitad de la competencia por defecto ({desviacion_competencia(nuevo, base):.0%}): "
            "el panorama será más optimista de lo que los datos respaldan."
        )
    return nuevo, avisos


def _elementos(selectors) -> set:
    """Elementos 'atómicos' de una lista de selectores: (categoría, subcategoría) o (categoría, '*') si abarca todas."""
    out = set()
    for s in selectors:
        if s.subcategories is None and s.excluding:
            out.add((s.category, "*-" + ",".join(sorted(s.excluding))))
        elif s.subcategories is None:
            out.add((s.category, "*"))
        else:
            out.update((s.category, sub) for sub in s.subcategories)
    return out


def desviacion_competencia(profile: BusinessProfile, base: Optional[BusinessProfile] = None) -> float:
    """Fracción (0-1) de los elementos de competencia por defecto (directa + indirecta) que el perfil ya no tiene.

    Añadir competencia no cuenta como desviación (hace el panorama más conservador, no más optimista)."""
    base = base or get_default_profile(profile.key)
    por_defecto = _elementos(base.competencia_directa) | _elementos(base.competencia_indirecta)
    actuales = _elementos(profile.competencia_directa) | _elementos(profile.competencia_indirecta)
    if not por_defecto:
        return 0.0
    quitados = {e for e in por_defecto if e not in actuales and (e[0], "*") not in actuales}
    return len(quitados) / len(por_defecto)
