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
    Foursquare, y el clasificador usa límites de palabra (\\b) para evitarlo."""
    assert classify_business_type("barbería") == "business"
    assert classify_business_type("quiero abrir una barbería") == "business"


def test_gana_la_coincidencia_de_categoria_mas_temprana():
    """El orden del registro no puede ocultar el negocio que aparece antes en la frase.

    Es esencial para que `interpretar` pueda compararlo con una actividad fuera de alcance por posición: en «un
    restaurante con fábrica y farmacia», restaurante debe ganar a farmacia aunque `hospital` aparezca antes que
    `food_drink` en el registro.
    """
    assert buscar_categoria("un restaurante con fabrica y farmacia") == ("food_drink", 3)


def test_ignora_mayusculas_tildes_y_espacios_de_mas():
    """El clasificador no distingue mayúsculas, tildes ni espacios repetidos o sobrantes."""
    assert classify_business_type("  PIZZERÍA  ") == "food_drink"
    assert classify_business_type("salon   de   belleza") == "business"


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
    """El README dice 395 palabras clave únicas. Eran 140 hasta el 16-nov-2026; la ampliación y el arreglo de los
    plurales subieron la exactitud del sistema de 76,0 % a 84,9 % (ver docs/DISENO_ML_RECOMENDACION.md §3.L2)."""
    unicas = {kw for kws in BUSINESS_TYPE_RULES.values() for kw in kws}
    assert len(unicas) == 395
