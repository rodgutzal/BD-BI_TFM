"""Tests del sector económico de cada categoría y del catálogo de actividades que el sistema NO puede analizar
(src/sectores.py).

Lo que se defiende aquí: que reconocer una granja y explicar por qué no se puede analizar es mejor que mandarla a la
categoría «más parecida», y que añadir ese paso no altera el sistema que se evaluó en la fase 3."""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from src import sectores as sec  # noqa: E402
from src.business_type_classifier import BUSINESS_TYPE_RULES  # noqa: E402
from src.business_type_classifier import classify_business_type, patron_palabra  # noqa: E402
from src.ml.text_hibrido import CATEGORIAS, FUENTE_FUERA, FUENTE_PALABRAS, interpretar  # noqa: E402


# ---- sectores ----------------------------------------------------------------------------------------------------
def test_las_siete_categorias_tienen_sector_y_todas_son_terciarias():
    """Es el límite del sistema puesto por escrito: todo lo que sabe analizar son servicios y comercio."""
    assert set(sec.SECTOR_POR_CATEGORIA) == set(CATEGORIAS)
    assert set(sec.SECTOR_POR_CATEGORIA.values()) == {sec.TERCIARIO}
    for categoria in CATEGORIAS:
        assert sec.sector_de(categoria) == sec.TERCIARIO


def test_una_categoria_desconocida_no_tiene_sector():
    assert sec.sector_de("granja") is None and sec.sector_de(None) is None
    assert sec.nombre_sector(None) == "" and sec.nombre_sector("inventado") == ""


def test_los_tres_sectores_estan_descritos():
    assert set(sec.SECTORES) == {sec.PRIMARIO, sec.SECUNDARIO, sec.TERCIARIO}
    for clave, datos in sec.SECTORES.items():
        assert datos["nombre"] and datos["descripcion"], clave


# ---- actividades fuera de alcance --------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "texto,clave,sector",
    [
        ("quiero poner un invernadero", "agricultura", sec.PRIMARIO),
        ("una granja de pollos", "agricultura", sec.PRIMARIO),
        ("montar un huerto en Malta", "agricultura", sec.PRIMARIO),
        ("instalar un apiario", "ganaderia", sec.PRIMARIO),
        ("una piscifactoria", "pesca", sec.PRIMARIO),
        ("abrir una cantera", "extraccion", sec.PRIMARIO),
        ("una fabrica de muebles", "manufactura", sec.SECUNDARIO),
    ],
)
def test_reconoce_la_actividad_y_su_sector(texto, clave, sector):
    actividad = sec.actividad_fuera_de_alcance(texto)
    assert actividad is not None and actividad.clave == clave and actividad.sector == sector


def test_cada_actividad_explica_el_porque_y_que_haria_falta():
    """Sin el porqué, «no puedo» es una pared. Con él, el usuario sabe si el problema es suyo o del sistema."""
    for actividad in sec.FUERA_DE_ALCANCE:
        assert actividad.motivo and actividad.haria_falta, actividad.clave
        assert actividad.sector in sec.SECTORES
        assert actividad.palabras


def test_el_plural_tambien_se_reconoce():
    """Mismo arreglo que en las palabras clave: «dos granjas» no puede quedarse sin reconocer."""
    assert sec.actividad_fuera_de_alcance("dos granjas").clave == "agricultura"
    assert sec.actividad_fuera_de_alcance("varias canteras").clave == "extraccion"


def test_un_texto_vacio_o_sin_actividad_no_devuelve_nada():
    for texto in ("", "   ", None, "una pizzeria", "quiero abrir una farmacia"):
        assert sec.actividad_fuera_de_alcance(texto) is None


def test_la_venta_gana_a_la_produccion():
    """«Centro de jardinería» es una tienda (se puede analizar); «invernadero» es producción (no). El catálogo solo
    lleva términos de producción para que no se trague comercios de verdad."""
    for texto in ("centro de jardineria", "tienda de semillas", "tienda de muebles", "pescaderia"):
        assert sec.actividad_fuera_de_alcance(texto) is None, texto
        assert classify_business_type(texto) is not None, texto


def test_ninguna_palabra_del_catalogo_choca_con_las_de_las_categorias():
    """Misma comprobación de CONTENCIÓN que entre categorías, no un simple cruce de conjuntos: si «taller» entrara en
    el catálogo, ningún «taller mecánico» volvería a analizarse, y un cruce de conjuntos no lo vería. Lo señaló un
    code-review. Se usa el patrón real del clasificador, con su plural."""
    de_categorias = [kw for kws in BUSINESS_TYPE_RULES.values() for kw in kws]
    del_catalogo = [(a.clave, p) for a in sec.FUERA_DE_ALCANCE for p in a.palabras]
    choques = [
        (clave, palabra, kw)
        for clave, palabra in del_catalogo
        for kw in de_categorias
        if re.search(patron_palabra(palabra), kw) or re.search(patron_palabra(kw), palabra)
    ]
    assert not choques, f"El catálogo y las categorías se pisan: {choques}"


# ---- integración con el intérprete -------------------------------------------------------------------------------
def test_interpretar_devuelve_la_actividad_sin_categoria():
    """`categoria` queda en None a propósito: no hay puntaje que dar, pero sí hay algo que explicar."""
    i = interpretar("quiero poner un invernadero")
    assert i.categoria is None and i.fuente == FUENTE_FUERA
    assert i.fuera is not None and i.fuera.clave == "agricultura" and i.sector == sec.PRIMARIO


def test_la_produccion_gana_a_una_palabra_clave_suelta():
    """«fábrica de muebles» contiene «mueble», que es palabra de comercio. Si las palabras clave fueran primero, una
    fábrica se analizaría como una tienda: por eso el paso de fuera de alcance va delante."""
    assert classify_business_type("una fabrica de muebles") == "business"  # la palabra suelta sí la atrapa
    i = interpretar("una fabrica de muebles")
    assert i.categoria is None and i.fuera.clave == "manufactura"


def test_una_categoria_reconocida_trae_su_sector():
    i = interpretar("una pizzeria")
    assert i.categoria == "food_drink" and i.fuente == FUENTE_PALABRAS and i.sector == sec.TERCIARIO


def test_ninguna_frase_evaluada_toca_el_catalogo():
    """La guarda que mantiene cierto que «la aplicación es el sistema que se evaluó»: anteponer el paso de fuera de
    alcance no cambia ninguna respuesta medida mientras ninguna frase del corpus lo dispare. Si alguien añade una
    palabra que choque con el corpus, este test lo detiene y obliga a volver a medir."""
    import evaluate_text_classifier as etc

    entrenamiento, evaluacion = etc.cargar(evaluacion=etc.DATA / "frases_evaluacion_v2.psv")
    for nombre, frases in (("entrenamiento", entrenamiento["frase"]), ("evaluacion", evaluacion["frase"])):
        tocadas = [f for f in frases if sec.actividad_fuera_de_alcance(f) is not None]
        assert not tocadas, f"{nombre}: {tocadas}"


@pytest.mark.parametrize(
    "texto,categoria,fuera",
    [
        ("una fabrica de muebles", None, "manufactura"),
        ("un restaurante con huerto propio", "food_drink", None),
        ("una panaderia que fabrica su pan", "food_drink", None),
        ("una tienda de productos de granja", "business", None),
        ("quiero poner un invernadero", None, "agricultura"),
    ],
)
def test_cuando_ambos_aciertan_gana_el_que_nombra_el_negocio(texto, categoria, fuera):
    """Code-review: con el catálogo siempre delante, «un restaurante con huerto propio» se rechazaba. Con las palabras
    clave siempre delante, «una fábrica de muebles» se analizaba como tienda. Lo que decide es la POSICIÓN: en
    castellano, el sustantivo que nombra el negocio va antes que su complemento."""
    i = interpretar(texto)
    assert i.categoria == categoria
    assert (i.fuera.clave if i.fuera else None) == fuera


def test_recommend_locations_explica_la_actividad_en_vez_de_pedir_que_reformule(tmp_path):
    """Code-review: la otra entrada al sistema decía «sé más específico», mandando al usuario a reformular algo que
    nunca iba a funcionar. Ahora devuelve el porqué y qué haría falta."""
    from src.database import RouteDatabase
    from src.location_scoring import recommend_locations

    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    with pytest.raises(ValueError) as e:
        recommend_locations(db, "quiero poner una granja")
    mensaje = str(e.value)
    assert "Agricultura" in mensaje and "primario" in mensaje
    assert "Haría falta:" in mensaje
    assert "más específica" not in mensaje  # no se le pide reformular lo que no tiene arreglo


def test_un_negocio_que_no_se_entiende_sigue_pidiendo_que_reformule(tmp_path):
    """Lo contrario también importa: si de verdad no se entiende, el mensaje de siempre."""
    from src.database import RouteDatabase
    from src.location_scoring import recommend_locations

    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    with pytest.raises(ValueError, match="más específica"):
        recommend_locations(db, "asdfgh qwerty")
