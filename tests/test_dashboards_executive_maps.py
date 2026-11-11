"""Tests de las pantallas Executive y Maps (Streamlit AppTest) con una base temporal.

Se comprueba que abren sin excepciones con datos y con la base vacía, y que lo que muestran sale de los datos
(tarjetas, deltas, alertas, colores y estados de las rutas, capas de POIs). No se prueba el aspecto visual.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.data_warehouse.bronze_layer import BronzeLayer  # noqa: E402
from src.data_warehouse.gold_layer import GoldLayer  # noqa: E402
from src.data_warehouse.silver_layer import SilverLayer  # noqa: E402
from src.database import RouteDatabase  # noqa: E402
from src.locations import ROUTES  # noqa: E402
from streamlit_app.dashboards import executive_dashboard as ex  # noqa: E402
from streamlit_app.dashboards import maps_dashboard as mp  # noqa: E402

AHORA = datetime.now(timezone.utc)
APP_EXEC = f"import sys\nsys.path.insert(0, r'{ROOT}')\nfrom streamlit_app.dashboards import executive_dashboard as m\nm.main()\n"
APP_MAPS = f"import sys\nsys.path.insert(0, r'{ROOT}')\nfrom streamlit_app.dashboards import maps_dashboard as m\nm.main()\n"
COLS_BRONZE = ["timestamp", "origin", "destination", "travel_time_min", "no_traffic_time_min", "average_speed_kmh",
               "origin_temperature", "origin_humidity", "origin_weather", "destination_temperature",
               "destination_humidity", "destination_weather"]


def _registro(momento, origen, destino, minutos=12.0, retraso=1.0):
    return {"timestamp": momento.isoformat(), "origin": origen, "destination": destino, "data_source": "tomtom",
            "travel_time_min": minutos, "no_traffic_time_min": minutos - retraso, "traffic_delay_min": retraso,
            "average_speed_kmh": 30.0, "distance_km": 4.0, "origin_temperature": 21.0, "origin_humidity": 55.0,
            "origin_weather": "claro", "destination_temperature": 21.0, "destination_humidity": 55.0,
            "destination_weather": "claro", "mobility_level": "Movilidad normal"}


def _poblar(db_path, dias_atras, rutas=(("Msida", "Gzira"), ("Msida", "Sliema")), minutos=12.0, n=8):
    """Guarda n mediciones por ruta en cada día indicado (días atrás) y construye Bronze→Silver→Gold de ese día."""
    db = RouteDatabase(db_path.parent / "t.csv", db_path)
    for d in dias_atras:
        base = (AHORA - timedelta(days=d)).replace(hour=9, minute=0, second=0, microsecond=0)
        registros = [_registro(base + timedelta(minutes=10 * i), o, de, minutos + (i % 3), 1.0 + (i % 2))
                     for o, de in rutas for i in range(n)]
        db.save_records_to_sqlite(registros)
        bronze = pd.DataFrame(registros)[COLS_BRONZE]
        BronzeLayer(db_path).ingest(bronze)
        import sqlite3
        con = sqlite3.connect(db_path)
        sb = pd.read_sql_query("SELECT * FROM bronze_measurements", con)
        con.close()
        SilverLayer(db_path).transform_bronze(sb)
        dia = base.date().isoformat()
        GoldLayer(db_path).calculate_kpis(date=dia)
        GoldLayer(db_path).calculate_rankings(date=dia)
    return db


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Base temporal; las pantallas la usan en vez de data/mobility.db. Devuelve (db, ruta)."""
    ruta = tmp_path / "m.db"
    db = RouteDatabase(tmp_path / "t.csv", ruta)
    db.init_sqlite()
    st.cache_data.clear()
    for modulo in (ex, mp):
        monkeypatch.setattr(modulo, "get_database", lambda: db)
    monkeypatch.setattr(ex, "get_gold_layer", lambda: GoldLayer(ruta))
    yield db, ruta
    st.cache_data.clear()


def _abrir(app):
    at = AppTest.from_string(app, default_timeout=120)
    at.run()
    return at


def _metricas(at):
    return {m.label: m for m in at.metric}


# ---------------------------------------------------------------------------
# Executive
# ---------------------------------------------------------------------------

def test_executive_abre_con_datos_y_muestra_las_tarjetas(base):
    _, ruta = base
    _poblar(ruta, dias_atras=[0, 1, 2])
    at = _abrir(APP_EXEC)
    assert not at.exception, [e.value for e in at.exception]
    m = _metricas(at)
    assert set(m) == {"System Avg Travel Time", "System Reliability", "Active Routes", "Total Measurements"}
    assert m["Active Routes"].value == "2"
    assert m["Total Measurements"].value == f"{3 * 2 * 8:,}"                  # 3 días x 2 rutas x 8 mediciones
    assert m["System Avg Travel Time"].value.endswith(" min") and 10 < float(m["System Avg Travel Time"].value.split()[0]) < 15


def test_executive_tablas_de_mejores_y_peores_rutas(base):
    _, ruta = base
    _poblar(ruta, [0, 1], rutas=(("Msida", "Gzira"),), minutos=8.0)
    _poblar(ruta, [0, 1], rutas=(("Msida", "Sliema"),), minutos=25.0)
    at = _abrir(APP_EXEC)
    assert not at.exception, [e.value for e in at.exception]
    mejores, peores = at.dataframe[0].value, at.dataframe[1].value
    assert set(mejores.columns) == {"route", "avg_time", "avg_reliability"}
    assert len(mejores) == 2 and len(peores) == 2                    # hay 2 rutas: se muestran todas (hasta 5)
    assert "Msida → Gzira" in mejores["route"].tolist()
    assert "Msida → Sliema" in peores["route"].tolist()


def test_executive_sin_periodo_anterior_no_inventa_deltas(base):
    _, ruta = base
    _poblar(ruta, [0, 1, 2])                                   # solo periodo actual
    m = _metricas(_abrir(APP_EXEC))
    assert m["System Avg Travel Time"].delta in (None, "") and m["System Reliability"].delta in (None, "")


def test_executive_con_periodo_anterior_calcula_el_delta_con_los_datos(base):
    _, ruta = base
    _poblar(ruta, [0, 1], minutos=20.0)                        # periodo actual: más lento
    _poblar(ruta, [31, 32], minutos=10.0)                      # periodo anterior (días 30-59)
    m = _metricas(_abrir(APP_EXEC))
    delta = m["System Avg Travel Time"].delta
    assert "vs. periodo anterior" in delta and "min" in delta
    assert float(delta.split()[0]) == pytest.approx(10.0, abs=1.0)           # ~ +10 min
    # Menos tiempo de viaje es mejor: un AUMENTO de tiempo se pinta en ROJO (delta_color="inverse").
    from streamlit.proto.Metric_pb2 import Metric
    assert m["System Avg Travel Time"].proto.color == Metric.MetricColor.RED


@pytest.mark.parametrize("actual, anterior, formato, esperado", [
    (12.0, 10.0, "{:+.1f} min", "+2.0 min"), (8.0, 10.0, "{:+.1f} min", "-2.0 min"),
    (None, 10.0, "{:+.1f}", None), (10.0, None, "{:+.1f}", None), (5.0, 5.0, "{:+.1f}", "+0.0")])
def test_delta(actual, anterior, formato, esperado):
    assert ex._delta(actual, anterior, formato) == esperado


def _resumen(**cambios):
    resumen = {"system_avg_travel_time": 12.0, "system_reliability": 90.0, "total_routes": 2, "total_measurements": 100,
               "best_routes": [], "worst_routes": []}
    resumen.update(cambios)
    return resumen


@pytest.mark.parametrize("cambios, esperados, ausentes", [
    ({}, ["All systems operating normally"], ["High average", "Low system"]),
    ({"system_avg_travel_time": 31.0}, ["High average travel time"], ["All systems"]),
    ({"system_avg_travel_time": 30.0}, ["All systems operating normally"], ["High average"]),       # 30 exacto: sin alerta
    ({"system_reliability": 49.9}, ["Low system reliability"], ["All systems"]),
    ({"system_reliability": 50.0}, ["All systems operating normally"], ["Low system"]),             # 50 exacto: sin alerta
    ({"system_avg_travel_time": 40.0, "system_reliability": 10.0}, ["High average", "Low system"], ["All systems"]),
])
def test_executive_alertas_segun_los_umbrales(base, monkeypatch, cambios, esperados, ausentes):
    monkeypatch.setattr(ex, "_fetch_executive_summary", lambda gold, days: _resumen(**cambios))
    at = _abrir(APP_EXEC)
    assert not at.exception, [e.value for e in at.exception]
    textos = " | ".join([w.value for w in at.warning] + [s.value for s in at.success])
    assert all(e in textos for e in esperados) and not any(a in textos for a in ausentes)


def test_executive_si_el_resumen_falla_muestra_el_error_y_no_sigue(base, monkeypatch):
    monkeypatch.setattr(ex, "_fetch_executive_summary", lambda gold, days: {"error": "tabla inexistente"})
    at = _abrir(APP_EXEC)
    assert not at.exception and [e.value for e in at.error] == ["Error loading summary data"]
    assert not at.metric                                         # se detiene antes de las tarjetas


def test_executive_con_la_base_vacia_no_lanza_excepciones(base):
    at = _abrir(APP_EXEC)
    assert not at.exception, [e.value for e in at.exception]


def test_executive_con_la_base_vacia_no_muestra_un_0_por_ciento_ni_una_alerta_falsa(base):
    """Sin mediciones la fiabilidad no es 0 %: es desconocida. Antes salía «0.0%» y la alerta «Low system reliability»."""
    at = _abrir(APP_EXEC)
    assert not at.exception, [e.value for e in at.exception]
    m = _metricas(at)
    assert m["System Avg Travel Time"].value == "—" and m["System Reliability"].value == "—"
    assert m["Total Measurements"].value == "0" and m["Active Routes"].value == "0"
    avisos = " | ".join(w.value for w in at.warning)                  # los gráficos avisan aparte de que no hay datos
    assert "Low system reliability" not in avisos and "High average" not in avisos and not at.success
    assert any("no se evalúan alertas" in i.value for i in at.info)


def test_executive_con_datos_sigue_mostrando_las_cifras_y_las_alertas(base):
    """El aviso de «sin mediciones» no aparece cuando sí las hay."""
    _, ruta = base
    _poblar(ruta, dias_atras=[0, 1])
    at = _abrir(APP_EXEC)
    m = _metricas(at)
    assert m["System Reliability"].value.endswith("%") and m["System Avg Travel Time"].value.endswith(" min")
    assert not any("no se evalúan alertas" in i.value for i in at.info)
    assert at.success or at.warning


@pytest.mark.parametrize("resumen, esperado", [({}, False), ({"total_measurements": 0}, False),
                                               ({"total_measurements": 1}, True)])
def test_hay_datos_solo_si_el_resumen_tiene_mediciones(resumen, esperado):
    assert ex._hay_datos(resumen) is esperado


# ---------------------------------------------------------------------------
# Maps
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("retraso, color", [(None, "#95a5a6"), (float("nan"), "#95a5a6"), (0.0, "#2ecc71"),
                                            (1.0, "#2ecc71"), (1.01, "#f1c40f"), (4.0, "#f1c40f"), (4.01, "#e74c3c")])
def test_color_segun_el_retraso(retraso, color):
    assert mp._delay_color(retraso) == color


def test_el_mapa_dibuja_una_traza_por_ruta_mas_las_ubicaciones_y_colorea_por_retraso(base):
    db, _ = base
    ahora = datetime.now(timezone.utc)
    db.save_records_to_sqlite([_registro(ahora - timedelta(minutes=5), "Msida", "Gzira", 10.0, 0.5),
                               _registro(ahora - timedelta(minutes=5), "Msida", "Sliema", 20.0, 6.0)])
    fig = mp.render_route_map(db, [("Msida", "Gzira"), ("Msida", "Sliema"), ("Valletta", "Sliema")])
    rutas = [t for t in fig.data if t.mode == "lines"]
    assert len(rutas) == 3 and fig.data[-1].mode == "markers+text"
    colores = {t.name: t.line.color for t in rutas}
    assert colores["Msida → Gzira"] == "#2ecc71" and colores["Msida → Sliema"] == "#e74c3c"
    assert colores["Valletta → Sliema"] == "#95a5a6"                           # sin datos en la última hora


def test_el_mapa_ignora_rutas_con_ubicaciones_desconocidas(base):
    db, _ = base
    fig = mp.render_route_map(db, [("Msida", "Gzira"), ("Atlantis", "Gzira")])
    assert len([t for t in fig.data if t.mode == "lines"]) == 1


def test_maps_abre_con_datos_y_la_tabla_de_estado_cubre_todas_las_rutas(base):
    db, _ = base
    ahora = datetime.now(timezone.utc)
    db.save_records_to_sqlite([
        _registro(ahora - timedelta(minutes=5), "Msida", "Gzira", 10.0, 0.5),           # flujo libre
        _registro(ahora - timedelta(minutes=5), "Msida", "Sliema", 14.0, 3.0),          # moderado
        _registro(ahora - timedelta(minutes=5), "Valletta", "Sliema", 25.0, 7.0)])      # denso
    at = _abrir(APP_MAPS)
    assert not at.exception, [e.value for e in at.exception]
    tabla = at.dataframe[0].value.set_index("Ruta")
    assert len(tabla) == len(ROUTES)
    assert tabla.loc["Msida → Gzira", "Estado"] == "🟢 Flujo libre"
    assert tabla.loc["Msida → Sliema", "Estado"] == "🟡 Moderado"
    assert tabla.loc["Valletta → Sliema", "Estado"] == "🔴 Denso"
    assert (tabla["Estado"] == "⚪ Sin dato").sum() == len(ROUTES) - 3
    assert tabla.loc["Msida → Gzira", "Tiempo de viaje (1h)"] == "10.0 min"


def test_los_limites_de_los_estados_de_la_tabla_son_1_y_4_minutos_de_retraso(base):
    """<=1 libre, <=4 moderado, >4 denso (los mismos umbrales que el color del mapa)."""
    db, _ = base
    ahora = datetime.now(timezone.utc)
    db.save_records_to_sqlite([
        _registro(ahora - timedelta(minutes=5), "Msida", "Gzira", 10.0, 1.0),
        _registro(ahora - timedelta(minutes=5), "Msida", "Sliema", 10.0, 4.0),
        _registro(ahora - timedelta(minutes=5), "Valletta", "Sliema", 10.0, 4.5)])
    tabla = _abrir(APP_MAPS).dataframe[0].value.set_index("Ruta")["Estado"]
    assert tabla["Msida → Gzira"] == "🟢 Flujo libre"
    assert tabla["Msida → Sliema"] == "🟡 Moderado"
    assert tabla["Valletta → Sliema"] == "🔴 Denso"


def test_maps_con_la_base_vacia_marca_todas_las_rutas_sin_dato(base):
    at = _abrir(APP_MAPS)
    assert not at.exception, [e.value for e in at.exception]
    assert (at.dataframe[0].value["Estado"] == "⚪ Sin dato").all()


def test_maps_sin_rutas_seleccionadas_avisa(base):
    at = _abrir(APP_MAPS)
    at.multiselect[0].set_value([]).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("al menos una ruta" in i.value for i in at.info)


def _poi_overpass(i, categoria="school"):
    return {"osm_type": "node", "osm_id": i, "category": categoria, "subcategory": "x", "name": f"POI {i}",
            "latitude": 35.9, "longitude": 14.5}


def test_maps_sin_pois_explica_como_cargarlos(base):
    at = _abrir(APP_MAPS)
    at.radio[0].set_value("Overpass (OSM)").run()
    assert any("poi_extraction" in i.value for i in at.info)
    at.radio[0].set_value("Foursquare").run()
    assert any("FOURSQUARE_API_KEY" in i.value for i in at.info)


def test_maps_con_pois_de_overpass_dibuja_la_capa_y_cuenta_los_elementos(base):
    db, _ = base
    db.save_pois([_poi_overpass(1), _poi_overpass(2), _poi_overpass(3, "hospital")])
    at = _abrir(APP_MAPS)
    at.radio[0].set_value("Overpass (OSM)").run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("3 elementos de Overpass" in c.value for c in at.caption)


def test_las_categorias_de_overpass_por_defecto_excluyen_las_masivas(base):
    at = _abrir(APP_MAPS)
    at.radio[0].set_value("Overpass (OSM)").run()
    seleccion = at.multiselect[1].value
    assert set(seleccion) == set(mp.OVERPASS_DEFAULT_CATEGORIES)
    assert not {"food_drink", "leisure", "sport"} & set(seleccion)


def test_la_capa_de_pois_usa_la_fuente_indicada_y_no_mezcla_las_dos(base):
    """school/mall existen en los dos catálogos: elegir una fuente no debe dibujar los de la otra."""
    db, _ = base
    db.save_pois([_poi_overpass(1, "school")])
    db.save_pois_foursquare([{"fsq_place_id": "f1", "category": "school", "subcategory": "x", "name": "FSQ 1",
                              "latitude": 35.9, "longitude": 14.5}])
    import plotly.graph_objects as go
    fig_o, fig_f = go.Figure(), go.Figure()
    mp.render_poi_layer(fig_o, db, ["school"], "overpass")
    mp.render_poi_layer(fig_f, db, ["school"], "foursquare")
    assert list(fig_o.data[0].text) == ["POI 1"] and list(fig_f.data[0].text) == ["FSQ 1"]


def test_la_capa_de_pois_no_hace_nada_sin_categorias_o_con_fuente_invalida(base):
    db, _ = base
    import plotly.graph_objects as go
    fig = go.Figure()
    mp.render_poi_layer(fig, db, [], "overpass")
    mp.render_poi_layer(fig, db, ["school"], "otra")
    assert len(fig.data) == 0
