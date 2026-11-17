"""Pruebas de la tabla de resultados del dashboard de Recomendación.

El README promete que el desglose muestra cada dimensión CRUDA y NORMALIZADA
("nunca solo el número final"). Esto lo verifica sin abrir Streamlit.
"""

import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import RouteDatabase
from src.location_scoring import POR_CLAVE, criterios_disponibles, filter_zones, pesos_por_defecto, recommend_locations
from src.locations import LOCATIONS
from streamlit_app.dashboards.recommendation_dashboard import (
    build_contributions_table,
    build_results_table,
    build_summary,
    normalize_weights,
)


def _medicion(ts, origin, destination, minutos):
    return {
        "timestamp": ts.isoformat(),
        "origin": origin,
        "destination": destination,
        "data_source": "tomtom",
        "travel_time_min": minutos,
        "distance_km": 3.0,
    }


@pytest.fixture
def out(tmp_path):
    db = RouteDatabase(tmp_path / "t.csv", tmp_path / "t.db")
    ahora = datetime.now(timezone.utc)
    db.save_records_to_sqlite(
        [
            _medicion(ahora, "Msida", "Gzira", 10.0),
            _medicion(ahora, "Msida", "Sliema", 20.0),
            _medicion(ahora, "Valletta", "Birkirkara", 15.0),
        ]
    )
    # Una zona (Marsaskala) sin demografía, para ver cómo queda un dato faltante.
    db.save_demographics(
        [{"zone_name": z, "population": 1000 * (i + 1)} for i, z in enumerate(LOCATIONS) if z != "Marsaskala"]
    )
    loc = LOCATIONS["Sliema"]
    db.save_pois(
        [
            {
                "osm_type": "node",
                "osm_id": i,
                "category": "business",
                "subcategory": "x",
                "name": f"p{i}",
                "latitude": loc.latitude + 0.0001 * i,
                "longitude": loc.longitude,
            }
            for i in range(1, 6)
        ]
    )
    return recommend_locations(db, "una tienda de ropa")


@pytest.fixture
def criterios(out):
    """Los criterios que esta tabla puntuó: los tres de la base (sin las lentes del panorama, que no se le pasaron)."""
    return criterios_disponibles(out)


def test_la_tabla_muestra_cada_factor_crudo_y_normalizado(out, criterios):
    """La tabla de resultados trae, por cada factor medido directamente, el crudo y el normalizado, una fila por zona."""
    tabla = build_results_table(out, criterios)
    for columna in (
        "Zona",
        "Puntaje",
        "Población",
        "Población (0-1)",
        "Competencia (conteo real)",
        "Competencia (ajustada)",
        "Baja competencia (0-1)",
        "Tiempo de viaje prom. (min)",
        "Accesibilidad (0-1)",
        "Datos completos (de 3)",
    ):
        assert columna in tabla.columns, f"Falta la columna {columna!r}"
    assert len(tabla) == len(LOCATIONS)


def test_las_columnas_normalizadas_estan_entre_0_y_1(out, criterios):
    """Las columnas normalizadas quedan entre 0 y 1."""
    tabla = build_results_table(out, criterios)
    for columna in [c for c in tabla.columns if c.endswith("(0-1)")]:
        valores = tabla[columna].dropna()
        assert valores.between(0, 1).all(), columna


def test_mas_alto_siempre_es_mejor_en_las_columnas_normalizadas(out, criterios):
    """La zona con más competencia tiene el menor 'Baja competencia'."""
    tabla = build_results_table(out, criterios).set_index("Zona")
    mas_competida = tabla["Competencia (conteo real)"].idxmax()
    assert tabla.loc[mas_competida, "Baja competencia (0-1)"] == tabla["Baja competencia (0-1)"].min()
    # y la más poblada, el mayor 'Población (0-1)'
    mas_poblada = tabla["Población"].idxmax()
    assert tabla.loc[mas_poblada, "Población (0-1)"] == 1.0


def test_el_puntaje_es_la_suma_ponderada_de_las_columnas_mostradas(out, criterios):
    """Lo que dice el pie de la tabla: Puntaje = suma ponderada de las columnas (0-1), con 0,5 donde falta el dato."""
    pesos = pesos_por_defecto(criterios)
    tabla = build_results_table(out, criterios).set_index("Zona")
    for zona, fila in tabla.iterrows():
        esperado = sum(
            peso
            * (0.5 if math.isnan(fila[f"{POR_CLAVE[clave].corta} (0-1)"]) else fila[f"{POR_CLAVE[clave].corta} (0-1)"])
            for clave, peso in pesos.items()
        )
        assert fila["Puntaje"] == pytest.approx(esperado), zona


def test_una_zona_sin_dato_queda_en_blanco_y_se_nota(out, criterios):
    """Una zona sin dato queda en blanco (NaN) en vez de en 0 y su recuento de datos completos baja."""
    tabla = build_results_table(out, criterios).set_index("Zona")
    assert math.isnan(tabla.loc["Marsaskala", "Población"])
    assert math.isnan(tabla.loc["Marsaskala", "Población (0-1)"])  # blanco -> "sin dato" en pantalla
    assert tabla.loc["Marsaskala", "Datos completos (de 3)"] < 3


def test_normalize_weights_conserva_proporciones_y_suma_uno(criterios):
    """Los pesos normalizados conservan las proporciones y suman 1; con todo en cero se vuelve a los de fábrica sin
    dividir entre cero."""
    w = normalize_weights({"demanda": 40, "competencia": 35, "accesibilidad": 25}, criterios)
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["demanda"] == pytest.approx(0.40)
    assert w["competencia"] == pytest.approx(0.35)
    cero = normalize_weights({c.clave: 0 for c in criterios}, criterios)
    assert sum(cero.values()) == pytest.approx(1.0)
    assert cero == pesos_por_defecto(criterios)


def test_la_tabla_solo_trae_los_factores_que_se_puntuaron(out, criterios):
    """Sin las lentes del panorama, sus columnas no aparecen: enseñarlas vacías haría creer que se tuvieron en cuenta."""
    tabla = build_results_table(out, criterios)
    assert not [c for c in tabla.columns if "Mercado" in c or "Proveedores" in c or "Diversidad" in c]
    assert "Datos completos (de 3)" in tabla.columns


# ---- desglose de aportación -------------------------------------------------------------------------------------
def test_el_desglose_dice_cuanto_puso_cada_factor_y_suma_el_puntaje(out, criterios):
    """Con varios pesos el número final solo es creíble si se puede abrir: cada columna es peso × normalizado."""
    tabla = build_contributions_table(out, criterios).set_index("Zona")
    assert list(tabla.columns) == ["Puntaje"] + [c.etiqueta for c in criterios]
    aportes = tabla[[c.etiqueta for c in criterios]]
    assert aportes.sum(axis=1).round(9).equals(tabla["Puntaje"].round(9))
    assert (aportes >= 0).all().all()


# ---- filtro de zonas ---------------------------------------------------------------------------------------------
def test_filtrar_zonas_quita_filas_pero_no_cambia_los_puntajes(out):
    """La decisión del autor: el filtro no toca el puntaje, que sigue midiendo la posición entre las 7."""
    elegidas = ["Sliema", "Gzira"]
    filtrado = filter_zones(out, elegidas)
    assert set(filtrado.index) == set(elegidas)
    for zona in elegidas:
        assert filtrado.loc[zona, "score"] == out.loc[zona, "score"]
    assert filtrado["score"].is_monotonic_decreasing


def test_filtrar_sin_zonas_o_con_desconocidas_no_rompe(out):
    """Sin filtro se devuelve todo; una zona que no existe simplemente no aparece."""
    assert filter_zones(out, None).equals(out)
    assert filter_zones(out, []).equals(out)
    assert list(filter_zones(out, ["Atlantis"]).index) == []
    assert list(filter_zones(out, ["Sliema", "Atlantis"]).index) == ["Sliema"]


def test_si_el_filtro_deja_la_tabla_vacia_no_se_lee_la_primera_fila(out):
    """QA de Codex: `out.index[0]` sobre una tabla vacía reventaría la pantalla. Hoy no se alcanza desde la interfaz,
    pero la función que filtra sí puede devolver vacío y quien la use debe poder comprobarlo."""
    vacio = filter_zones(out, ["Atlantis"])
    assert vacio.empty and list(vacio.index) == []


# ---- resumen final -----------------------------------------------------------------------------------------------
def test_el_resumen_dice_la_zona_su_puntaje_y_que_la_hizo_ganar(out, criterios):
    """El cierre de la pantalla: qué zona ganó y QUÉ la hizo ganar, ordenado por lo que aportó cada factor."""
    zona = out.index[0]
    r = build_summary(out, criterios, zona=zona)
    assert r["zona"] == zona and r["posicion"] == 1 and r["zonas"] == len(LOCATIONS)
    assert r["puntaje"] == pytest.approx(out.loc[zona, "score"])
    aportes = [f["aporte"] for f in r["factores"]]
    assert aportes == sorted(aportes, reverse=True)
    assert sum(aportes) == pytest.approx(r["puntaje"])  # el resumen no se deja nada fuera
    for f in r["factores"]:
        assert f["parte"] == pytest.approx(f["aporte"] / r["puntaje"])


def test_el_resumen_marca_los_factores_sin_dato_de_esa_zona(out, criterios):
    """Un factor sin dato entra como neutral (0,5 × su peso): aporta sin ser mérito, y el resumen debe poder decirlo."""
    r = build_summary(out, criterios, zona="Marsaskala")  # la zona que el fixture dejó sin demografía
    poblacion = next(f for f in r["factores"] if f["etiqueta"] == "Población")
    assert poblacion["sin_dato"] is True
    assert not any(f["sin_dato"] for f in r["factores"] if f["etiqueta"] == "Baja competencia")


def test_el_resumen_sin_zona_o_con_una_desconocida_no_falla(out, criterios):
    for zona in (None, "Atlantis"):
        r = build_summary(out, criterios, zona=zona)
        assert r["zona"] is None and r["factores"] == [] and r["celdas"] is None


def test_el_resumen_sin_panorama_no_nombra_celdas(out, criterios):
    """Sin data/ml no hay celdas que concretar, pero la parte de zona sigue entera."""
    r = build_summary(out, criterios, panorama=None, zona=out.index[0])
    assert r["celdas"] is None and r["factores"]
