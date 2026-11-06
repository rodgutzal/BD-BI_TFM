"""Pruebas de la tabla de resultados del dashboard de Recomendación.

El README promete que el desglose muestra cada dimensión CRUDA y NORMALIZADA
("nunca solo el número final"). Esto lo verifica sin abrir Streamlit.
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import RouteDatabase
from src.location_scoring import recommend_locations
from src.locations import LOCATIONS
from streamlit_app.dashboards.recommendation_dashboard import build_results_table, normalize_weights


@pytest.fixture
def out(tmp_path):
    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    # Una zona (Marsaskala) sin demografía, para ver cómo queda un dato faltante.
    db.save_demographics([
        {"zone_name": z, "population": 1000 * (i + 1)}
        for i, z in enumerate(LOCATIONS) if z != "Marsaskala"
    ])
    loc = LOCATIONS["Sliema"]
    db.save_pois([
        {"osm_type": "node", "osm_id": i, "category": "business", "subcategory": "x", "name": f"p{i}",
         "latitude": loc.latitude + 0.0001 * i, "longitude": loc.longitude}
        for i in range(1, 6)
    ])
    return recommend_locations(db, "una tienda de ropa")


def test_la_tabla_muestra_cada_factor_crudo_y_normalizado(out):
    tabla = build_results_table(out)
    for columna in (
        "Zona", "Puntaje",
        "Población", "Demanda (0-1)",
        "Competencia (conteo real)", "Competencia (ajustada)", "Baja competencia (0-1)",
        "Tiempo de viaje prom. (min)", "Accesibilidad (0-1)",
        "Datos completos (de 3)",
    ):
        assert columna in tabla.columns, f"Falta la columna {columna!r}"
    assert len(tabla) == len(LOCATIONS)


def test_las_columnas_normalizadas_estan_entre_0_y_1(out):
    tabla = build_results_table(out)
    for columna in ("Demanda (0-1)", "Baja competencia (0-1)", "Accesibilidad (0-1)"):
        valores = tabla[columna].dropna()
        assert valores.between(0, 1).all(), columna


def test_mas_alto_siempre_es_mejor_en_las_tres_columnas(out):
    """La zona con más competencia tiene el menor 'Baja competencia'."""
    tabla = build_results_table(out).set_index("Zona")
    mas_competida = tabla["Competencia (conteo real)"].idxmax()
    assert tabla.loc[mas_competida, "Baja competencia (0-1)"] == tabla["Baja competencia (0-1)"].min()
    # y la más poblada, el mayor 'Demanda'
    mas_poblada = tabla["Población"].idxmax()
    assert tabla.loc[mas_poblada, "Demanda (0-1)"] == 1.0


def test_el_puntaje_es_la_suma_ponderada_de_las_columnas_mostradas(out):
    """Lo que dice el pie de la tabla: Puntaje = suma ponderada de las tres
    columnas (0-1), con 0.5 donde falta el dato."""
    pesos = {"demanda": 0.40, "competencia": 0.35, "accesibilidad": 0.25}   # los de por defecto
    tabla = build_results_table(out)
    for _, fila in tabla.iterrows():
        esperado = (
            pesos["demanda"] * (0.5 if math.isnan(fila["Demanda (0-1)"]) else fila["Demanda (0-1)"])
            + pesos["competencia"] * (0.5 if math.isnan(fila["Baja competencia (0-1)"]) else fila["Baja competencia (0-1)"])
            + pesos["accesibilidad"] * (0.5 if math.isnan(fila["Accesibilidad (0-1)"]) else fila["Accesibilidad (0-1)"])
        )
        assert fila["Puntaje"] == pytest.approx(esperado), fila["Zona"]


def test_una_zona_sin_dato_queda_en_blanco_y_se_nota(out):
    tabla = build_results_table(out).set_index("Zona")
    assert math.isnan(tabla.loc["Marsaskala", "Población"])
    assert math.isnan(tabla.loc["Marsaskala", "Demanda (0-1)"])      # blanco -> "sin dato" en pantalla
    assert tabla.loc["Marsaskala", "Datos completos (de 3)"] < 3


def test_normalize_weights_conserva_proporciones_y_suma_uno():
    w = normalize_weights(40, 35, 25)
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["demanda"] == pytest.approx(0.40)
    # todo en cero -> pesos por defecto, sin dividir entre cero
    assert sum(normalize_weights(0, 0, 0).values()) == pytest.approx(1.0)
