"""Pruebas del clasificador de texto libre -> categoría de Overpass."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.business_type_classifier import BUSINESS_TYPE_RULES, classify_business_type
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
    assert classify_business_type(texto) == esperado


def test_barberia_no_se_confunde_con_bar():
    """Regresión: la palabra clave "bar" (comida y bebida) no debe matchear
    dentro de "barbería". Es el bug que ya ocurrió una vez con datos reales de
    Foursquare, y el clasificador usa límites de palabra (\\b) para evitarlo."""
    assert classify_business_type("barbería") == "business"
    assert classify_business_type("quiero abrir una barbería") == "business"


def test_ignora_mayusculas_tildes_y_espacios_de_mas():
    assert classify_business_type("  PIZZERÍA  ") == "food_drink"
    assert classify_business_type("salon   de   belleza") == "business"


@pytest.mark.parametrize("texto", ["", "   ", None, "xyz", "asdfgh qwerty"])
def test_sin_coincidencia_devuelve_none_y_nunca_adivina(texto):
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

    choques = [
        (cat1, kw1, cat2, kw2)
        for cat1, kw1 in todas
        for cat2, kw2 in todas
        if cat1 != cat2 and re.search(rf"\b{re.escape(kw1)}\b", kw2)
    ]
    assert not choques, f"Palabras que se contienen entre categorías: {choques}"


def test_cantidad_de_palabras_clave_documentada():
    """El README dice 140 palabras clave (únicas)."""
    unicas = {kw for kws in BUSINESS_TYPE_RULES.values() for kw in kws}
    assert len(unicas) == 140
