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


def test_la_tabla_publicada_no_ofrece_brecha_en_ninguna_categoria():
    """La brecha se retiró de `data/ml/` (docs/DATOS_Y_LICENCIAS.md): ni capa, ni aviso, ni intervalo en la ficha."""
    for categoria in ("food_drink", "business", "hospital"):
        at = abrir(categoria)
        assert not any("Brecha" in o for o in at.radio[0].options), categoria
        assert not any("Brecha" in w.value for w in at.warning), categoria
        assert not any(
            "modelo de brecha" in c for c in textos(at.caption)
        ), categoria  # ni se habla de un modelo que no hay
        assert any(
            "se retiró la brecha de oferta" in c for c in textos(at.caption)
        ), categoria  # y se dice que se retiró
        lentes = {
            "Competencia directa (conteo ponderado)",
            "Mercado (índice 0-1)",
            "Proveedores (conteo ponderado)",
            "Diversidad de proveedores (0-1)",
        }
        assert at.radio[0].options and set(at.radio[0].options) <= lentes, categoria  # solo lentes, nada más


def test_las_capas_son_las_tres_lentes_y_la_brecha_solo_donde_existe(datos_ml_con_brecha):
    """Con una brecha (sintética), food_drink la ofrece como capa exploratoria; hospital no la tiene."""
    con, sin = abrir("food_drink", datos_ml_con_brecha), abrir("hospital", datos_ml_con_brecha)
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


def _vista_y_mapa(capa=None, elegida="auto", acercar=False, con_lugares=True):
    from src.ml import panorama_view as pv
    from src.ml.business_profiles import DEFAULT_PROFILES
    from streamlit_app.dashboards import panorama_section as ps

    guardado, counts, _ = ps.load_data(ROOT / "data" / "ml")
    vista = pv.compute_view(counts, DEFAULT_PROFILES["food_drink"], guardado, "food_drink")
    if con_lugares:
        vista = pv.attach_places(vista, ps.load_places(ROOT / "data" / "ml"))
    capa = capa or pv.available_layers(vista)[0]
    sel = vista.index[0] if elegida == "auto" else elegida
    return vista, sel, ps.build_map(vista, capa, sel, acercar)


def _trazas_elegida(fig):
    return [t for t in fig.data if t.name == "celda elegida"]


def test_el_mapa_rotula_la_celda_elegida_con_su_calle():
    """El punto azul lleva el identificador y el lugar, para saber cuál es sin abrir la ficha."""
    from src.ml import panorama_view as pv

    vista, sel, fig = _vista_y_mapa()
    marcador = next(t for t in _trazas_elegida(fig) if t.mode == "markers+text")
    assert marcador.text == (f"{sel} · {pv.place_label(vista.loc[sel])}",)
    assert vista.loc[sel, "calle"] in marcador.text[0]


def test_el_mapa_dibuja_la_celda_como_el_cuadrado_de_250_m_que_es():
    """Un punto no deja ver qué área es: la celda elegida se dibuja con sus cuatro lados, cerrados."""
    from src.ml import grid

    _, sel, fig = _vista_y_mapa()
    cuadro = next(t for t in _trazas_elegida(fig) if t.mode == "lines")
    sur, oeste, norte, este = grid.cell_bounds(*grid.parse_cell_id(sel))
    assert cuadro.fill == "toself" and len(cuadro.lat) == 5
    assert cuadro.lat[0] == cuadro.lat[-1] and cuadro.lon[0] == cuadro.lon[-1]  # cerrado
    assert set(cuadro.lat) == {sur, norte} and set(cuadro.lon) == {oeste, este}


def test_acercar_centra_el_mapa_en_la_celda_y_se_ven_las_calles():
    """Sin acercar, el mapa muestra toda la rejilla y la celda es un punto perdido en la isla."""
    from streamlit_app.dashboards import panorama_section as ps

    vista, sel, lejos = _vista_y_mapa(acercar=False)
    _, _, cerca = _vista_y_mapa(acercar=True)
    assert lejos.layout.mapbox.zoom == ps.ZOOM_ISLA
    assert cerca.layout.mapbox.zoom == ps.ZOOM_CELDA > 14  # a este zoom el mapa base ya rotula las calles
    assert cerca.layout.mapbox.center.lat == pytest.approx(vista.loc[sel, "lat"])
    assert cerca.layout.mapbox.center.lon == pytest.approx(vista.loc[sel, "lon"])
    assert lejos.layout.mapbox.center.lat == pytest.approx(vista["lat"].mean())


def test_acercar_sin_celda_elegida_no_cambia_la_vista():
    """No hay a qué acercarse: el mapa se queda como está en vez de centrarse en cualquier sitio."""
    from streamlit_app.dashboards import panorama_section as ps

    _, _, fig = _vista_y_mapa(elegida=None, acercar=True)
    assert fig.layout.mapbox.zoom == ps.ZOOM_ISLA


def test_el_mapa_sin_celda_elegida_no_dibuja_el_marcador():
    """Si no hay celda elegida no se añade ningún marcador, rótulo ni cuadrado extra."""
    _, _, fig = _vista_y_mapa(elegida=None)
    assert not _trazas_elegida(fig)


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
def test_la_brecha_de_la_ficha_se_etiqueta_como_exploratoria_y_no_validada(datos_ml_con_brecha):
    """Donde hay brecha (sintética), la ficha la muestra con la advertencia de que no está validada y el intervalo no es de confianza."""
    at = abrir("food_drink", datos_ml_con_brecha)
    aviso = next(w.value for w in at.warning if "Brecha de oferta EXPLORATORIA" in w.value)
    assert "no validada" in aviso and "no es de confianza" in aviso


def test_sin_brecha_no_hay_advertencia_de_brecha():
    """En una categoría sin brecha no aparece ninguna advertencia sobre ella."""
    at = abrir("hospital")
    assert not any("Brecha" in w.value for w in at.warning)


def test_elegir_la_capa_de_brecha_muestra_la_advertencia_de_capa(datos_ml_con_brecha):
    """Cambiar a la capa de brecha añade el aviso de que es exploratoria y puede reflejar solo la saturación."""
    at = abrir("food_drink", datos_ml_con_brecha)
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


def test_cambiar_el_perfil_no_cambia_la_brecha_y_la_pantalla_lo_dice(datos_ml_con_brecha):
    """La brecha (sintética) de la misma celda es idéntica con el perfil por defecto y con uno personalizado, y la ficha
    avisa de que usa las categorías estándar."""
    at = abrir("food_drink", datos_ml_con_brecha)

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


def test_con_brecha_la_pantalla_si_menciona_el_modelo_de_brecha(datos_ml_con_brecha):
    at = abrir("food_drink", datos_ml_con_brecha)
    assert any("modelo de brecha" in c for c in textos(at.caption))
    assert not any("se retiró la brecha de oferta" in c for c in textos(at.caption))


def test_una_categoria_sin_brecha_no_habla_del_modelo_aunque_otras_categorias_lo_tengan(datos_ml_con_brecha):
    at = abrir("hospital", datos_ml_con_brecha)
    assert not any("modelo de brecha" in c for c in textos(at.caption))


# ---- celdas de la zona, lentes por zona y exportación a CSV ------------------------------------------------------
def clave_tabla(at, categoria="food_drink"):
    """La clave de la tabla de celdas lleva la huella de sus filas (ver firma_tabla): se busca la vigente."""
    (clave,) = [k for k in at.session_state.filtered_state if k.startswith(f"pano_top_{categoria}_")]
    return clave


def marcar(at, filas, categoria="food_drink"):
    at.session_state[clave_tabla(at, categoria)] = {"selection": {"rows": list(filas), "columns": []}}


def boton(at, empieza):
    return next(b for b in at.button if b.label.startswith(empieza))


def descargas(at):
    return [d.proto.label for d in at.get("download_button")]


def test_la_seccion_con_zona_lista_sus_celdas_y_las_lentes_por_zona():
    """Con la zona recomendada, la tabla es de esa zona; el resumen por zona trae las 7."""
    at = abrir_con_zona("food_drink", "Valletta")
    assert any("Celdas de la zona Valletta" in m for m in textos(at.markdown))
    assert any("Lentes del panorama por zona" in m for m in textos(at.markdown))
    assert len(at.dataframe) == 2 and len(at.dataframe[1].value) == len(LOCATIONS)
    assert any("No es un puntaje" in c for c in textos(at.caption))


def abrir_con_zona(categoria, zona, datos=None):
    codigo = APP_SECCION.replace(
        "render_panorama_section({categoria!r}, {datos!r})",
        "render_panorama_section({categoria!r}, {datos!r}, zona={zona!r})",
    )
    at = AppTest.from_string(
        codigo.format(raiz=str(ROOT), categoria=categoria, datos=str(datos) if datos else None, zona=zona),
        default_timeout=120,
    )
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_sin_zona_la_tabla_es_de_todas_las_zonas():
    at = abrir("food_drink")
    assert any("Celdas de todas las zonas" in m for m in textos(at.markdown))


def test_sin_marcar_filas_no_se_puede_confirmar_ni_hay_descarga():
    at = abrir_con_zona("food_drink", "Valletta")
    b = boton(at, "Confirmar selección (0)")
    assert b.proto.disabled and descargas(at) == []
    assert any("Marca filas de la tabla" in c for c in textos(at.caption))


def test_la_descarga_solo_aparece_tras_confirmar_la_seleccion():
    """Marcar filas no basta: el CSV se prepara al pulsar «Confirmar», y es exactamente de las celdas marcadas."""
    from src.ml import panorama_view as pv

    at = abrir_con_zona("food_drink", "Valletta")
    marcar(at, [0, 2])
    at.run()
    assert descargas(at) == []  # marcadas, sin confirmar
    marcar(at, [0, 2])  # AppTest no conserva la selección de una tabla entre ejecuciones: se repite al pulsar
    boton(at, "Confirmar selección (2)").click().run()
    assert not at.exception and descargas(at) == ["⬇️ Descargar CSV de 2 celda(s) confirmada(s)"]
    from streamlit_app.dashboards import panorama_section as ps

    guardado, counts, _ = ps.load_data(ROOT / "data" / "ml")
    vista = pv.attach_places(
        pv.compute_view(counts, bp.get_default_profile("food_drink"), guardado, "food_drink"),
        ps.load_places(ROOT / "data" / "ml"),
    )
    esperadas = list(pv.candidate_cells(vista, "Valletta").index[[0, 2]])
    assert at.session_state["pano_conf_food_drink"]["ids"] == esperadas


def test_si_la_seleccion_cambia_despues_de_confirmar_se_avisa():
    at = abrir_con_zona("food_drink", "Valletta")
    marcar(at, [0])
    at.run()
    marcar(at, [0])
    boton(at, "Confirmar selección (1)").click().run()
    marcar(at, [0, 1])
    at.run()
    assert any("vuelve a confirmar" in c for c in textos(at.caption))
    assert descargas(at) == ["⬇️ Descargar CSV de 1 celda(s) confirmada(s)"]  # sigue la confirmada, no la nueva


def test_el_toggle_amplia_la_tabla_de_15_filas_a_todas():
    at = abrir_con_zona("food_drink", "Valletta")
    assert len(at.dataframe[0].value) == 15
    at.toggle[0].set_value(True).run()
    assert len(at.dataframe[0].value) > 15


def test_la_pagina_pone_las_celdas_bajo_la_zona_recomendada_y_las_lentes_bajo_el_desglose(pagina):
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    m = textos(pagina.markdown)
    pos = {
        k: next(i for i, t in enumerate(m) if k in t)
        for k in ("Celdas de la zona", "Desglose por zona", "Lentes del panorama por zona")
    }
    assert pos["Celdas de la zona"] < pos["Desglose por zona"] < pos["Lentes del panorama por zona"]
    zona = pagina.metric[0].value
    assert f"Celdas de la zona {zona}" in m[pos["Celdas de la zona"]]


def test_cambiar_el_perfil_descarta_la_seleccion_confirmada():
    """Regresión del code-review: el CSV se genera con el perfil vigente, así que una confirmación hecha con otro perfil
    mezclaría la selección vieja con lentes nuevas. Se descarta y se avisa."""
    at = abrir_con_zona("food_drink", "Valletta")
    marcar(at, [0])
    at.run()
    marcar(at, [0])
    boton(at, "Confirmar selección (1)").click().run()
    assert len(descargas(at)) == 1
    multiselect(at, "Competencia indirecta (sustitutos)").set_value([]).run()
    assert not at.exception and descargas(at) == []
    assert any("Se descartó la selección confirmada" in c for c in textos(at.caption))
    assert "pano_conf_food_drink" not in at.session_state


def test_si_la_tabla_cambia_la_seleccion_de_filas_no_se_arrastra():
    """Regresión del code-review: la selección es por posición de fila. Marcar la 20 con «ver todas» y apagar el interruptor
    dejaba una posición fuera de la tabla (IndexError); ahora la tabla cambia de clave y empieza sin filas marcadas."""
    at = abrir_con_zona("food_drink", "Valletta")
    at.toggle[0].set_value(True).run()
    marcar(at, [20])
    at.run()
    assert boton(at, "Confirmar selección (1)")
    at.toggle[0].set_value(False).run()
    assert not at.exception, [e.value for e in at.exception]
    assert boton(at, "Confirmar selección (0)").proto.disabled


def test_una_zona_desconocida_no_rompe_la_seccion():
    at = abrir_con_zona("food_drink", "Atlantis")
    assert any("Celdas de todas las zonas" in m for m in textos(at.markdown))


def test_el_hover_del_mapa_escapa_el_html_de_la_localidad():
    """La localidad viene de una fuente externa y editable: no se interpola como HTML en el hover de Plotly."""
    from src.ml import panorama_view as pv
    from streamlit_app.dashboards import panorama_section as ps

    guardado, counts, _ = ps.load_data(ROOT / "data" / "ml")
    vista = pv.compute_view(counts, bp.get_default_profile("food_drink"), guardado, "food_drink")
    vista["localidad"] = "<img src=x>&Co"
    fig = ps.build_map(vista, pv.available_layers(vista)[0], None)
    texto = next(t for t in fig.data if t.name not in ("sin datos",)).hovertext[0]
    assert "<img" not in texto and "&lt;img src=x&gt;&amp;Co" in texto


# ---- ver el área concreta: calle en el rótulo y mapa acercado ----------------------------------------------------
def toggle(at, empieza):
    return next(t for t in at.toggle if t.label.startswith(empieza))


def test_la_seccion_ofrece_acercar_a_la_celda_y_viene_activado():
    """Lo que faltaba era ver el sitio: el mapa llega acercado y se puede alejar para comparar."""
    at = abrir("food_drink")
    t = toggle(at, "🔍 Acercar")
    assert t.value is True
    assert any("cuadrado de 250 m" in c for c in textos(at.caption))
    t.set_value(False).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Acércate con el control" in c for c in textos(at.caption))


def test_la_ficha_y_la_lista_dicen_la_calle_no_solo_el_pueblo():
    """La ficha encabeza con «calle, pueblo» y la lista de celdas también."""
    from src.ml import panorama_view as pv
    from streamlit_app.dashboards import panorama_section as ps

    lugares = ps.load_places(ROOT / "data" / "ml")
    at = abrir("food_drink")
    cell_id = at.selectbox[0].value  # AppTest da el valor de la opción; la etiqueta la pone format_func
    calle = lugares.loc[cell_id, "calle"]
    assert calle and calle in pv.cell_label(cell_id, lugares.loc[cell_id])
    ficha = next(m for m in textos(at.markdown) if m.startswith("##### Ficha de la celda"))
    assert cell_id in ficha and calle in ficha
    assert any("Zona de referencia:" in c for c in textos(at.caption))


def test_la_tabla_de_la_zona_ya_no_repite_el_mismo_pueblo_en_cada_fila():
    """El motivo del cambio, comprobado en la pantalla: en Birkirkara la columna «Lugar» decía siempre «Birkirkara»."""
    at = abrir_con_zona("food_drink", "Birkirkara")
    lugares = list(at.dataframe[0].value["Lugar"])
    assert len(lugares) > 5
    assert len(set(lugares)) >= len(lugares) - 2  # casi una calle distinta por fila
    assert not all(l == "Birkirkara" for l in lugares)


def test_sin_el_archivo_de_lugares_la_pantalla_sigue_funcionando(tmp_path):
    """Si cell_places.csv falta, se rotula con la zona de referencia y no se rompe nada."""
    copia = tmp_path / "ml"
    shutil.copytree(ROOT / "data" / "ml", copia)
    (copia / "cell_places.csv").unlink()
    (copia / "cell_places_manifest.json").unlink()
    at = abrir("food_drink", copia)
    assert not at.exception, [e.value for e in at.exception]
    assert all(l.startswith("cerca de ") for l in at.dataframe[0].value["Lugar"])


def test_el_rotulo_de_la_celda_elegida_tambien_escapa_el_html():
    """Code-review: el hover escapaba el nombre de OSM pero el rótulo del punto azul no."""
    from src.ml import panorama_view as pv
    from streamlit_app.dashboards import panorama_section as ps

    guardado, counts, _ = ps.load_data(ROOT / "data" / "ml")
    vista = pv.compute_view(counts, bp.get_default_profile("food_drink"), guardado, "food_drink")
    vista["calle"], vista["localidad"] = "<b>Triq</b>", "A&B"
    sel = vista.index[0]
    fig = ps.build_map(vista, pv.available_layers(vista)[0], sel)
    rotulo = next(t for t in fig.data if t.name == "celda elegida" and t.mode == "markers+text").text[0]
    assert "<b>" not in rotulo and "&lt;b&gt;Triq&lt;/b&gt;, A&amp;B" in rotulo


def test_la_ficha_escapa_el_marcado_del_nombre_de_osm():
    """QA de Codex (menor): un nombre de OSM con sintaxis Markdown alteraba el encabezado de la ficha."""
    from streamlit_app.dashboards import panorama_section as ps

    assert ps.escapar_markdown("Triq *il* _Kbira_") == r"Triq \*il\* \_Kbira\_"
    assert ps.escapar_markdown("A & B") == "A & B"  # lo que no es marcado no se toca
    assert ps.escapar_markdown("Triq il-Kbira") == "Triq il-Kbira"


def test_la_ficha_de_una_celda_real_no_lleva_escapes_de_mas():
    """El escape no debe ensuciar los nombres corrientes, que son la inmensa mayoría."""
    at = abrir("food_drink")
    ficha = next(m for m in textos(at.markdown) if m.startswith("##### Ficha de la celda"))
    assert "\\" not in ficha


# ---- celdas dentro del mapa de recomendación ---------------------------------------------------------------------
def _mapa_reco(zona="Birkirkara", capa=None, isla=False, con_panorama=True, marcadas=()):
    """(out, panorama, figura) del mapa de arriba, sin levantar la pantalla."""
    import pandas as pd

    from src.locations import LOCATIONS
    from src.ml import panorama_view as pv
    from streamlit_app.dashboards import panorama_section as ps
    from streamlit_app.dashboards import recommendation_dashboard as rd

    out = pd.DataFrame(
        {"score": [0.9 - 0.1 * i for i in range(len(LOCATIONS))]},
        index=pd.Index(list(LOCATIONS), name="zone_name"),
    )
    pano = None
    if con_panorama:
        guardado, counts, _ = ps.load_data(ROOT / "data" / "ml")
        vista = pv.attach_places(
            pv.compute_view(counts, bp.get_default_profile("food_drink"), guardado, "food_drink"),
            ps.load_places(ROOT / "data" / "ml"),
        )
        pano = ps.Panorama(vista=vista, perfil=bp.get_default_profile("food_drink"), marcadas=list(marcadas))
        capa = capa or pv.available_layers(vista)[rd.capa_por_defecto(pv.available_layers(vista))]
    return out, pano, rd.build_score_map(out, pano, zona, capa, isla)


def test_el_mapa_de_recomendacion_dibuja_las_celdas_de_la_zona():
    """Lo que faltaba: el mapa de arriba solo tenía 7 puntos de ciudad. Ahora trae las celdas de la zona recomendada."""
    from src.ml import panorama_view as pv

    out, pano, fig = _mapa_reco()
    celdas = next(t for t in fig.data if t.name not in ("zonas", "sin datos") and t.mode == "markers")
    esperadas = pano.vista[pv.zone_cells(pano.vista, "Birkirkara")]
    assert len(celdas.lat) == len(esperadas) > 50
    assert set(celdas.lat) == set(esperadas["lat"])


def test_el_mapa_de_recomendacion_se_centra_en_la_zona_no_en_la_isla():
    from src.locations import LOCATIONS
    from streamlit_app.dashboards import recommendation_dashboard as rd

    _, _, cerca = _mapa_reco()
    assert cerca.layout.mapbox.zoom == rd.ZOOM_ZONA > rd.ZOOM_ISLA
    assert cerca.layout.mapbox.center.lat == pytest.approx(LOCATIONS["Birkirkara"].latitude)
    _, _, lejos = _mapa_reco(isla=True)
    assert lejos.layout.mapbox.zoom == rd.ZOOM_ISLA


def test_el_hover_de_una_celda_dice_su_calle_y_escapa_el_html():
    out, pano, fig = _mapa_reco()
    celdas = next(t for t in fig.data if t.name not in ("zonas", "sin datos") and t.mode == "markers")
    assert any(", Birkirkara<br>" in t for t in celdas.hovertext)
    pano.vista["calle"] = "<b>Triq</b>"
    from streamlit_app.dashboards import recommendation_dashboard as rd

    fig2 = rd.build_score_map(out, pano, "Birkirkara", "Mercado (índice 0-1)")
    hov = next(t for t in fig2.data if t.name not in ("zonas", "sin datos") and t.mode == "markers").hovertext[0]
    assert "<b>" not in hov and "&lt;b&gt;Triq&lt;/b&gt;" in hov


def test_las_celdas_marcadas_en_la_tabla_salen_como_su_cuadrado():
    from src.ml import panorama_view as pv
    from streamlit_app.dashboards import panorama_section as ps

    _, pano0, _ = _mapa_reco()
    dos = list(pano0.vista[pv.zone_cells(pano0.vista, "Birkirkara")].index[:2])
    _, _, fig = _mapa_reco(marcadas=dos)
    cuadros = [t for t in fig.data if t.name == "celda marcada"]
    assert len(cuadros) == 2
    lat_sq, _ = ps.cuadrado_celda(dos[0])
    assert list(cuadros[0].lat) == lat_sq and cuadros[0].fill == "toself"
    # una celda marcada que no está en la zona no se dibuja
    _, _, sin = _mapa_reco(marcadas=["r02c08"])
    assert not [t for t in sin.data if t.name == "celda marcada"]


def test_sin_panorama_el_mapa_sigue_siendo_el_de_zonas_con_su_puntaje():
    """Si falta data/ml el mapa no debe romperse: vuelve al de siempre, con la barra de color del puntaje."""
    out, pano, fig = _mapa_reco(con_panorama=False)
    assert pano is None and len(fig.data) == 1
    zonas = fig.data[0]
    assert zonas.marker.showscale and zonas.marker.colorbar.title.text == "Puntaje"
    assert list(zonas.text) == list(out.index)


def test_con_celdas_la_barra_de_color_es_la_lente_y_la_zona_recomendada_se_distingue():
    """Dos barras de color en un mapa no se leen: con celdas, la barra es de la lente y las zonas van por color plano."""
    out, _, fig = _mapa_reco()
    zonas = next(t for t in fig.data if t.name == "zonas")
    assert not zonas.marker.showscale
    assert list(zonas.marker.color) == ["#1a7f37" if z == "Birkirkara" else "#8a8a8a" for z in out.index]
    celdas = next(t for t in fig.data if t.name not in ("zonas", "sin datos") and t.mode == "markers")
    assert celdas.marker.showscale


def test_la_lente_por_defecto_del_mapa_es_el_mercado():
    from src.ml import panorama_view as pv
    from streamlit_app.dashboards import recommendation_dashboard as rd

    capas = list(pv.CAPAS)
    assert capas[rd.capa_por_defecto(capas)].startswith("Mercado")
    assert rd.capa_por_defecto(["Solo una"]) == 0  # sin mercado disponible, la primera


def test_una_zona_desconocida_no_dibuja_celdas_pero_tampoco_falla():
    _, _, fig = _mapa_reco(zona="Atlantis")
    assert [t.name for t in fig.data] == ["zonas"]


def test_la_pagina_pone_el_mapa_con_celdas_entre_la_tabla_y_el_desglose(pagina):
    """El mapa de arriba es el de la decisión: va bajo la zona recomendada y sus celdas, antes del desglose por zona."""
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    assert any(r.label == "Color de las celdas" for r in pagina.radio)
    assert any(t.label == "Ver toda la isla" for t in pagina.toggle)
    m = textos(pagina.markdown)
    pos = {k: next(i for i, t in enumerate(m) if k in t) for k in ("Celdas de la zona", "Desglose por zona")}
    assert pos["Celdas de la zona"] < pos["Desglose por zona"]
    assert any("El color de las celdas es una lente, no el puntaje de la zona" in c for c in textos(pagina.caption))


def test_sin_datos_de_celda_la_pagina_mantiene_el_mapa_de_zonas(pagina, tmp_path, monkeypatch):
    """Si falta data/ml no hay celdas que dibujar, pero la recomendación por zona sigue entera."""
    from streamlit_app.dashboards import panorama_section as ps

    monkeypatch.setattr(ps, "DATA_ML", tmp_path)
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    assert not any(r.label == "Color de las celdas" for r in pagina.radio)
    assert any("zonas que estás comparando" in c for c in textos(pagina.caption))
    assert any("Zona recomendada" in m.label for m in pagina.metric)


def test_el_mapa_de_recomendacion_no_ofrece_la_brecha_exploratoria(datos_ml_con_brecha, monkeypatch):
    """Code-review: la brecha no está validada y este es el mapa con el que se decide. Vive en el panorama, con su aviso."""
    from src.ml import panorama_view as pv
    from streamlit_app.dashboards import panorama_section as ps
    from streamlit_app.dashboards import recommendation_dashboard as rd

    guardado, counts, _ = ps.load_data(datos_ml_con_brecha)
    vista = pv.compute_view(counts, bp.get_default_profile("food_drink"), guardado, "food_drink")
    assert pv.CAPA_BRECHA in pv.available_layers(vista)  # el panorama sí la ofrece
    assert pv.CAPA_BRECHA not in rd.capas_del_mapa(vista)  # este mapa no


def test_las_celdas_sin_dato_de_la_lente_salen_en_gris_y_se_cuentan():
    """Code-review: antes se omitían en silencio mientras el texto afirmaba que estaban todas."""
    import numpy as np

    from src.ml import panorama_view as pv
    from streamlit_app.dashboards import recommendation_dashboard as rd

    out, pano, _ = _mapa_reco()
    celda = pano.vista[pv.zone_cells(pano.vista, "Birkirkara")].index[0]
    pano.vista.loc[celda, "mercado_total"] = np.nan
    fig = rd.build_score_map(out, pano, "Birkirkara", "Mercado (índice 0-1)")
    grises = [t for t in fig.data if t.name == "sin datos"]
    assert len(grises) == 1 and len(grises[0].lat) == 1
    assert "sin datos" in grises[0].hovertext[0]


def test_las_claves_del_mapa_llevan_la_categoria(pagina):
    """Code-review: eran globales, así que la lente elegida se arrastraba al buscar otro negocio."""
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert "reco_capa_celdas_food_drink" in pagina.session_state
    pagina.text_input[0].set_value("una farmacia")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    assert "reco_capa_celdas_hospital" in pagina.session_state


APP_MAPA = """
import sys
from pathlib import Path
sys.path.insert(0, {raiz!r})
import pandas as pd
from src.locations import LOCATIONS
from src.ml import business_profiles as bp
from src.ml import panorama_view as pv
from streamlit_app.dashboards import panorama_section as ps
from streamlit_app.dashboards import recommendation_dashboard as rd

datos = Path({datos!r})
guardado, counts, _ = ps.load_data(datos)
perfil = bp.get_default_profile("food_drink")
vista = pv.attach_places(pv.compute_view(counts, perfil, guardado, "food_drink"), ps.load_places(datos))
pano = ps.Panorama(vista=vista, perfil=perfil, marcadas=[])
out = pd.DataFrame({{"score": [0.9 - 0.1 * i for i in range(len(LOCATIONS))]}}, index=list(LOCATIONS))
rd.render_score_map(out, pano, {zona!r}, "food_drink")
"""


def abrir_mapa(zona):
    """La pantalla del mapa de recomendación sola, CON panorama real, para probar la rama de cada zona."""
    at = AppTest.from_string(
        APP_MAPA.format(raiz=str(ROOT), datos=str(ROOT / "data" / "ml"), zona=zona), default_timeout=120
    )
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_con_zona_desconocida_no_se_ofrece_la_lente_ni_se_habla_de_celdas():
    """Code-review: salía el selector de lente y un texto de «0 celdas de Atlantis» sobre un mapa que era el de zonas.

    QA de Codex: antes este test anulaba el panorama, con lo que probaba el camino «sin datos», no este. Ahora el
    panorama es real y lo único raro es la zona, que es justo la condición que se quiere ejercitar."""
    conocida = abrir_mapa("Birkirkara")
    assert any(r.label == "Color de las celdas" for r in conocida.radio)

    desconocida = abrir_mapa("Atlantis")
    assert not any(r.label == "Color de las celdas" for r in desconocida.radio)
    assert not desconocida.toggle  # tampoco el de «ver toda la isla»
    textos_c = [c.value for c in desconocida.caption]
    assert any("zonas que estás comparando" in c for c in textos_c)
    assert not any("Atlantis" in c or "celdas de 250 m" in c for c in textos_c)


# ---- ajustes: filtro de zonas y seis criterios -------------------------------------------------------------------
def test_los_ajustes_ofrecen_un_deslizador_por_criterio_disponible(pagina):
    """Con data/ml hay más de tres factores, y están los tres nuevos. La base de prueba no tiene rutas guardadas, así
    que accesibilidad no se ofrece: un criterio sin datos no debe salir como si se pudiera usar."""
    from src import location_scoring as ls

    pagina.run()
    etiquetas = {s.label for s in pagina.slider}
    assert etiquetas <= {c.etiqueta for c in ls.CRITERIOS}
    assert len(etiquetas) > 3
    assert {"Mercado por segmento (proxy OSM)", "Proveedores cerca", "Diversidad de proveedores"} <= etiquetas
    assert "Accesibilidad" not in etiquetas  # sin rutas en esta base


def test_el_filtro_de_zonas_viene_con_todas_y_es_un_filtro_no_un_peso(pagina):
    """La decisión del autor: elegir zonas quita filas, no cambia el puntaje de las que quedan."""
    from src.locations import LOCATIONS

    pagina.run()
    zonas = next(m for m in pagina.multiselect if m.label == "Zonas a considerar")
    assert list(zonas.value) == list(LOCATIONS)
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()

    def puntajes():
        tabla = next(d.value for d in pagina.dataframe if "Zona" in getattr(d.value, "columns", []))
        return tabla.set_index("Zona")["Puntaje"]

    antes = puntajes()

    dos = ["Sliema", "Gzira"]
    next(m for m in pagina.multiselect if m.label == "Zonas a considerar").set_value(dos).run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    assert pagina.metric[0].value in dos
    assert any("Comparando **2 de 7 zonas**" in c for c in textos(pagina.caption))
    despues = puntajes()
    assert list(despues.index) == sorted(dos, key=lambda z: -antes[z])  # solo quedan esas, y en el mismo orden
    # QA de Codex: lo que de verdad hay que comprobar es que filtrar NO cambia la nota de las que quedan
    for zona in dos:
        assert despues[zona] == pytest.approx(antes[zona])


def test_dejar_el_filtro_vacio_avisa_y_usa_todas(pagina):
    from src.locations import LOCATIONS

    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    next(m for m in pagina.multiselect if m.label == "Zonas a considerar").set_value([]).run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    assert any("No dejaste ninguna zona" in w.value for w in pagina.warning)
    tabla = next(d for d in pagina.dataframe if "Zona" in getattr(d.value, "columns", []))
    assert len(tabla.value) == len(LOCATIONS)


def test_el_desglose_de_aportacion_sale_en_la_pantalla(pagina):
    """Cada factor puntuado tiene su columna en el desglose, y las filas suman el puntaje."""
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert any("De dónde sale cada puntaje" in e.label for e in pagina.expander)
    etiquetas = {s.label for s in pagina.slider}
    columnas = [list(getattr(d.value, "columns", [])) for d in pagina.dataframe]
    desglose = next(c for c in columnas if "Puntaje" in c and etiquetas <= set(c))
    tabla = next(d.value for d in pagina.dataframe if list(d.value.columns) == desglose)
    aportes = tabla[[c for c in desglose if c not in ("Zona", "Puntaje")]]
    assert aportes.sum(axis=1).round(9).equals(tabla["Puntaje"].round(9))


def test_poner_un_peso_en_cero_cambia_la_recomendacion(pagina):
    """Los pesos siguen mandando: todo el peso en población hace ganar a la zona más poblada."""
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    for s in pagina.slider:
        s.set_value(0)
    next(s for s in pagina.slider if s.label.startswith("Población")).set_value(100).run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    tabla = next(d for d in pagina.dataframe if "Población" in getattr(d.value, "columns", []))
    assert tabla.value["Población"].idxmax() == tabla.value["Puntaje"].idxmax()


# ---- correcciones del code-review de los ajustes -----------------------------------------------------------------
def test_los_criterios_dependen_de_la_categoria_no_de_una_sonda_fija(pagina):
    """Code-review (verificado con data/ml): `business`, `hospital` y `leisure` no tienen NINGÚN proveedor con datos,
    así que para una farmacia no deben ofrecerse «proveedores» ni «diversidad». Antes se sondeaba siempre con
    food_drink y salían dos deslizadores que el puntaje descartaba en silencio."""
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    con_proveedores = {s.label for s in pagina.slider}
    assert "Proveedores cerca" in con_proveedores

    pagina.text_input[0].set_value("una farmacia")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    sin_proveedores = {s.label for s in pagina.slider}
    assert "Proveedores cerca" not in sin_proveedores and "Diversidad de proveedores" not in sin_proveedores
    assert "Mercado por segmento (proxy OSM)" in sin_proveedores  # el mercado sí existe para todas
    assert any("No se ofrecen" in c and "Proveedores" in c for c in textos(pagina.caption))


def test_un_factor_en_cero_se_queda_fuera_del_puntaje_y_de_los_avisos(pagina):
    """Code-review: la ayuda promete «ponlo en 0 para dejarlo fuera», pero seguía contando como factor puntuado y
    disparaba el aviso de datos incompletos por algo que no aportaba nada."""
    from streamlit_app.dashboards.recommendation_dashboard import normalize_weights

    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    antes = next(d.value for d in pagina.dataframe if "Zona" in getattr(d.value, "columns", []))
    columnas_antes = [c for c in antes.columns if c.endswith("(0-1)")]

    next(s for s in pagina.slider if s.label == "Mercado por segmento (proxy OSM)").set_value(0).run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    despues = next(d.value for d in pagina.dataframe if "Zona" in getattr(d.value, "columns", []))
    assert len(columnas_antes) - 1 == len([c for c in despues.columns if c.endswith("(0-1)")])
    assert not [c for c in despues.columns if c.startswith("Mercado")]
    assert "Datos completos (de 4)" in despues.columns  # uno menos que antes

    pesos = normalize_weights({"demanda": 50, "competencia": 50, "mercado": 0}, [])
    assert "mercado" not in pesos and sum(pesos.values()) == pytest.approx(1.0)


def test_los_textos_hablan_de_los_factores_que_se_puntuaron(pagina):
    """Code-review: el pie decía «en las 6» mientras la tabla mostraba 4 columnas y «Datos completos (de 4)»."""
    pagina.run()
    pagina.text_input[0].set_value("una farmacia")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    tabla = next(d.value for d in pagina.dataframe if "Zona" in getattr(d.value, "columns", []))
    n = len([c for c in tabla.columns if c.endswith("(0-1)")])
    assert f"Datos completos (de {n})" in tabla.columns
    assert any(f"en las {n}, **más alto = mejor" in c for c in textos(pagina.caption))


def test_al_filtrar_zonas_el_mapa_no_dice_que_enseña_siete(pagina):
    """Code-review: con el filtro nuevo el mapa dibuja menos zonas, pero el texto seguía afirmando «las 7 zonas»."""
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    next(m for m in pagina.multiselect if m.label == "Zonas a considerar").set_value(["Sliema", "Gzira"]).run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    pies = textos(pagina.caption)
    assert not any("las 7 zonas" in c for c in pies)
    assert any("las 2 zonas que comparas" in c or "Las 2 zonas que estás comparando" in c for c in pies)


# ---- resumen final en pantalla -----------------------------------------------------------------------------------
def test_el_resumen_final_cierra_el_circulo_de_la_ciudad_a_la_calle(pagina):
    """Lo que el usuario pidió: al final, la zona ganadora con lo que la hizo ganar y las calles donde mirar."""
    from src.ml import panorama_view as pv
    from streamlit_app.dashboards import panorama_section as ps
    from streamlit_app.dashboards import recommendation_dashboard as rd

    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    assert not pagina.exception, [e.value for e in pagina.exception]

    assert any("En resumen" in s.value for s in pagina.subheader)
    md = textos(pagina.markdown)
    zona = pagina.metric[0].value
    assert any(f"**{zona}** es la mejor de las" in m for m in md)
    assert any("Lo que más pesa en ese puntaje" in m for m in md)
    assert any(f"Dónde mirar dentro de {zona}" in m for m in md)

    # las celdas que nombra son las primeras de esa zona, con su calle y su enlace
    guardado, counts, _ = ps.load_data(ROOT / "data" / "ml")
    vista = pv.attach_places(
        pv.compute_view(counts, bp.get_default_profile("food_drink"), guardado, "food_drink"),
        ps.load_places(ROOT / "data" / "ml"),
    )
    esperadas = list(pv.candidate_cells(vista, zona).head(rd.CELDAS_RESUMEN).index)
    assert esperadas, "la zona recomendada debería tener celdas"
    for cell_id in esperadas:
        assert any(f"`{cell_id}`" in m for m in md), cell_id
    assert any("ver en el mapa" in m and "openstreetmap.org" in m for m in md)
    assert any("El **puntaje es de la zona**" in c and "no una predicción" in c for c in textos(pagina.caption))


def test_el_resumen_va_al_final_despues_del_panorama(pagina):
    """«Al final»: el resumen cierra la pantalla, después de la ficha de celda del panorama."""
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    md = textos(pagina.markdown)
    ficha = max(i for i, t in enumerate(md) if t.startswith("##### Ficha de la celda"))
    resumen = next(i for i, t in enumerate(md) if "es la mejor de las" in t or "es la única zona" in t)
    assert resumen > ficha


def test_el_resumen_sigue_a_la_zona_cuando_se_filtra(pagina):
    """Si filtras zonas, el resumen habla de la que gana entre esas, no de la que ganaba antes."""
    pagina.run()
    pagina.text_input[0].set_value("un restaurante")
    next(b for b in pagina.button if "Buscar" in b.label).click().run()
    next(m for m in pagina.multiselect if m.label == "Zonas a considerar").set_value(["Sliema", "Gzira"]).run()
    assert not pagina.exception, [e.value for e in pagina.exception]
    zona = pagina.metric[0].value
    assert zona in ("Sliema", "Gzira")
    assert any(f"**{zona}** es la mejor de las 2 zonas" in m for m in textos(pagina.markdown))
