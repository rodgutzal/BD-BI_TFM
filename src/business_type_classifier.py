"""Interpreta texto libre en español ("quiero poner una pizzería") y lo
mapea a una de las 9 categorías de `src/poi_client.CATEGORY_TAGS`
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
        "farmacia",
        "botica",
        "parafarmacia",
        "clinica",
        "consultorio",
        "centro de salud",
        "centro medico",
        "dentista",
        "dental",
        "odontologia",
        "ortodoncia",
        "veterinaria",
        "veterinario",
        "laboratorio clinico",
        "laboratorio de analisis",
        "analisis clinicos",
        "optica",
        "optometrista",
        "audiologia",
        "audifonos",
        "fisioterapia",
        "fisioterapeuta",
        # «rehabilitacion» estuvo aquí y se retiró: en castellano es mucho más habitual en obra («rehabilitación de
        # fachadas», «empresa de rehabilitación de edificios») que en salud, y el sentido médico ya lo cubren
        # «fisioterapia», «fisioterapeuta» y «terapia». Lo señaló un code-review.
        "quiropractico",
        "podologia",
        "podologo",
        "psicologia",
        "psicologo",
        "psiquiatra",
        "terapia",
        "logopedia",
        "medico",
        "doctor",
        "pediatra",
        "ginecologo",
        "dermatologo",
        "oftalmologo",
        "traumatologo",
        "hospital",
        "policlinico",
        "ambulatorio",
        "enfermeria",
        "nutriologo",
        "nutricionista",
        "dietista",
        "matrona",
        "obstetra",
        "radiologia",
        "imagenologia",
        "vacunacion",
        "donacion de sangre",
    ),
    "school": (
        "escuela",
        "colegio",
        "academia",
        "guarderia",
        "kinder",
        "kindergarten",
        "jardin infantil",
        "jardin de ninos",
        "ludoteca",
        "universidad",
        "facultad",
        "instituto educativo",
        "centro educativo",
        "centro de formacion",
        "formacion profesional",
        "escuela de negocios",
        "autoescuela",
        "escuela de manejo",
        "escuela de musica",
        "conservatorio",
        "escuela de arte",
        "escuela de cocina",
        "clases particulares",
        "tutoria",
        "refuerzo escolar",
        "preparatoria",
        "bachillerato",
        "preescolar",
        "primaria",
        "secundaria",
        "idiomas",
        # «ingles» no: con el plural daría «ingleses», que es otra palabra («una cervecería para ingleses»).
        "clases de ingles",
        "biblioteca",
        "centro de estudios",
    ),
    "sport": (
        "gimnasio",
        "gym",
        "yoga",
        "pilates",
        "crossfit",
        "artes marciales",
        "spinning",
        "centro deportivo",
        "polideportivo",
        "club deportivo",
        "cancha",
        "campo de futbol",
        "futbol sala",
        "piscina",
        "natacion",
        "fitness",
        "sala de musculacion",
        "entrenamiento funcional",
        "boxeo",
        "kickboxing",
        "judo",
        "karate",
        "taekwondo",
        "jiu jitsu",
        "escalada",
        "rocodromo",
        "padel",
        "tenis",
        "squash",
        "frontenis",
        "baloncesto",
        "voleibol",
        "atletismo",
        "ciclismo indoor",
        "danza",
        "zumba",
        "ballet",
        "patinaje",
        # «box» no: con el plural daría «boxes», que en castellano son plazas de aparcamiento, no boxeo.
        "halterofilia",
        "calistenia",
    ),
    "leisure": (
        "cine",
        "teatro",
        "auditorio",
        "sala de conciertos",
        "museo",
        "galeria de arte",
        "centro cultural",
        "discoteca",
        "club nocturno",
        "sala de baile",
        "casino",
        "bingo",
        "salon de fiestas",
        "salon de eventos",
        "arcade",
        "salon recreativo",
        "boliche",
        "bolera",
        "billar",
        "parque de diversiones",
        "parque tematico",
        "parque acuatico",
        "zoologico",
        "acuario",
        "sala de juegos",
        "sala de escape",
        "escape room",
        "realidad virtual",
        "karaoke",
        "minigolf",
        "laser tag",
        "club de lectura",
    ),
    "mall": (
        "centro comercial",
        "mall",
        "plaza comercial",
        "galeria comercial",
        "gran almacen",
        "grandes almacenes",
        "outlet",
        "paseo comercial",
    ),
    "food_drink": (
        "restaurante",
        "restaurant",
        "cafeteria",
        "cafe",
        "bar",
        "pizzeria",
        "panaderia",
        "pasteleria",
        "heladeria",
        "taqueria",
        "marisqueria",
        "asador",
        "parrilla",
        "sushi",
        "hamburgueseria",
        "pub",
        "cerveceria",
        "comida rapida",
        "food truck",
        "reposteria",
        "jugueria",
        "smoothie",
        "brunch",
        "bistro",
        "taberna",
        "cantina",
        "churrasqueria",
        "creperia",
        "rosticeria",
        "fonda",
        "comedor",
        "cocina economica",
        "antojitos",
        "trattoria",
        "gastrobar",
        "vermuteria",
        "coctaileria",
        "tapas",
        "arroceria",
        "pulperia",
        "sidreria",
        "vinoteca",
        "bar de vinos",
        "pizza al corte",
        "kebab",
        "wok",
        "ramen",
        "poke",
        "burrito",
        "tacos",
        "arepas",
        "empanadas",
        "bocateria",
        "sandwicheria",
        "ensaladas",
        "comida saludable",
        "comida a domicilio",
        "dark kitchen",
        "cocina fantasma",
        "chocolateria",
        "churreria",
        "donuts",
        "waffles",
        "crepes",
        "yogurteria",
        "zumeria",
        "cafe de especialidad",
        "teteria",
        "salon de te",
        "buffet",
        "catering",
    ),
    # Fase 3: dos comercios con categoría propia. Van ANTES de `business` por la misma razón que en
    # `poi_client.CATEGORY_TAGS`: `business` es el cajón y tiene que ser el último en reclamar una frase.
    "belleza": (
        "peluqueria",
        "peluquero",
        "barberia",
        "barbero",
        "salon de belleza",
        "centro de belleza",
        "estetica",
        "esteticista",
        "centro de estetica",
        "manicura",
        "pedicura",
        "depilacion",
        "corte de pelo",
        # Nada de «uñas»: normaliza a «unas», que es una palabra castellana corriente y atraparía
        # «unas tiendas». Es el mismo riesgo que ya costó retirar «ingles» y «box».
    ),
    "taller": (
        # NO está «taller» a secas, y es deliberado: un taller puede ser de bicis, de motos, de costura o de
        # carpintería, y a ninguno de esos le sirve la competencia de un taller de coches. Con «taller» suelto el
        # conjunto de evaluación lo demostró en el acto («taller de bicis», «taller de motos» pasaban a `taller`).
        # Hay que nombrar el vehículo. «quiero poner un taller» se queda a propósito sin categoría: no se sabe de qué.
        "taller mecanico",
        "taller de coches",
        "taller de automoviles",
        "taller de vehiculos",
        "taller de mecanica",
        # NO está «mecanico» a secas: «oficina para un ingeniero mecanico» acababa en `taller`. Es el mismo riesgo
        # que obligó a retirar «rehabilitacion» (más de obra que de salud) y lo señaló un code-review. El oficio
        # solo se reconoce acompañado del local: «taller mecanico», «taller de mecanica», «mecanica rapida».
        "mecanica rapida",
        "chapa y pintura",
        "reparacion de coches",
        "reparacion de automoviles",
        "reparacion de vehiculos",
        "neumaticos",
        "llantas",
    ),
    # Fase 2: alojamiento turístico. Dos trampas evitadas a propósito:
    #
    # - NO está «pension»: en castellano es muchísimo más habitual la prestación («oficina de pensiones») que la casa
    #   de huéspedes, y además el plural «pensiones» la dispararía. Es el mismo riesgo que retiró «rehabilitacion».
    # - NO está «apartamento» a secas, porque «busco un apartamento» suele ser para vivir, no para explotarlo. Hace
    #   falta el adjetivo: «apartamento turistico» (que con el plural ya reconoce «apartamentos turisticos»).
    "alojamiento": (
        "hotel",
        "hostal",
        "albergue",
        "motel",
        "resort",
        "camping",
        "alojamiento",
        "hospedaje",
        "casa de huespedes",
        "apartamento turistico",
        "bed and breakfast",
        "airbnb",
    ),
    # Residual: comercio y oficinas en general (igual definición que en Overpass).
    "business": (
        "tienda",
        "boutique",
        "ropa",
        "zapateria",
        "libreria",
        "papeleria",
        "ferreteria",
        "mueble",
        "joyeria",
        # «peluqueria», «salon de belleza», «barberia» y «estetica» se fueron a `belleza` en la fase 3.
        # «spa» se queda aquí a propósito: un spa no compite con una peluquería, y mandarlo a `belleza` le daría
        # una lente de competencia que no es la suya. Lo mismo con «masajes», «sauna» y «tatuajes» más abajo.
        "spa",
        "lavanderia",
        "tintoreria",
        "oficina",
        "despacho",
        "agencia",
        # «taller mecanico», «taller», «taller de coches», «chapa y pintura» y «neumaticos» se fueron a `taller`.
        # «autopartes», «pinturas», «lavado de coches» y «alquiler de coches» NO: la tienda de recambios es el
        # PROVEEDOR del taller, la de pinturas vende pintura (no hace chapa), y lavar o alquilar no es reparar.
        "banco",
        "inmobiliaria",
        "aseguradora",
        "seguros",
        "supermercado",
        "minimarket",
        "abarrotes",
        "electronica",
        "celulares",
        "computadoras",
        "floreria",
        "mascotas",
        "petshop",
        "jugueteria",
        "bazar",
        "cerrajeria",
        "imprenta",
        "fotografia",
        "notaria",
        "consultoria",
        # --- comercio minorista ---
        "almacen de ropa",
        "lenceria",
        "merceria",
        "textil",
        "calzado",
        "bolsos",
        "marroquineria",
        "relojeria",
        "bisuteria",
        "perfumeria",
        "cosmetica",
        "herbolario",
        "dietetica",
        "drogueria",
        "fruteria",
        "verduleria",
        "carniceria",
        "pescaderia",
        "charcuteria",
        "licoreria",
        "vinos y licores",
        "tienda de barrio",
        "ultramarinos",
        "kiosco",
        "estanco",
        "tabaqueria",
        "tienda de deportes",
        "bicicletas",
        "ciclos",
        "motos",
        "repuestos",
        "autopartes",
        # «llantas» y «neumaticos» se fueron a `taller`: las dos son `shop=tyres`, que además de vender monta.
        # «bici» (y su plural «bicis») se añadió al quitar «taller» suelto: sin ella «un taller de bicis» se quedaba
        # sin categoría, cuando una tienda-taller de bicicletas es `shop=bicycle`, o sea comercio.
        "bici",
        "electrodomesticos",
        "informatica",
        "videojuegos",
        "telefonia",
        "tienda de musica",
        "instrumentos musicales",
        "discos",
        "jardineria",
        "centro de jardineria",
        "semillas",
        "decoracion",
        "menaje",
        "colchones",
        "iluminacion",
        "pinturas",
        "azulejos",
        "materiales de construccion",
        "ortopedia",
        "segunda mano",
        "antiguedades",
        "tienda de regalos",
        "souvenirs",
        "artesania",
        # --- servicios personales ---
        # «manicura», «pedicura» y «depilacion» se fueron a `belleza` (son lo que hace un `shop=beauty`).
        # «masajes», «tatuajes», «piercing» y «solarium» se quedan: son los oficios que `belleza` cuenta como
        # competencia INDIRECTA, así que no pueden ser a la vez la categoría (un POI, una lente).
        "masajes",
        "tatuajes",
        "piercing",
        "solarium",
        "sauna",
        "costurera",
        "sastreria",
        "arreglos de ropa",
        "zapatero",
        "reparacion de calzado",
        "funeraria",
        "tanatorio",
        # --- servicios de empresa y oficina ---
        "coworking",
        "gestoria",
        "asesoria",
        "contabilidad",
        "contador",
        "abogado",
        "bufete",
        "arquitecto",
        "ingenieria",
        "estudio de diseno",
        "agencia de publicidad",
        "agencia de marketing",
        "agencia de viajes",
        "agencia inmobiliaria",
        "recursos humanos",
        "empresa de limpieza",
        "seguridad privada",
        "mensajeria",
        "paqueteria",
        "mudanzas",
        "alquiler de coches",
        "rent a car",
        "casa de cambio",
        "financiera",
        "cajero automatico",
        "copisteria",
        "copias",
        "rotulacion",
        "call center",
        "informatica empresarial",
        "soporte tecnico",
        "reparacion de moviles",
        "reparacion de ordenadores",
        # --- talleres de reparación (servicio, no manufactura) ---
        # «taller», «taller de coches» y «chapa y pintura» se fueron a `taller` en la fase 3. «lavado de coches» y
        # «car wash» se quedan: lavar no es reparar y su competencia son otros lavaderos, no los talleres.
        "lavado de coches",
        "car wash",
        "electricista",
        "fontanero",
        "plomero",
        "carpinteria",
        "ebanisteria",
        "herreria",
        "vidrieria",
        "tapiceria",
        "reparacion de electrodomesticos",
    ),
}


def patron_palabra(keyword: str) -> str:
    """Patrón de una palabra clave que acepta también el PLURAL castellano, palabra por palabra.

    Sin esto, «farmacia» no reconocía «varias farmacias» y «centro comercial» no reconocía «centros comerciales»: el
    límite de palabra `\\b` corta justo antes de la -s. El sufijo opcional va detrás de CADA palabra de la frase
    porque en castellano el plural se marca en todas («salones de belleza»).

    `(?:e?s)?` cubre las dos formas regulares: +s (farmacia → farmacias) y +es (bar → bares). Las combinaciones que no
    son palabras («dees») no aparecen en texto real, así que no molestan.

    CUIDADO al añadir palabras clave: el riesgo de este patrón es la palabra cuyo plural es OTRA palabra distinta.
    Por eso no están «ingles» (daría «ingleses») ni «box» (daría «boxes», plazas de aparcamiento); hay un test con
    esos dos casos. Antes de añadir un término corto, piensa qué significa seguido de -s y de -es."""
    return r"\b" + r"(?:e?s)?\s+".join(re.escape(p) for p in keyword.split()) + r"(?:e?s)?\b"


# Se compilan una vez al importar: son ~400 palabras clave y la pantalla clasifica en cada ejecución del script.
_REGLAS_COMPILADAS: Tuple[Tuple[str, Tuple[re.Pattern, ...]], ...] = tuple(
    (categoria, tuple(re.compile(patron_palabra(kw)) for kw in keywords))
    for categoria, keywords in BUSINESS_TYPE_RULES.items()
)


def buscar_categoria(text: str) -> Tuple[Optional[str], Optional[int]]:
    """(categoría, posición de la mención de negocio más temprana), o (None, None).

    Las dos mitades responden a preguntas distintas, así que a propósito NO salen del mismo acierto:

    - La CATEGORÍA la decide el orden del registro, el declarado arriba: gana la primera categoría que acierte, con
      `business` al final para que una palabra genérica no le gane a una específica. Decidirla por posición se probó
      y se descartó: «una oficina de farmacia» dejaba de ser `hospital`, y sobre las mismas 192 frases la exactitud
      bajaba del 85,4 % al 84,9 % mientras las respuestas equivocadas subían del 9,4 % al 9,9 % (lo señaló un
      code-review).
    - La POSICIÓN es la del acierto más temprano de CUALQUIER categoría, que es lo único que sirve para saber si una
      actividad no analizable se nombra antes que el negocio (ver `text_hibrido.interpretar`). Con la posición de la
      categoría ganadora, «un restaurante con fábrica y farmacia» se rechazaba como fuera de alcance: la fábrica
      está antes que «farmacia» aunque «restaurante» esté antes que las dos (lo señaló el QA de Codex).
    """
    if not text or not text.strip():
        return None, None
    normalized = _normalize(text)

    categoria, donde = None, None
    for category, patrones in _REGLAS_COMPILADAS:
        for patron in patrones:
            encontrado = patron.search(normalized)
            if encontrado is None:
                continue
            if categoria is None:  # orden del registro = prioridad
                categoria = category
            if donde is None or encontrado.start() < donde:  # posición = el acierto más temprano de todos
                donde = encontrado.start()
    return categoria, donde


def classify_business_type(text: str) -> Optional[str]:
    """Texto libre -> una de las 9 categorías de Overpass, o None si ninguna
    palabra clave matchea (el llamador decide qué hacer: pedir que
    reformule, usar una categoría por defecto, etc. — esta función nunca
    adivina)."""
    return buscar_categoria(text)[0]
