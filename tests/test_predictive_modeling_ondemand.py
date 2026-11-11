"""Pruebas del modelado predictivo BAJO DEMANDA del dashboard.

Regresión: Streamlit ejecuta el contenido de TODAS las pestañas en cada rerun, así que los
cuatro modelos se entrenaban de golpe al abrir Analyst (con la base real: ~75 s con 16 CPUs y
~9 min dentro del contenedor del dashboard, de 1 CPU y 1 GiB, donde además rozaba el límite de
memoria). Ahora se entrena solo lo que el usuario pide.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest

from streamlit_app.dashboards import predictive_modeling_dashboard as pm
from tests.test_predictive_modeling_dashboard import _datos

FIT = {
    "clf": "_fit_classification",
    "reg": "_fit_regression",
    "temporal": "_fit_temporal",
    "cluster": "_fit_clustering",
}

APP = f"""
import sys
sys.path.insert(0, r'{ROOT}')
from streamlit_app.dashboards import predictive_modeling_dashboard as pm
pm.render()
"""


@pytest.fixture
def llamadas(monkeypatch):
    """Sustituye load_modeling_data por datos sintéticos (sin tocar la base real) y envuelve cada
    _fit_* para anotar cuándo se pide entrenar algo. Devuelve la lista de claves llamadas."""
    df = _datos()
    # 5 corredores: el clustering por defecto agrupa en 3 y necesita al menos esa cantidad
    # (la base real tiene 12).
    pares = [
        ("Msida", "Gzira"),
        ("Msida", "Sliema"),
        ("Valletta", "Sliema"),
        ("Msida", "Valletta"),
        ("Gzira", "Sliema"),
    ]
    df["origin"] = [pares[i % 5][0] for i in range(len(df))]
    df["destination"] = [pares[i % 5][1] for i in range(len(df))]
    monkeypatch.setattr(pm, "load_modeling_data", lambda: df)
    registro = []
    for clave, nombre in FIT.items():
        original = getattr(pm, nombre)

        def envoltorio(*args, _clave=clave, _orig=original, **kwargs):
            registro.append(_clave)
            return _orig(*args, **kwargs)

        monkeypatch.setattr(pm, nombre, envoltorio)
    return registro


def _app():
    at = AppTest.from_string(APP, default_timeout=180)
    at.run()
    return at


def _botones(at):
    return {b.key for b in at.button}


def test_las_secciones_coinciden_con_los_modelos():
    """Las secciones de la pantalla coinciden con los modelos que se pueden entrenar."""
    assert set(pm.SECCIONES) == set(FIT)


def test_al_abrir_no_se_entrena_nada(llamadas):
    """Al abrir la pantalla no se entrena ningún modelo; solo se muestran los botones y las métricas baratas de resumen."""
    at = _app()
    assert not at.exception, [e.value for e in at.exception]
    assert llamadas == [], "no debe entrenarse ningún modelo hasta que el usuario lo pida"
    assert _botones(at) == {"pm_btn_all", "pm_btn_clf", "pm_btn_reg", "pm_btn_temporal", "pm_btn_cluster"}
    # lo barato sí se muestra: las métricas de resumen de los datos
    assert {m.label for m in at.metric} >= {"Registros modelados", "Corredores"}


def test_pulsar_un_boton_entrena_solo_esa_seccion(llamadas):
    """Pulsar el botón de una sección entrena solo esa y el botón se reemplaza por su resultado."""
    at = _app()
    at.button(key="pm_btn_reg").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert set(llamadas) == {"reg"}
    assert "pm_btn_reg" not in _botones(at), "ya pedido: el botón se reemplaza por el resultado"
    assert {"pm_btn_clf", "pm_btn_temporal", "pm_btn_cluster"} <= _botones(at), "las demás siguen sin entrenar"


def test_lo_pedido_se_mantiene_en_la_sesion(llamadas):
    """Lo ya pedido se conserva entre reejecuciones de la página, sin pedir de nuevo otras secciones."""
    at = _app()
    at.button(key="pm_btn_cluster").click().run()
    llamadas.clear()
    at.run()  # cualquier otro rerun (otro clic, un slider...)
    assert "pm_btn_cluster" not in _botones(at)
    assert set(llamadas) == {"cluster"}  # la sección sigue visible; nada más se entrena


def test_el_boton_de_todos_entrena_las_cuatro_secciones(llamadas):
    """El botón de «todos» entrena las cuatro secciones."""
    at = _app()
    at.button(key="pm_btn_all").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert set(llamadas) == set(FIT)
    assert _botones(at) == {"pm_btn_all"}


def test_el_forecast_temporal_funciona_con_low_memory(llamadas):
    """El SARIMA usa fit(low_memory=True): se comprueba que el pronóstico y su intervalo se pueden
    obtener (sin resultados suavizados ni predicción en muestra, que low_memory no ofrece), y que la
    pantalla muestra la referencia y la nota de validación."""
    at = _app()
    at.button(key="pm_btn_temporal").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert set(llamadas) == {"temporal"}
    texto = " ".join(c.value for c in at.caption)
    assert "horas de calendario" in texto and "datos faltantes" in texto
    assert "convergió" in texto
    assert any("media de cada hora del día" in i.value for i in at.info)
