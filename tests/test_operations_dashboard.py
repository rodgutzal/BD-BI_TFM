"""Pantalla Operations (AppTest): se abre con datos y un error en una sección no tumba las demás."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.database import RouteDatabase  # noqa: E402
from streamlit_app.dashboards import operations_dashboard as op  # noqa: E402

APP_OPS = (
    f"import sys\nsys.path.insert(0, r'{ROOT}')\n"
    "from streamlit_app.dashboards import operations_dashboard as m\nm.main()\n"
)

SUBTITULOS = [
    "🚨 Real-Time Alerts",
    "📍 Route Status Overview",
    "📈 Últimas 24 horas por ruta",
    "🔥 Performance Heatmap (24-hour)",
]

# (función de la sección, nombre con el que se avisa del fallo)
SECCIONES_OPS = [
    ("render_real_time_alerts", "Real-Time Alerts"),
    ("render_route_status_grid", "Route Status Overview"),
    ("render_last_24h_summary", "Últimas 24 horas por ruta"),
    ("render_performance_heatmap", "Performance Heatmap"),
]


def _registro(minutos_atras, origin, destination, viaje, delay):
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)
    return {
        "timestamp": ts.isoformat(),
        "origin": origin,
        "destination": destination,
        "data_source": "tomtom",
        "travel_time_min": viaje,
        "traffic_delay_min": delay,
        "average_speed_kmh": 30.0,
        "distance_km": 3.0,
        "polyline": [[35.9, 14.5], [35.8, 14.4]],
    }


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base temporal con mediciones recientes de dos rutas; la pantalla la usa en vez de data/mobility.db."""
    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    db.save_records_to_sqlite(
        [
            _registro(m, o, d, viaje, delay)
            for m in (5, 35, 65, 95)
            for o, d, viaje, delay in (("Msida", "Gzira", 12.0, 1.0), ("Msida", "Sliema", 35.0, 9.0))
        ]
    )
    st.cache_data.clear()
    monkeypatch.setattr(op, "get_database", lambda: db)
    yield db
    st.cache_data.clear()


def _abrir():
    at = AppTest.from_string(APP_OPS, default_timeout=120)
    at.run()
    return at


def _falla(*_args, **_kw):
    raise RuntimeError("tabla inexistente")


def test_operations_abre_con_datos_y_muestra_sus_cuatro_secciones(base):
    """Operations se abre sin excepciones con datos, y muestra las cuatro secciones y el aviso final."""
    at = _abrir()
    assert not at.exception, [e.value for e in at.exception]
    assert [s.value for s in at.subheader] == SUBTITULOS
    assert any("Refresh the page" in i.value for i in at.info)
    assert not any("No se pudo mostrar" in e.value for e in at.error)


def test_operations_la_tabla_de_alertas_marca_la_ruta_lenta(base):
    """Con una ruta de más de 30 min de media en la última hora, las alertas la listan."""
    at = _abrir()
    alertas = [d.value for d in at.dataframe if "severity" in getattr(d.value, "columns", [])]
    assert len(alertas) == 1 and alertas[0]["route"].tolist() == ["Msida → Sliema"]


@pytest.mark.parametrize("funcion, nombre", SECCIONES_OPS)
def test_operations_un_error_en_una_seccion_se_muestra_en_ella_y_no_tumba_la_pagina(base, monkeypatch, funcion, nombre):
    """Cada sección (parametrizado) se aísla: se dice cuál falló y por qué, y la página sigue hasta el aviso final."""
    monkeypatch.setattr(op, funcion, _falla)
    at = _abrir()
    assert not at.exception, [e.value for e in at.exception]
    assert [e.value for e in at.error] == [f"No se pudo mostrar «{nombre}»: RuntimeError: tabla inexistente"]
    assert any("Refresh the page" in i.value for i in at.info)  # se llegó hasta el final de la pantalla


def test_operations_las_demas_secciones_siguen_mostrandose_cuando_una_falla(base, monkeypatch):
    """Con las alertas rotas, la tabla de estado y el resumen de 24 h (que vienen después) se siguen viendo."""
    monkeypatch.setattr(op, "render_real_time_alerts", _falla)
    at = _abrir()
    assert not at.exception and len(at.error) == 1
    assert [s.value for s in at.subheader] == SUBTITULOS[1:]
    assert any("Route" in getattr(d.value, "columns", []) and "Status" in d.value.columns for d in at.dataframe)
    assert any(c.value.startswith("Las demás secciones no se ven afectadas") for c in at.caption)


def test_operations_una_seccion_que_falla_a_mitad_no_deja_lo_que_ya_habia_dibujado(base, monkeypatch):
    """Si una sección dibuja un título y luego falla, ese título a medias se retira: solo queda el aviso."""

    def a_medias(_db):
        st.subheader("Parcial (no debería verse)")
        raise RuntimeError("se cayó a mitad")

    monkeypatch.setattr(op, "render_route_status_grid", a_medias)
    at = _abrir()
    assert not at.exception, [e.value for e in at.exception]
    assert "Parcial (no debería verse)" not in [s.value for s in at.subheader]
    assert [e.value for e in at.error] == ["No se pudo mostrar «Route Status Overview»: RuntimeError: se cayó a mitad"]


def test_operations_el_fallo_de_una_seccion_queda_en_el_registro(base, monkeypatch, caplog):
    """El mensaje en pantalla es corto; el traceback completo va al registro de la aplicación."""
    monkeypatch.setattr(op, "render_performance_heatmap", _falla)
    with caplog.at_level("ERROR", logger=op.logger.name):
        _abrir()
    assert any("Performance Heatmap" in r.getMessage() and r.exc_info for r in caplog.records)


def test_operations_st_stop_dentro_de_una_seccion_no_se_trata_como_un_error(base, monkeypatch, caplog):
    """Solo se captura Exception: `st.stop()` usa una excepción de control y debe seguir deteniendo el script. Si se
    capturara, se registraría como un fallo de la sección que no lo es, así que se comprueba el registro."""

    def parar(_db):
        st.stop()

    monkeypatch.setattr(op, "render_route_status_grid", parar)
    with caplog.at_level("ERROR", logger=op.logger.name):
        at = _abrir()
    assert not at.exception and not any("No se pudo mostrar" in e.value for e in at.error)
    assert not [r for r in caplog.records if r.name == op.logger.name]
    assert not any("Refresh the page" in i.value for i in at.info)  # el script se detuvo antes del aviso final
