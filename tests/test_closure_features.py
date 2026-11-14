"""Tests de las variables del estudio de riesgo de cierre (fase 4, protocolo 3.M, «Variables principales»).

Datos sintéticos: cada test fija una regla del protocolo. No leen `data/osm_history/`.
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import closure_features as cf  # noqa: E402
from src.ml import closure_labels as cl  # noqa: E402
from src.poi_client import CATEGORY_TAGS  # noqa: E402

LAT0, LON0 = 35.890, 14.510
M_LAT = 111_320.0
M_LON = 111_320.0 * math.cos(math.radians(LAT0))


def a(norte=0.0, este=0.0):
    """Punto a esa distancia (m) al norte y al este del origen."""
    return LAT0 + norte / M_LAT, LON0 + este / M_LON


def nodo(ident, punto=None, **tags):
    lat, lon = punto or (LAT0, LON0)
    return {"type": "node", "id": ident, "lat": lat, "lon": lon, "tags": tags}


def via(ident, punto=None, **tags):
    lat, lon = punto or (LAT0, LON0)
    return {"type": "way", "id": ident, "center": {"lat": lat, "lon": lon}, "tags": tags}


CAFE = dict(amenity="cafe", name="Café Luna")  # food_drink
ESCUELA = dict(amenity="school", name="Escuela")  # school


def poblacion_de(elementos, *ids):
    """Tabla de población con solo los locales `ids` (tipo node) tomados de `elementos`."""
    tabla, _ = cl.poblacion_2022(elementos)
    return tabla[tabla["id"].isin(ids)].reset_index(drop=True)


def una_fila(elementos, ident, tipo="node"):
    tabla, _ = cl.poblacion_2022(elementos)
    fila = tabla[(tabla["id"] == ident) & (tabla["tipo"] == tipo)].reset_index(drop=True)
    assert len(fila) == 1
    return cf.variables(fila, elementos).iloc[0]


# ---- columnas ---------------------------------------------------------------------------------------------------------------
def test_las_variables_son_exactamente_las_del_protocolo_y_en_este_orden():
    assert cf.COLUMNAS == (
        "cat_school",
        "cat_hospital",
        "cat_food_drink",
        "cat_leisure",
        "cat_sport",
        "cat_mall",
        "cat_business",
        "n_misma_250",
        "n_total_250",
        "n_misma_500",
        "n_total_500",
        "dist_misma_m",
        "cadena",
    )
    assert cf.CATEGORIAS == tuple(CATEGORY_TAGS)  # las siete categorías del recolector


def test_los_parametros_son_los_del_protocolo():
    assert (cf.RADIOS_M, cf.DISTANCIA_MAXIMA_M, cf.MIN_REPETICIONES_CADENA) == ((250.0, 500.0), 1000.0, 3)


def test_no_hay_ninguna_variable_del_estado_actual_ni_externa():
    """El protocolo excluye tiempo de viaje, población por zona y contexto estático actual."""
    prohibidas = ("tiempo", "viaje", "poblacion", "edificio", "alojamiento", "parada", "industria", "hoy", "actual")
    assert not [c for c in cf.COLUMNAS if any(p in c for p in prohibidas)]


# ---- universo ---------------------------------------------------------------------------------------------------------------
def test_el_universo_incluye_elementos_sin_nombre_y_excluye_vacios_sin_categoria_y_sin_posicion():
    elementos = [
        nodo(1, **CAFE),
        nodo(2, amenity="cafe"),  # sin nombre: entra en el universo (cuenta como competencia)
        nodo(3, shop="vacant"),
        nodo(4, amenity="cafe", disused="yes"),
        nodo(5, amenity="bench"),
        {"type": "node", "id": 6, "tags": {"amenity": "cafe"}},
        nodo(7, amenity="cafe", name="Abandonado", abandoned="yes"),
        nodo(8, amenity="cafe", name="Libre", vacant="yes"),
    ]
    u = cf.universo(elementos)
    assert sorted(u["id"]) == [1, 2]
    assert u.set_index("id").loc[2, "nombre_norm"] == ""


def test_el_universo_cuenta_una_vez_los_repetidos_y_distingue_nodo_y_way():
    u = cf.universo([nodo(1, **CAFE), nodo(1, **CAFE), via(1, a(10, 10), **CAFE)])
    assert sorted(zip(u["tipo"], u["id"])) == [("node", 1), ("way", 1)]


def test_un_universo_vacio_da_tabla_vacia_con_columnas():
    u = cf.universo([])
    assert len(u) == 0 and list(u.columns) == ["tipo", "id", "lat", "lon", "categoria", "nombre_norm"]


# ---- categoría --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "tags, categoria", [(CAFE, "food_drink"), (ESCUELA, "school"), (dict(shop="bakery", name="P"), "business")]
)
def test_la_categoria_es_una_columna_por_categoria_y_solo_una(tags, categoria):
    fila = una_fila([nodo(1, **tags)], 1)
    activas = [c for c in cf.COLUMNAS_CATEGORIA if fila[c] == 1.0]
    assert activas == [f"cat_{categoria}"]
    assert fila[list(cf.COLUMNAS_CATEGORIA)].sum() == 1.0


# ---- recuentos a 250 m y 500 m -----------------------------------------------------------------------------------------------
def _entorno():
    """El local 1 (café) en el origen y vecinos a distancias conocidas."""
    return [
        nodo(1, **CAFE),
        nodo(2, a(100, 0), amenity="cafe", name="Cerca igual"),  # 100 m, misma categoría
        nodo(3, a(0, 300), amenity="restaurant", name="Media igual"),  # 300 m, misma categoría
        nodo(4, a(300, 0), **ESCUELA),  # 300 m, otra categoría
        nodo(5, a(600, 0), amenity="bar", name="Lejos igual"),  # 600 m, misma categoría: fuera de 500
        nodo(6, a(0, 200), shop="bakery", name="Panadería"),  # 200 m, otra categoría
    ]


def test_recuentos_de_la_misma_categoria_y_totales_a_250_y_500_m():
    f = una_fila(_entorno(), 1)
    assert (f["n_misma_250"], f["n_total_250"]) == (1.0, 2.0)  # 100 m (misma) y 200 m (otra)
    assert (f["n_misma_500"], f["n_total_500"]) == (2.0, 4.0)  # +300 m misma, +300 m otra; el de 600 m no cuenta


def test_el_propio_local_no_se_cuenta_a_si_mismo():
    f = una_fila([nodo(1, **CAFE)], 1)
    assert (f["n_misma_250"], f["n_total_250"], f["n_misma_500"], f["n_total_500"]) == (0.0, 0.0, 0.0, 0.0)


def test_los_vecinos_sin_nombre_cuentan_y_los_vacios_no():
    elementos = [
        nodo(1, **CAFE),
        nodo(2, a(50, 0), amenity="cafe"),  # sin nombre: cuenta
        nodo(3, a(60, 0), shop="vacant"),  # vacío: no cuenta
        nodo(4, a(70, 0), amenity="cafe", name="Cerrado", disused="yes"),  # vacío: no cuenta
    ]
    f = una_fila(elementos, 1)
    assert (f["n_misma_250"], f["n_total_250"]) == (1.0, 1.0)


@pytest.mark.parametrize("radio, columna", [(250.0, "n_total_250"), (500.0, "n_total_500")])
def test_los_radios_son_inclusivos(monkeypatch, radio, columna):
    elementos = [nodo(1, **CAFE), nodo(2, a(10, 0), **{**CAFE, "name": "Otro"})]
    monkeypatch.setattr(
        cf.grid, "haversine_m", lambda *args: np.full(np.broadcast(*[np.asarray(x) for x in args]).shape, radio)
    )
    assert una_fila(elementos, 1)[columna] == 1.0
    monkeypatch.setattr(
        cf.grid, "haversine_m", lambda *args: np.full(np.broadcast(*[np.asarray(x) for x in args]).shape, radio + 0.01)
    )
    assert una_fila(elementos, 1)[columna] == 0.0


def test_un_vecino_fuera_de_la_poblacion_cuenta_igualmente():
    """El vecino puede estar a < 500 m del borde (no es población de estudio) y aun así es competencia."""
    from src.ml import grid

    junto_al_borde = (grid.SOUTH + 100 / M_LAT, LON0)  # a 100 m del borde: fuera de la población
    elementos = [
        nodo(1, (grid.SOUTH + 550 / M_LAT, LON0), **CAFE),
        nodo(2, junto_al_borde, amenity="cafe", name="Borde"),
    ]
    poblacion, _ = cl.poblacion_2022(elementos)
    assert list(poblacion["id"]) == [1]  # el 2 no es población
    assert cf.variables(poblacion, elementos).iloc[0]["n_total_500"] == 1.0  # pero cuenta como vecino (a unos 450 m)


# ---- distancia al más cercano de la misma categoría ----------------------------------------------------------------------------
def test_la_distancia_es_al_mas_cercano_de_la_misma_categoria_y_no_al_propio():
    f = una_fila(_entorno(), 1)
    assert f["dist_misma_m"] == pytest.approx(100, abs=2)  # el de 100 m; la panadería de 200 m y la escuela no cuentan


def test_la_distancia_tiene_un_maximo_de_1000_m_y_sin_vecinos_de_su_categoria_vale_1000():
    sin_igual = [nodo(1, **CAFE), nodo(2, a(50, 0), **ESCUELA)]
    assert una_fila(sin_igual, 1)["dist_misma_m"] == 1000.0
    lejos = [nodo(1, **CAFE), nodo(2, a(5000, 0), amenity="cafe", name="Lejano")]
    assert una_fila(lejos, 1)["dist_misma_m"] == 1000.0  # existe, pero a más de 1.000 m: se corta
    justo = [nodo(1, **CAFE), nodo(2, a(900, 0), amenity="cafe", name="Cercano")]
    assert una_fila(justo, 1)["dist_misma_m"] == pytest.approx(900, abs=2)


def test_el_mas_cercano_de_la_misma_categoria_incluye_los_sin_nombre():
    f = una_fila([nodo(1, **CAFE), nodo(2, a(80, 0), amenity="cafe")], 1)
    assert f["dist_misma_m"] == pytest.approx(80, abs=2)


# ---- cadena ----------------------------------------------------------------------------------------------------------------
def test_cadena_si_el_nombre_normalizado_se_repite_3_o_mas_veces_incluido_el_propio():
    tres = [
        nodo(i, a(300 * i, 0), amenity="cafe", name=n)
        for i, n in ((1, "Café Luna"), (2, "CAFE LUNA"), (3, "cafe, luna"))
    ]
    assert una_fila(tres, 1)["cadena"] == 1.0
    dos = tres[:2]
    assert una_fila(dos, 1)["cadena"] == 0.0


def test_la_cadena_cuenta_el_universo_entero_no_solo_la_poblacion():
    """El tercer homónimo está a 100 m del borde (no es población) pero figura en la foto de 2022: cuenta."""
    from src.ml import grid

    elementos = [
        nodo(1, a(0, 0), amenity="cafe", name="Cadena"),
        nodo(2, a(1000, 0), amenity="cafe", name="Cadena"),
        nodo(3, (grid.SOUTH + 100 / M_LAT, LON0), amenity="cafe", name="Cadena"),
    ]
    poblacion, _ = cl.poblacion_2022(elementos)
    assert sorted(poblacion["id"]) == [1, 2]
    assert list(cf.variables(poblacion, elementos)["cadena"]) == [1.0, 1.0]


def test_los_elementos_sin_nombre_no_forman_cadena_y_los_vacios_homonimos_no_cuentan():
    sin_nombre = [nodo(1, **CAFE)] + [nodo(i, a(300 * i, 0), amenity="cafe") for i in (2, 3, 4)]
    assert una_fila(sin_nombre, 1)["cadena"] == 0.0
    con_vacios = [
        nodo(1, **CAFE),
        nodo(2, a(300, 0), shop="vacant", name="Café Luna"),
        nodo(3, a(600, 0), amenity="cafe", name="Café Luna", disused="yes"),
    ]
    assert una_fila(con_vacios, 1)["cadena"] == 0.0


# ---- forma de la tabla ----------------------------------------------------------------------------------------------------
def test_la_tabla_conserva_el_orden_de_la_poblacion_y_tiene_las_columnas_exactas():
    elementos = [nodo(i, a(400 * i, 0), amenity="cafe", name=f"N{i}") for i in range(1, 5)]
    poblacion, _ = cl.poblacion_2022(elementos)
    poblacion = poblacion.iloc[::-1].reset_index(drop=True)  # otro orden
    X = cf.variables(poblacion, elementos)
    assert list(X.columns) == list(cf.COLUMNAS) and list(X.index) == list(range(len(poblacion)))
    assert [X.loc[i, "cat_food_drink"] for i in range(4)] == [1.0] * 4
    # el local de más al norte (id 4) es el primero ahora: su vecino más cercano de la misma categoría está a 400 m
    assert poblacion.loc[0, "id"] == 4 and X.loc[0, "dist_misma_m"] == pytest.approx(400, abs=3)
    assert not X.isna().any().any()


def test_un_local_que_no_esta_en_el_universo_es_un_error():
    elementos = [nodo(1, **CAFE)]
    poblacion, _ = cl.poblacion_2022(elementos)
    with pytest.raises(ValueError, match="no están en el universo"):
        cf.variables(poblacion, [nodo(2, **CAFE)])


def test_una_poblacion_vacia_da_una_tabla_vacia():
    vacia = pd.DataFrame({"tipo": [], "id": [], "lat": [], "lon": [], "categoria": [], "nombre_norm": []})
    X = cf.variables(vacia, [nodo(1, **CAFE)])
    assert len(X) == 0 and list(X.columns) == list(cf.COLUMNAS)


def test_solo_se_usa_la_foto_que_se_le_da():
    """Las variables salen únicamente de los elementos del instante de partida: añadir un elemento de «hoy» cambia el resultado
    solo si se le pasa a la función (aquí se comprueba que no hay otra fuente)."""
    antes = [nodo(1, **CAFE)]
    poblacion, _ = cl.poblacion_2022(antes)
    sin = cf.variables(poblacion, antes).iloc[0]["n_total_250"]
    con = cf.variables(poblacion, antes + [nodo(2, a(50, 0), **ESCUELA)]).iloc[0]["n_total_250"]
    assert (sin, con) == (0.0, 1.0)
