"""Tests de las pestañas de Analyst que no cubría test_analyst_quality.py: editor SQL (solo lectura de verdad),
exportación completa, explorador de datos, pruebas estadísticas, correlaciones y base vacía.

(test_analyst_quality.py ya prueba que Analyst abre con UN perfil de la base; test_predictive_modeling_*.py,
el modelado. Aquí el modelado se sustituye por un no-op.)
"""

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("streamlit")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.database import RouteDatabase  # noqa: E402
from streamlit_app.dashboards import analyst_dashboard as ad  # noqa: E402

AHORA = datetime.now(timezone.utc)
APP = f"import sys\nsys.path.insert(0, r'{ROOT}')\nfrom streamlit_app.dashboards import analyst_dashboard as ad\nad.main()\n"


def _fila(i, origin="Msida", destination="Gzira", **extra):
    base = {"timestamp": (AHORA - timedelta(hours=i)).isoformat(), "origin": origin, "destination": destination,
            "data_source": "tomtom", "travel_time_min": 10.0 + (i % 7), "distance_km": 3.0, "average_speed_kmh": 30.0 - (i % 7),
            "traffic_delay_min": 1.0, "origin_temperature": 20.0 + (i % 5), "origin_humidity": 50.0,
            "polyline": "abcdefghij"}
    base.update(extra)
    return base


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    ruta = tmp_path / "t.db"
    db = RouteDatabase(tmp_path / "t.csv", ruta)
    db.save_records_to_sqlite([_fila(i) for i in range(60)] + [_fila(i, "Msida", "Sliema") for i in range(40)])
    st.cache_data.clear()
    monkeypatch.setattr(ad, "get_database", lambda: db)
    monkeypatch.setattr(ad, "ROOT_DIR", tmp_path)                      # el editor SQL lee ROOT_DIR/data/mobility.db
    (tmp_path / "data").mkdir()
    # data/mobility.db = la base temporal (se copia: el editor la abre en solo lectura por esa ruta)
    import shutil
    shutil.copy(ruta, tmp_path / "data" / "mobility.db")
    monkeypatch.setattr(ad.predictive_modeling_dashboard, "render", lambda: None)
    yield db, tmp_path
    st.cache_data.clear()


def _abrir():
    at = AppTest.from_string(APP, default_timeout=120)
    at.run()
    return at


def _sql(at, consulta):
    at.text_area[0].set_value(consulta)
    at.button[[b.label for b in at.button].index("▶ Ejecutar")].click().run()
    return at


# ---------------------------------------------------------------------------
# Editor SQL: solo lectura REAL
# ---------------------------------------------------------------------------

def test_el_editor_sql_ejecuta_selects_y_ofrece_la_descarga(entorno):
    at = _sql(_abrir(), "SELECT destination, COUNT(*) AS n FROM route_measurements GROUP BY destination ORDER BY destination")
    assert not at.exception, [e.value for e in at.exception]
    assert any(s.value == "2 filas" for s in at.success)
    resultado = [d.value for d in at.dataframe if list(d.value.columns) == ["destination", "n"]][0]
    assert resultado["destination"].tolist() == ["Gzira", "Sliema"] and resultado["n"].tolist() == [60, 40]


def test_el_editor_sql_acepta_with_recursivo_y_funciones(entorno):
    r = ad._read_only_query(entorno[1] / "data" / "mobility.db",
                            "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c WHERE x < 3) "
                            "SELECT x, ROUND(x / 2.0, 1) AS m, datetime('now') > '2000' AS ok FROM c")
    assert r["x"].tolist() == [1, 2, 3] and r["m"].tolist() == [0.5, 1.0, 1.5]


@pytest.mark.parametrize("consulta", [
    "INSERT INTO route_measurements (timestamp, origin, destination) VALUES ('x', 'a', 'b')",
    "UPDATE route_measurements SET travel_time_min = 0",
    "DELETE FROM route_measurements",
    "DROP TABLE route_measurements",
    "CREATE TABLE intruso (a)",
    "PRAGMA journal_mode = DELETE",
    "PRAGMA writable_schema = 1",
])
def test_el_editor_sql_rechaza_escrituras_y_pragmas_sin_tocar_los_datos(entorno, consulta):
    _, tmp = entorno
    ruta = tmp / "data" / "mobility.db"
    antes = ruta.read_bytes()
    at = _sql(_abrir(), consulta)
    assert not at.exception and at.error and "Error en la consulta" in at.error[0].value
    assert ruta.read_bytes() == antes                                   # la base no cambió ni un byte


@pytest.mark.parametrize("plantilla", ["ATTACH DATABASE '{p}' AS intruso", "VACUUM INTO '{p}'"])
def test_el_editor_sql_no_crea_archivos_en_disco(entorno, plantilla):
    """Regresión: con solo `mode=ro`, ATTACH y VACUUM INTO se ejecutaban y creaban archivos nuevos (VACUUM INTO
    vuelca una copia completa de la base a cualquier ruta escribible). El authorizer de SQLite los deniega."""
    _, tmp = entorno
    destino = tmp / "fuga.db"
    at = _sql(_abrir(), plantilla.format(p=destino.as_posix()))
    assert not at.exception and at.error
    assert not destino.exists()


def test_el_editor_sql_cierra_la_conexion_aunque_la_consulta_falle(entorno):
    """Si no se cerrara, en Windows el archivo quedaría bloqueado (no se podría borrar/mover)."""
    ruta = entorno[1] / "data" / "mobility.db"
    with pytest.raises(Exception):
        ad._read_only_query(ruta, "SELECT * FROM tabla_que_no_existe")
    ruta.unlink()                                                       # falla en Windows si queda abierta
    assert not ruta.exists()


def test_el_editor_sql_con_consulta_vacia_avisa(entorno):
    at = _sql(_abrir(), "   ")
    assert not at.exception and any("Escribe una consulta" in w.value for w in at.warning)


def test_un_ejemplo_del_editor_rellena_la_consulta(entorno):
    at = _abrir()
    at.selectbox[[s.label for s in at.selectbox].index("Ejemplos")].select("Tablas disponibles").run()
    assert "sqlite_master" in at.text_area[0].value


def test_todos_los_ejemplos_del_editor_se_pueden_ejecutar(entorno):
    """Cada consulta de ejemplo debe ser válida y pasar el authorizer (incluida sqlite_master)."""
    ruta = entorno[1] / "data" / "mobility.db"
    at = _abrir()
    selector = at.selectbox[[s.label for s in at.selectbox].index("Ejemplos")]
    ejemplos = [o for o in selector.options if not o.startswith("—")]
    assert len(ejemplos) >= 5
    for nombre in ejemplos:
        at.selectbox[[s.label for s in at.selectbox].index("Ejemplos")].select(nombre).run()
        consulta = at.text_area[0].value
        try:
            ad._read_only_query(ruta, consulta)
        except Exception as e:                                          # tablas opcionales (Gold/Foursquare) pueden no existir
            assert "no such table" in str(e), f"{nombre}: {e}"


# ---------------------------------------------------------------------------
# Exportación completa
# ---------------------------------------------------------------------------

def _generar(at):
    at.button[[b.label for b in at.button].index("🔄 Generar exportación completa")].click().run()
    return at


def test_la_exportacion_incluye_todas_las_rutas_y_la_polyline_por_defecto(entorno):
    at = _generar(_abrir())
    assert not at.exception, [e.value for e in at.exception]
    assert any("100 filas de 2 rutas" in s.value for s in at.success)


@pytest.mark.parametrize("con_fechas", [False, True])
def test_la_exportacion_ligera_omite_la_polyline(entorno, monkeypatch, con_fechas):
    """La casilla de la polyline debe respetarse tanto en la exportación total como en la limitada por fechas."""
    pedidos = []
    original = RouteDatabase.query_measurements

    def espia(self, *a, **k):
        pedidos.append(k.get("include_polyline"))
        return original(self, *a, **k)

    monkeypatch.setattr(RouteDatabase, "query_measurements", espia)
    at = _abrir()
    if con_fechas:
        at.checkbox[[c.label for c in at.checkbox].index("Limitar por rango de fechas")].set_value(True)
    at.checkbox[[c.label for c in at.checkbox].index("Incluir la columna `polyline` (geometría de la ruta)")].set_value(False)
    _generar(at)
    assert pedidos[-1] is False and not at.exception


def test_la_exportacion_con_rango_de_fechas_filtra(entorno):
    at = _abrir()
    at.checkbox[[c.label for c in at.checkbox].index("Limitar por rango de fechas")].set_value(True)
    at.slider[[s.label for s in at.slider].index("Días de historial a incluir")].set_value(1).run()
    _generar(at)
    assert not at.exception
    exito = [s.value for s in at.success if "filas de" in s.value]
    assert exito and int(exito[0].split()[0].replace(",", "")) < 100          # solo ~24 h de las 60/40 horas


def test_la_exportacion_sin_datos_avisa(entorno):
    db, tmp = entorno
    con = sqlite3.connect(tmp / "t.db")
    con.execute("DELETE FROM route_measurements")
    con.commit()
    con.close()
    st.cache_data.clear()
    at = _generar(_abrir())
    assert not at.exception and any("No hay datos disponibles" in w.value for w in at.warning)


# ---------------------------------------------------------------------------
# Explorador, pruebas estadísticas, correlaciones y base vacía
# ---------------------------------------------------------------------------

def test_el_explorador_muestra_los_datos_de_la_ruta_elegida(entorno):
    at = _abrir()
    assert not at.exception, [e.value for e in at.exception]
    assert any(len(d.value) == 60 for d in at.dataframe)                  # Msida → Gzira: 60 filas


def test_las_pruebas_estadisticas_corren_con_datos_suficientes(entorno):
    at = _abrir()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Stationarity Tests" in m.value for m in at.markdown) and len(at.json) >= 1


def test_las_correlaciones_se_dibujan_con_las_columnas_por_defecto(entorno):
    at = _abrir()
    assert not at.exception
    ms = [m for m in at.multiselect if m.label == "Select columns for correlation"][0]
    assert {"travel_time_min", "average_speed_kmh", "origin_temperature"} <= set(ms.value)


def test_analyst_con_la_base_vacia_no_lanza_excepciones(tmp_path, monkeypatch):
    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    db.init_sqlite()
    st.cache_data.clear()
    monkeypatch.setattr(ad, "get_database", lambda: db)
    monkeypatch.setattr(ad, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(ad.predictive_modeling_dashboard, "render", lambda: None)
    at = _abrir()
    assert not at.exception, [e.value for e in at.exception]
    st.cache_data.clear()


def test_la_pestana_de_modelos_marca_las_rutas_con_modelo_entrenado(entorno):
    _, tmp = entorno
    (tmp / "models").mkdir()
    (tmp / "models" / "Msida_Gzira_ensemble.pkl").write_bytes(b"x")
    at = _abrir()
    assert not at.exception
    tabla = [d.value for d in at.dataframe if "Model Status" in d.value.columns][0].set_index("Route")
    assert tabla.loc["Msida → Gzira", "Model Status"] == "✅ Trained"
    assert tabla.loc["Msida → Sliema", "Model Status"] == "❌ Not Trained"
    assert tabla.loc["Msida → Gzira", "Samples"] == 60
