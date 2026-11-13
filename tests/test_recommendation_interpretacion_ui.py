"""Tests de pantalla (Streamlit AppTest) de cómo Recomendación interpreta el texto: palabras clave primero, el modelo
entrenado solo donde ellas no reconocen el negocio (con su lectura marcada como decidida por el modelo) y la posibilidad de
corregir la categoría (docs/DISENO_ML_RECOMENDACION.md §3.L2)."""

import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import RouteDatabase  # noqa: E402
from src.locations import LOCATIONS  # noqa: E402
from streamlit_app.dashboards import recommendation_dashboard as rd  # noqa: E402

APP_PAGINA = """
import sys
sys.path.insert(0, {raiz!r})
from streamlit_app.dashboards import recommendation_dashboard as rd
rd.main()
"""


@pytest.fixture(autouse=True)
def limpiar():
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


@pytest.fixture
def categorias_calculadas(monkeypatch):
    """Anota con qué categoría se calcula el puntaje (lo que de verdad llega al MCDA) y delega en la función real."""
    llamadas = []
    original = rd.recommend_for_category

    def espia(db, categoria, *args, **kwargs):
        llamadas.append(categoria)
        return original(db, categoria, *args, **kwargs)

    monkeypatch.setattr(rd, "recommend_for_category", espia)
    return llamadas


@pytest.fixture
def pagina(tmp_path, monkeypatch, categorias_calculadas):
    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    db.save_demographics([{"zone_name": z, "population": 1000 * (i + 1)} for i, z in enumerate(LOCATIONS)])
    monkeypatch.setattr(rd, "get_database", lambda: db)
    return AppTest.from_string(APP_PAGINA.format(raiz=str(ROOT)), default_timeout=120)


def buscar(pagina, texto):
    pagina.text_input[0].set_value(texto)
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert not pagina.exception, [e.value for e in pagina.exception]


def selector(pagina):
    return next(s for s in pagina.selectbox if s.label == "Categoría a usar")


class ModeloFalso:
    def __init__(self, categoria, probabilidad=0.62):
        self.categoria, self.probabilidad = categoria, probabilidad

    def clasificar(self, texto):
        return self.categoria, self.probabilidad


def test_una_palabra_clave_se_interpreta_sin_aviso_del_modelo_y_se_puede_corregir(pagina):
    """Con una palabra clave se muestra la interpretación de siempre, sin aviso, y el selector de categoría está
    disponible pero plegado."""
    pagina.run()
    buscar(pagina, "una farmacia")
    assert any("Interpretado como: **🏥 Salud**" in s.value for s in pagina.success)
    assert not any("modelo entrenado" in w.value for w in pagina.warning)
    assert selector(pagina).value == "hospital"


def test_un_texto_que_solo_entiende_el_modelo_se_marca_como_decidido_por_el_modelo(pagina, monkeypatch):
    """Si las palabras clave no reconocen el negocio y responde el modelo, la pantalla lo dice, da su confianza y deja
    el selector abierto para revisarlo."""
    monkeypatch.setattr(rd, "get_text_model", lambda: ModeloFalso("sport", 0.62))
    pagina.run()
    buscar(pagina, "zzz qqq")
    avisos = [w.value for w in pagina.warning if "modelo entrenado" in w.value]
    assert (
        len(avisos) == 1
        and "Deporte" in avisos[0]
        and "confianza 62%" in avisos[0]
        and "lo decidió el modelo" in avisos[0]
    )
    assert not pagina.success  # no se presenta como una lectura segura
    assert selector(pagina).value == "sport"
    assert next(e for e in pagina.expander if "Cambiar la categoría" in e.label).proto.expanded is True


def test_corregir_la_categoria_es_la_que_llega_al_puntaje(pagina, monkeypatch, categorias_calculadas):
    """La categoría que elige el usuario sustituye a la interpretada: es la que se usa para calcular el puntaje, y la
    pantalla dice que se usa la elegida."""
    monkeypatch.setattr(rd, "get_text_model", lambda: ModeloFalso("sport"))
    pagina.run()
    buscar(pagina, "zzz qqq")
    assert categorias_calculadas[-1] == "sport"
    selector(pagina).set_value("school").run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    assert categorias_calculadas[-1] == "school"
    assert any("Usando la categoría que elegiste" in i.value and "Escuelas" in i.value for i in pagina.info)


def test_la_correccion_no_se_arrastra_a_la_siguiente_busqueda(pagina, monkeypatch, categorias_calculadas):
    """Una corrección vale para esa búsqueda: con otro texto, la categoría vuelve a ser la interpretada."""
    monkeypatch.setattr(rd, "get_text_model", lambda: ModeloFalso("sport"))
    pagina.run()
    buscar(pagina, "zzz qqq")
    selector(pagina).set_value("school").run()
    buscar(pagina, "una farmacia")
    assert selector(pagina).value == "hospital" and categorias_calculadas[-1] == "hospital"
    assert not any("Usando la categoría que elegiste" in i.value for i in pagina.info)


def test_un_texto_que_nadie_entiende_da_el_error_de_siempre(pagina, monkeypatch, categorias_calculadas):
    """Si ni las palabras clave ni el modelo responden, se muestra el mensaje de siempre y no se calcula nada."""
    monkeypatch.setattr(rd, "get_text_model", lambda: ModeloFalso(None, 0.1))
    pagina.run()
    buscar(pagina, "asdfgh qwerty")
    assert any("No pude identificar el tipo de negocio" in e.value for e in pagina.error)
    assert any("palabras más concretas" in i.value for i in pagina.info)
    assert categorias_calculadas == [] and not pagina.selectbox


def test_sin_modelo_la_pantalla_funciona_como_antes(pagina, monkeypatch):
    """Si el artefacto falta o no se verifica (`get_text_model` devuelve None), solo responden las palabras clave: una
    errata que antes no se entendía sigue sin entenderse y no hay aviso del modelo."""
    monkeypatch.setattr(rd, "get_text_model", lambda: None)
    pagina.run()
    buscar(pagina, "una pizeria")
    assert any("No pude identificar" in e.value for e in pagina.error)
    buscar(pagina, "una farmacia")
    assert any("Interpretado como" in s.value for s in pagina.success)


def test_con_el_modelo_real_una_errata_se_entiende_y_se_marca(pagina):
    """Con el artefacto versionado en data/ml/: «una pizeria» (errata) la entiende el modelo como restauración, con aviso
    de que lo decidió el modelo, y se calcula el puntaje de esa categoría."""
    pagina.run()
    buscar(pagina, "una pizeria")
    avisos = [w.value for w in pagina.warning if "modelo entrenado" in w.value]
    assert len(avisos) == 1 and "Restauración y bares" in avisos[0]
    assert selector(pagina).value == "food_drink"
    assert any("Panorama por celda" in s.value for s in pagina.subheader)
