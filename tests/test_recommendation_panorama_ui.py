"""Tests de pantalla de la fase 2b (Streamlit AppTest): el panorama por celda dentro de Recomendación, con la tabla
versionada en data/ml/. Comprueban lo que promete el diseño: lentes por separado sin puntaje combinado, el perfil usado
siempre indicado, los controles que recalculan, la brecha etiquetada como exploratoria y que no cambia con el perfil."""

import shutil
import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import RouteDatabase  # noqa: E402
from src.locations import LOCATIONS  # noqa: E402
from src.ml import business_profiles as bp  # noqa: E402
from streamlit_app.dashboards import recommendation_dashboard as rd  # noqa: E402

APP_SECCION = """
import sys
sys.path.insert(0, {raiz!r})
from pathlib import Path
from streamlit_app.dashboards.panorama_section import render_panorama_section
render_panorama_section({categoria!r}, {datos!r})
"""

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


def abrir(categoria, datos=None):
    at = AppTest.from_string(
        APP_SECCION.format(raiz=str(ROOT), categoria=categoria, datos=str(datos) if datos else None),
        default_timeout=120,
    )
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def textos(elementos):
    return [e.value for e in elementos]


def multiselect(at, etiqueta):
    return next(m for m in at.multiselect if m.label == etiqueta)


# ---- lo que muestra -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("categoria", sorted(bp.DEFAULT_PROFILES))
def test_la_seccion_abre_para_cada_categoria(categoria):
    """Las siete categorías muestran el mapa, la lista de celdas y los cuatro controles de perfil."""
    at = abrir(categoria)
    assert len(at.get("plotly_chart")) == 1 and len(at.selectbox) == 1
    assert [m.label for m in at.multiselect] == [
        "Le vendes a…",
        "Competencia directa",
        "Competencia indirecta (sustitutos)",
        "Proveedores que te importan",
    ]
    assert at.subheader[0].value.endswith("Panorama por celda de 250 m")


def test_declara_que_no_hay_puntaje_combinado():
    """El texto explicativo dice que no hay puntaje y que son conteos, no una predicción."""
    at = abrir("food_drink")
    texto = " ".join(textos(at.caption))
    assert "No hay un puntaje combinado" in texto and "conteos" in texto


def test_siempre_indica_el_perfil_usado():
    """Con el perfil por defecto lo dice; no aparece el aviso de perfil personalizado."""
    at = abrir("food_drink")
    assert any("Perfil usado: **Restaurante, café o bar** (por defecto)" in t for t in textos(at.caption))
    assert not any("Perfil personalizado" in t for t in textos(at.info))


def test_las_capas_son_las_tres_lentes_y_la_brecha_solo_donde_existe():
    """food_drink ofrece la brecha como capa exploratoria; hospital no la tiene."""
    con, sin = abrir("food_drink"), abrir("hospital")
    assert con.radio[0].options[-1].startswith("Brecha de oferta — EXPLORATORIA")
    assert not any("Brecha" in o for o in sin.radio[0].options)
    assert con.radio[0].options[:3] == [
        "Competencia directa (conteo ponderado)",
        "Mercado (índice 0-1)",
        "Proveedores (conteo ponderado)",
    ]


def test_la_lista_de_celdas_empieza_por_las_de_mercado_alto_y_competencia_baja():
    """La primera opción lleva la estrella del filtro de oportunidad, y la nota dice cuántas celdas son."""
    at = abrir("food_drink")
    assert at.selectbox[0].options[0].startswith("★ ")
    assert any("celdas** (" in t and "Es un filtro, no un puntaje" in t for t in textos(at.caption))


def test_el_porcentaje_de_candidatas_no_se_redondea_a_cero():
    """5 de 1139 es 0,4 %: con cero decimales se leía «0%», que parece «ninguna celda». Se muestra con un decimal."""
    from streamlit_app.dashboards.panorama_section import porcentaje

    assert porcentaje(5, 1139) == "0.4%"
    assert porcentaje(0, 1139) == "0.0%"
    assert porcentaje(1139, 1139) == "100.0%"
    assert porcentaje(3, 0) == "—"  # sin celdas no se divide entre cero


def _vista_y_mapa(capa=None, elegida="auto"):
    from src.ml import panorama_view as pv
    from src.ml.business_profiles import DEFAULT_PROFILES
    from streamlit_app.dashboards import panorama_section as ps

    guardado, counts, _ = ps.load_data(ROOT / "data" / "ml")
    vista = pv.compute_view(counts, DEFAULT_PROFILES["food_drink"], guardado, "food_drink")
    capa = capa or pv.available_layers(vista)[0]
    sel = vista.index[0] if elegida == "auto" else elegida
    return vista, sel, ps.build_map(vista, capa, sel)


def test_el_mapa_rotula_la_celda_elegida():
    """El punto azul de la celda elegida lleva su identificador, para que se sepa cuál es sin abrir la ficha."""
    vista, sel, fig = _vista_y_mapa()
    elegido = [t for t in fig.data if t.name == "celda elegida"]
    assert len(elegido) == 1
    assert elegido[0].mode == "markers+text" and elegido[0].text == (f"Celda elegida: {sel}",)


def test_el_mapa_sin_celda_elegida_no_dibuja_el_marcador():
    """Si no hay celda elegida no se añade ningún marcador (ni rótulo) extra."""
    _, _, fig = _vista_y_mapa(elegida=None)
    assert not [t for t in fig.data if t.name == "celda elegida"]


def test_los_puntos_del_mapa_son_legibles():
    """Los puntos de celda no son diminutos ni casi transparentes (se confundían con las etiquetas del mapa base)."""
    _, _, fig = _vista_y_mapa()
    capa = next(t for t in fig.data if t.name not in ("celda elegida", "sin datos"))
    assert capa.marker.size >= 9 and capa.marker.opacity >= 0.9


def test_la_ficha_muestra_las_tres_lentes_y_la_confianza():
    """La ficha de la celda elegida trae competencia, mercado, proveedores y la confianza (que no es una probabilidad)."""
    at = abrir("food_drink")
    md = " ".join(textos(at.markdown))
    assert (
        "Ficha de la celda" in md
        and "**Competencia**" in md
        and "**Mercado consumidor**" in md
        and "**Proveedores**" in md
    )
    assert any("Confianza de datos" in t and "no es una probabilidad" in t for t in textos(at.caption))


def test_el_mapa_y_la_ficha_usan_el_perfil_elegido():
    """Una celda con competencia indirecta la pierde al quitar ese tipo de competencia: las lentes se recalculan con el
    perfil del usuario, no con el de por defecto."""
    from src.ml import panorama
    from src.ml import panorama_view as pv

    guardado, counts = panorama.read_panorama(ROOT / "data" / "ml"), panorama.read_counts(ROOT / "data" / "ml")
    base = pv.compute_view(counts, bp.get_default_profile("food_drink"), guardado, "food_drink")
    celda = base.index[base["competencia_indirecta"] > 0][0]
    at = abrir("food_drink")
    at.selectbox[0].set_value(celda).run()
    ficha = next(m.value for m in at.markdown if m.value.startswith("Directa:"))
    assert f"indirecta: {base.loc[celda, 'competencia_indirecta']:.2f}" in ficha and "indirecta: 0.00" not in ficha
    multiselect(at, "Competencia indirecta (sustitutos)").set_value([]).run()
    at.selectbox[0].set_value(celda).run()
    assert "indirecta: 0.00" in next(m.value for m in at.markdown if m.value.startswith("Directa:"))


# ---- brecha exploratoria -----------------------------------------------------------------------------------------
def test_la_brecha_de_la_ficha_se_etiqueta_como_exploratoria_y_no_validada():
    """Donde hay brecha, la ficha la muestra con la advertencia de que no está validada y el intervalo no es de confianza."""
    at = abrir("food_drink")
    aviso = next(w.value for w in at.warning if "Brecha de oferta EXPLORATORIA" in w.value)
    assert "no validada" in aviso and "no es de confianza" in aviso


def test_sin_brecha_no_hay_advertencia_de_brecha():
    """En una categoría sin brecha no aparece ninguna advertencia sobre ella."""
    at = abrir("hospital")
    assert not any("Brecha" in w.value for w in at.warning)


def test_elegir_la_capa_de_brecha_muestra_la_advertencia_de_capa():
    """Cambiar a la capa de brecha añade el aviso de que es exploratoria y puede reflejar solo la saturación."""
    at = abrir("food_drink")
    at.radio[0].set_value(at.radio[0].options[-1]).run()
    assert not at.exception
    assert any(w.value.startswith("Capa **exploratoria**") and "no está validada" in w.value for w in at.warning)


# ---- controles de perfil -----------------------------------------------------------------------------------------
def test_quitar_un_segmento_marca_el_perfil_como_personalizado():
    """Al cambiar un control, la pantalla lo dice y el perfil ya no es el por defecto."""
    at = abrir("food_drink")
    m = multiselect(at, "Le vendes a…")
    m.set_value([s for s in m.value if s != "turistas"]).run()
    assert not at.exception
    assert any("Perfil personalizado" in i.value for i in at.info)
    assert not any("(por defecto)" in t for t in textos(at.caption))


def test_volver_al_perfil_por_defecto_quita_el_aviso():
    """Restaurar la selección original devuelve el perfil por defecto."""
    at = abrir("food_drink")
    m = multiselect(at, "Le vendes a…")
    original = list(m.value)
    m.set_value(original[:-1]).run()
    multiselect(at, "Le vendes a…").set_value(original).run()
    assert not any("Perfil personalizado" in i.value for i in at.info)
    assert any("(por defecto)" in t for t in textos(at.caption))


def test_quitar_la_competencia_indirecta_avisa_de_que_el_panorama_es_mas_optimista():
    """Quitar más de la mitad de la competencia por defecto genera el aviso del diseño."""
    at = abrir("food_drink")
    multiselect(at, "Competencia indirecta (sustitutos)").set_value([]).run()
    assert any("más de la mitad" in w.value for w in at.warning)


def test_dejar_vacia_la_competencia_directa_avisa_y_conserva_la_de_por_defecto():
    """No se puede quedar sin competencia directa: se avisa y se usa la de por defecto."""
    at = abrir("food_drink")
    multiselect(at, "Competencia directa").set_value([]).run()
    assert not at.exception and any("no puede quedar vacía" in w.value for w in at.warning)


def test_cambiar_el_perfil_no_cambia_la_brecha_y_la_pantalla_lo_dice():
    """La brecha de la misma celda es idéntica con el perfil por defecto y con uno personalizado, y la ficha avisa de que
    usa las categorías estándar."""
    at = abrir("food_drink")

    def aviso(a):
        return next(w.value for w in a.warning if w.value.startswith("**Brecha de oferta EXPLORATORIA"))

    antes = aviso(at)
    celda = at.selectbox[0].value
    multiselect(at, "Competencia indirecta (sustitutos)").set_value([]).run()
    at.selectbox[0].set_value(celda).run()  # la misma celda: la lista se reordena con el perfil
    despues = aviso(at)
    cifras = lambda t: t[: t.index("Positiva")]  # brecha, esperado e intervalo
    assert cifras(antes) == cifras(despues)
    assert "Usa las categorías estándar, no tu perfil." not in antes
    assert "Usa las categorías estándar, no tu perfil." in despues


# ---- tabla ausente o alterada ------------------------------------------------------------------------------------
def test_sin_tabla_la_seccion_lo_dice_y_no_falla(tmp_path):
    """Con un directorio vacío no hay excepción: se informa y se indica cómo generarla."""
    at = abrir("food_drink", tmp_path)
    assert any("no está disponible" in i.value and "build_panorama.py" in i.value for i in at.info)
    assert not at.multiselect


def test_con_la_tabla_alterada_la_seccion_se_niega_a_mostrarla(tmp_path):
    """Si un CSV no coincide con el hash del manifiesto, no se muestra nada de él."""
    copia = tmp_path / "ml"
    shutil.copytree(ROOT / "data" / "ml", copia)
    ruta = copia / "panorama.csv"
    ruta.write_text(ruta.read_text(encoding="utf-8").replace("food_drink", "food_drinK", 1), encoding="utf-8")
    at = abrir("food_drink", copia)
    assert any("no coincide" in i.value or "hash" in i.value for i in at.info) and not at.get("plotly_chart")


# ---- la página completa ------------------------------------------------------------------------------------------
@pytest.fixture
def pagina(tmp_path, monkeypatch):
    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    db.save_demographics([{"zone_name": z, "population": 1000 * (i + 1)} for i, z in enumerate(LOCATIONS)])
    loc = LOCATIONS["Sliema"]
    db.save_pois(
        [
            {
                "osm_type": "node",
                "osm_id": i,
                "category": "food_drink",
                "subcategory": "restaurant",
                "name": f"p{i}",
                "latitude": loc.latitude + 0.0001 * i,
                "longitude": loc.longitude,
            }
            for i in range(1, 6)
        ]
    )
    monkeypatch.setattr(rd, "get_database", lambda: db)
    return AppTest.from_string(APP_PAGINA.format(raiz=str(ROOT)), default_timeout=120)


def test_la_pagina_muestra_el_panorama_despues_de_buscar(pagina):
    """Sin pulsar el botón no hay resultados; al buscar aparecen el MCDA por zona y debajo el panorama por celda."""
    pagina.run()
    assert not pagina.exception and not any("Panorama por celda" in s.value for s in pagina.subheader)
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    assert any("Panorama por celda" in s.value for s in pagina.subheader)
    assert any("Interpretado como" in s.value for s in pagina.success)


def test_los_resultados_sobreviven_a_cambiar_un_control_del_panorama(pagina):
    """Regresión: cada cambio de un control vuelve a ejecutar la página con el botón en False; antes los resultados
    desaparecían. Ahora se recuerda el texto buscado."""
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    seg = next(m for m in pagina.multiselect if m.label == "Le vendes a…")
    seg.set_value(seg.value[:-1]).run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    assert any("Panorama por celda" in s.value for s in pagina.subheader)
    assert any("Perfil personalizado" in i.value for i in pagina.info)


def test_buscar_con_texto_vacio_avisa_y_no_deja_resultados_viejos(pagina):
    """Un texto vacío da el aviso de siempre y borra lo buscado antes."""
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    pagina.text_input[0].set_value("   ")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert any("Escribe una descripción" in w.value for w in pagina.warning)
    assert not any("Panorama por celda" in s.value for s in pagina.subheader)
    pagina.run()  # otra ejecución (p. ej. al tocar un control): sigue sin resultados
    assert not any("Panorama por celda" in s.value for s in pagina.subheader)


def test_cambiar_de_negocio_no_arrastra_los_ajustes_del_anterior(pagina):
    """Los controles del panorama son propios de cada categoría: tras ajustar el perfil de un restaurante y buscar una
    farmacia, el perfil de la farmacia es el de por defecto."""
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    seg = next(m for m in pagina.multiselect if m.label == "Le vendes a…")
    seg.set_value(seg.value[:-1]).run()
    assert any("Perfil personalizado" in i.value for i in pagina.info)
    pagina.text_input[0].set_value("una farmacia")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    assert any("Interpretado como" in s.value for s in pagina.success)
    assert not any("Perfil personalizado" in i.value for i in pagina.info)
    assert any("Farmacia, clínica o consulta" in t.value for t in pagina.caption)
