"""Pruebas del clasificador de texto libre -> categoría de Overpass."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.business_type_classifier import BUSINESS_TYPE_RULES, buscar_categoria, classify_business_type, patron_palabra
from src.poi_client import CATEGORY_TAGS


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("quiero abrir una pizzería", "food_drink"),
        ("Cafetería", "food_drink"),
        ("un bar de copas", "food_drink"),
        ("una farmacia", "hospital"),
        ("clínica veterinaria", "hospital"),
        ("gimnasio", "sport"),
        ("escuela de idiomas", "school"),
        ("cine", "leisure"),
        ("centro comercial", "mall"),
        ("tienda de ropa", "business"),
    ],
)
def test_clasifica_negocios_comunes(texto, esperado):
    """Cada texto de negocio común (parametrizado) se clasifica en la categoría esperada."""
    assert classify_business_type(texto) == esperado


def test_barberia_no_se_confunde_con_bar():
    """Regresión: la palabra clave "bar" (comida y bebida) no debe matchear
    dentro de "barbería". Es el bug que ya ocurrió una vez con datos reales de
    Foursquare, y el clasificador usa límites de palabra (\\b) para evitarlo.

    Desde la fase 3 una barbería es `belleza` y no `business`; lo que este test protege es que NUNCA sea
    `food_drink`, que es el bug de verdad."""
    assert classify_business_type("barbería") == "belleza"
    assert classify_business_type("quiero abrir una barbería") == "belleza"


def test_la_posicion_es_la_del_acierto_mas_temprano_aunque_la_categoria_la_decida_el_registro():
    """Las dos mitades que devuelve `buscar_categoria` salen de aciertos DISTINTOS, y es a propósito.

    En «un restaurante con fábrica y farmacia» la categoría es `hospital`, porque el registro pone `hospital` antes
    que `food_drink` y ese orden es la prioridad declarada. Pero la posición es la 3, la de «restaurante», no la 29
    de «farmacia»: es la única que permite a `interpretar` ver que el negocio se nombra ANTES que la fábrica (19) y
    no rechazar la frase como fuera de alcance. Con la posición de la categoría ganadora se rechazaba (QA de Codex).
    """
    assert buscar_categoria("un restaurante con fabrica y farmacia") == ("hospital", 3)


def test_una_palabra_generica_no_le_gana_a_una_especifica_por_aparecer_antes():
    """`business` es la categoría residual y va al final del registro justamente para esto: «oficina» no puede
    ganarle a «farmacia». Decidir la categoría por posición rompía el invariante, y sobre las mismas 192 frases
    bajaba la exactitud del 85,4 % al 84,9 % subiendo las equivocadas del 9,4 % al 9,9 % (lo señaló un
    code-review)."""
    assert classify_business_type("una oficina de farmacia") == "hospital"
    assert classify_business_type("un local en un centro comercial para poner una farmacia") == "hospital"


@pytest.mark.parametrize(
    "frase, esperado",
    [
        ("quiero abrir una peluqueria", "belleza"),
        ("un salon de belleza en Sliema", "belleza"),
        ("montar un centro de estetica", "belleza"),
        ("hago manicura y pedicura", "belleza"),
        ("un taller mecanico", "taller"),
        ("un taller de coches en Msida", "taller"),
        ("busco local para chapa y pintura", "taller"),
        ("un local para mecanica rapida", "taller"),
        ("una tienda de neumaticos", "taller"),
    ],
)
def test_las_dos_categorias_de_la_fase_3(frase, esperado):
    """Belleza y taller salieron del cajón `business` en la fase 3: ya tienen competencia propia, no «cualquier
    comercio»."""
    assert classify_business_type(frase) == esperado


@pytest.mark.parametrize(
    "frase, no_debe_ser",
    [
        ("un taller de bicis en Birkirkara", "taller"),
        ("Taller de motos por Birkirkara", "taller"),
        ("una tienda de motos", "taller"),
        ("autopartes y repuestos", "taller"),
        ("una tienda de pinturas", "taller"),
        ("lavado de coches", "taller"),
        ("oficina para un ingeniero mecanico", "taller"),
        ("un spa", "belleza"),
        ("masajes a domicilio", "belleza"),
    ],
)
def test_un_taller_o_un_salon_de_otra_cosa_no_cuentan(frase, no_debe_ser):
    """Por eso «taller» a secas NO es palabra clave: un taller puede ser de bicis, de motos o de costura, y a
    ninguno le sirve la competencia de un taller de coches. Lo encontró el propio conjunto de evaluación.

    Y al contrario: lo que es PROVEEDOR del taller (recambios, pinturas) o un oficio vecino (spa, masajes) se queda
    en `business`, porque un POI solo puede contar en una lente."""
    assert classify_business_type(frase) != no_debe_ser


def test_quiero_poner_un_taller_se_queda_sin_categoria_a_proposito():
    """No se sabe de qué: no hay que adivinar. Es el mismo principio que «nunca elige una categoría al azar»."""
    assert classify_business_type("quiero poner un taller") is None


def test_limite_conocido_la_peluqueria_canina_se_clasifica_mal():
    """Límite declarado, no olvidado: «peluquería canina» (`shop=pet_grooming`) cae en `belleza`, y no compite con
    una barbería. Con palabras clave no se puede arreglar: añadir «peluqueria canina» a `business` rompería el test
    de choques, porque «peluqueria» está contenida dentro, y `belleza` va antes en el registro.

    Se deja fijado aquí para que se vea que es sabido y para que, si alguien añade un mecanismo de contexto
    negativo, este test le avise de que ya puede mejorarlo. Es 1 de las 192 frases de la evaluación."""
    assert classify_business_type("Peluquería canina en Mosta") == "belleza"


@pytest.mark.parametrize(
    "frase, esperado",
    [
        ("quiero abrir un hotel en Sliema", "alojamiento"),
        ("varios hoteles pequenos", "alojamiento"),
        ("un hostal para mochileros", "alojamiento"),
        ("un albergue juvenil", "alojamiento"),
        ("montar apartamentos turisticos", "alojamiento"),
        ("una casa de huespedes", "alojamiento"),
        ("un bed and breakfast", "alojamiento"),
        ("quiero poner un camping", "alojamiento"),
        ("gestionar un airbnb", "alojamiento"),
    ],
)
def test_el_alojamiento_de_la_fase_2(frase, esperado):
    """El alojamiento turístico ya existía como CONTEXTO de OSM (198 POIs), pero no como categoría que el usuario
    pudiera pedir. Desde la fase 2 sí."""
    assert classify_business_type(frase) == esperado


@pytest.mark.parametrize(
    "frase, no_debe_ser",
    [
        ("una oficina de pensiones", "alojamiento"),
        ("gestion de pensiones y jubilaciones", "alojamiento"),
        ("busco un apartamento para vivir", "alojamiento"),
        ("un apartamento de dos habitaciones", "alojamiento"),
    ],
)
def test_las_dos_palabras_que_el_alojamiento_no_puede_usar(frase, no_debe_ser):
    """«pension» es mucho más la prestación que la casa de huéspedes (y su plural «pensiones» lo confirma), y
    «apartamento» a secas suele ser para vivir, no para explotarlo. Por eso el vocabulario exige el adjetivo:
    «apartamento turistico». Es el mismo criterio que retiró «rehabilitacion» y «mecanico»."""
    assert classify_business_type(frase) != no_debe_ser


@pytest.mark.parametrize("frase", ["rehabilitacion de fachadas", "una empresa de rehabilitacion de edificios"])
def test_rehabilitacion_de_obra_no_es_un_negocio_de_salud(frase):
    """«rehabilitación» se retiró del vocabulario de `hospital`: en castellano es más de obra que de salud, y el
    sentido médico ya lo cubren «fisioterapia» y «terapia» (lo señaló un code-review)."""
    assert classify_business_type(frase) != "hospital"


def test_ignora_mayusculas_tildes_y_espacios_de_mas():
    """El clasificador no distingue mayúsculas, tildes ni espacios repetidos o sobrantes."""
    assert classify_business_type("  PIZZERÍA  ") == "food_drink"
    assert classify_business_type("salon   de   belleza") == "belleza"


@pytest.mark.parametrize("texto", ["", "   ", None, "xyz", "asdfgh qwerty"])
def test_sin_coincidencia_devuelve_none_y_nunca_adivina(texto):
    """Un texto sin ninguna palabra clave devuelve `None`; nunca elige una categoría al azar."""
    assert classify_business_type(texto) is None


def test_todas_las_categorias_existen_en_overpass():
    """El clasificador solo puede devolver categorías que realmente guarda
    la tabla `pois` (CATEGORY_TAGS de poi_client.py)."""
    assert set(BUSINESS_TYPE_RULES) <= set(CATEGORY_TAGS)


def test_ninguna_palabra_clave_choca_con_otra_categoria():
    """Una misma palabra no puede aparecer en dos categorías (el orden de las
    reglas decidiría en silencio), y ninguna palabra de una categoría puede
    estar contenida como palabra completa dentro de una frase de otra."""
    todas = [(cat, kw) for cat, kws in BUSINESS_TYPE_RULES.items() for kw in kws]

    cats_por_palabra = {}
    for cat, kw in todas:
        cats_por_palabra.setdefault(kw, set()).add(cat)
    repetidas = {kw: c for kw, c in cats_por_palabra.items() if len(c) > 1}
    assert not repetidas, f"Palabras en más de una categoría: {repetidas}"

    # Se compara con el MISMO patrón que usa el clasificador en producción (incluido el plural): si el test usara
    # `\b{kw}\b` a mano, garantizaría algo distinto de lo que realmente hace el sistema. Lo señaló un code-review.
    choques = [
        (cat1, kw1, cat2, kw2)
        for cat1, kw1 in todas
        for cat2, kw2 in todas
        if cat1 != cat2 and re.search(patron_palabra(kw1), kw2)
    ]
    assert not choques, f"Palabras que se contienen entre categorías: {choques}"


@pytest.mark.parametrize(
    "frase,no_debe_ser",
    [
        ("una cerveceria para ingleses", "school"),  # «ingles» + plural daría «ingleses»
        ("un local con boxes de aparcamiento", "sport"),  # «box» + plural daría «boxes»
    ],
)
def test_el_plural_no_atrapa_palabras_que_son_otra_cosa(frase, no_debe_ser):
    """El riesgo del sufijo de plural: una palabra corta cuyo plural es OTRA palabra. Por eso «ingles» y «box» no
    están en el vocabulario (lo señaló un code-review, que encontró estos dos casos reales)."""
    assert classify_business_type(frase) != no_debe_ser


def test_cantidad_de_palabras_clave_documentada():
    """El README dice 419 palabras clave únicas. Fueron 140 hasta el 16-nov-2026, 394 hasta la fase 3 (`belleza`,
    `taller`) y 407 hasta la fase 2 (`alojamiento`); ver docs/DISENO_ML_RECOMENDACION.md §3.L2 y §E."""
    unicas = {kw for kws in BUSINESS_TYPE_RULES.values() for kw in kws}
    assert len(unicas) == 419
