"""Tests de la rejilla de ~250 m (src/ml/grid.py) y de los conteos por celda (src/ml/cell_counts.py)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import grid  # noqa: E402
from src.ml.cell_counts import CellCounts, Selector, selector, selector_except  # noqa: E402


def pois_en(*celdas):
    """DataFrame de POIs situados en el centro de cada celda: (fila, col, categoria, subcategoria)."""
    filas = []
    for fila, col, cat, sub in celdas:
        lat, lon = grid.cell_center(fila, col)
        filas.append({"category": cat, "subcategory": sub, "latitude": float(lat), "longitude": float(lon)})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Geometría de la rejilla
# ---------------------------------------------------------------------------

def test_la_rejilla_es_fija_y_cubre_el_area():
    assert grid.SHAPE == (45, 51)
    assert grid.N_ROWS * grid.N_COLS == 2295
    # cubre los POIs conocidos (lat 35,847-35,932; lon 14,446-14,572) y los centros de las 7 zonas
    assert grid.SOUTH < 35.847 and grid.NORTH > 35.932 and grid.WEST < 14.446 and grid.EAST > 14.572


def test_las_celdas_miden_unos_250_m_en_las_dos_direcciones():
    lat0, lon0 = grid.cell_center(20, 20)
    lat1, _ = grid.cell_center(21, 20)
    _, lon1 = grid.cell_center(20, 21)
    assert grid.haversine_m(lat0, lon0, lat1, lon0) == pytest.approx(250, abs=3)
    assert grid.haversine_m(lat0, lon0, lat0, lon1) == pytest.approx(250, abs=3)


def test_un_punto_cae_en_la_celda_cuyo_centro_esta_cerca():
    fila, col = grid.cell_index(35.8970, 14.4890)             # Msida
    assert (fila[0], col[0]) == (25, 17)
    lat, lon = grid.cell_center(fila[0], col[0])
    assert grid.haversine_m(35.8970, 14.4890, lat, lon) < 250 * 0.71 + 1      # a lo sumo media diagonal


def test_puntos_fuera_de_la_rejilla_o_sin_coordenadas_dan_menos_uno():
    fila, col = grid.cell_index([35.0, 36.5, np.nan, 35.9, None], [14.5, 14.5, 14.5, np.nan, 14.5])
    assert fila.tolist() == [-1, -1, -1, -1, -1] and col.tolist() == [-1, -1, -1, -1, -1]


def test_los_bordes_de_la_rejilla():
    assert grid.cell_index(grid.SOUTH, grid.WEST) == (np.array([0]), np.array([0]))          # esquina suroeste incluida
    fila, _ = grid.cell_index(grid.SOUTH - 1e-6, grid.WEST)
    assert fila[0] == -1
    fila, col = grid.cell_index(grid.SOUTH + grid.N_ROWS * grid.DLAT + 1e-6, grid.WEST + grid.N_COLS * grid.DLON + 1e-6)
    assert fila[0] == -1 and col[0] == -1


def test_identificadores_de_celda():
    assert grid.cell_id(23, 20) == "r23c20" and grid.cell_id(3, 7) == "r03c07"
    assert grid.parse_cell_id("r23c20") == (23, 20)
    for malo in ("x23c20", "r23", "celda"):
        with pytest.raises(ValueError):
            grid.parse_cell_id(malo)


def test_cells_frame_tiene_todas_las_celdas_y_cada_centro_cae_en_su_celda():
    celdas = grid.cells_frame()
    assert len(celdas) == 2295 and celdas["cell_id"].is_unique
    fila, col = grid.cell_index(celdas["lat"].to_numpy(), celdas["lon"].to_numpy())
    assert (fila == celdas["fila"].to_numpy()).all() and (col == celdas["col"].to_numpy()).all()


def test_count_grid_cuenta_por_celda_e_ignora_lo_de_fuera():
    contador = grid.count_grid([3, 3, 5, -1], [4, 4, 6, -1])
    assert contador.shape == grid.SHAPE and contador[3, 4] == 2 and contador[5, 6] == 1 and contador.sum() == 3


@pytest.mark.parametrize("anillo, esperado", [(0, 1), (1, 8), (2, 16), (3, 24)])
def test_los_anillos_tienen_las_celdas_esperadas(anillo, esperado):
    assert grid.ring_kernel(anillo).sum() == esperado


def test_la_suma_por_anillos_pondera_la_vecindad():
    una = np.zeros(grid.SHAPE)
    una[20, 20] = 1.0
    ponderada = grid.neighborhood_sum(una)
    assert ponderada[20, 20] == 1.0 and ponderada[20, 21] == 0.5 and ponderada[21, 21] == 0.5     # anillo 1
    assert ponderada[20, 22] == 0.25 and ponderada[22, 22] == 0.25                                 # anillo 2
    assert ponderada[20, 23] == 0.0 and ponderada.sum() == pytest.approx(1 + 8 * 0.5 + 16 * 0.25)


def test_los_bordes_no_dan_la_vuelta():
    una = np.zeros(grid.SHAPE)
    una[0, 0] = 1.0
    ponderada = grid.neighborhood_sum(una)
    assert ponderada[0, 0] == 1.0 and ponderada[grid.N_ROWS - 1, grid.N_COLS - 1] == 0.0
    assert ponderada.sum() < 1 + 8 * 0.5 + 16 * 0.25                       # parte de la vecindad cae fuera


def test_activas_son_las_celdas_con_algun_poi_en_ella_o_en_su_vecindad():
    una = np.zeros(grid.SHAPE)
    una[10, 10] = 1.0
    activas = grid.active_mask(una, anillo=1)
    assert activas.sum() == 9 and activas[10, 10] and activas[11, 11] and not activas[12, 10]


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------

def test_selector_toda_la_categoria_un_subconjunto_o_todo_menos_algo():
    assert Selector("food_drink").matches("food_drink", "cafe") and not Selector("food_drink").matches("school", "cafe")
    assert selector("business", "bakery").matches("business", "bakery") and not selector("business", "bakery").matches("business", "butcher")
    todo_menos = selector_except("business", "company", "government")
    assert todo_menos.matches("business", "bakery") and not todo_menos.matches("business", "company")
    assert not todo_menos.matches("school", "bakery")


# ---------------------------------------------------------------------------
# CellCounts
# ---------------------------------------------------------------------------

def test_los_conteos_se_separan_por_categoria_y_subcategoria():
    cc = CellCounts.from_pois(pois_en((10, 10, "food_drink", "cafe"), (10, 10, "food_drink", "cafe"),
                                      (10, 10, "food_drink", "bar"), (10, 11, "business", "bakery")))
    assert cc.pairs() == [("business", "bakery"), ("food_drink", "bar"), ("food_drink", "cafe")]
    assert cc.arrays[("food_drink", "cafe")][10, 10] == 2 and cc.arrays[("business", "bakery")][10, 11] == 1
    assert cc.grid([Selector("food_drink")])[10, 10] == 3 and cc.total_grid().sum() == 4


def test_subcategoria_vacia_o_nula_se_cuenta_como_cadena_vacia():
    df = pois_en((5, 5, "business", None), (5, 5, "business", "bakery"))
    df.loc[0, "subcategory"] = np.nan
    cc = CellCounts.from_pois(df)
    assert ("business", "") in cc.arrays and cc.grid([Selector("business")])[5, 5] == 2


def test_los_pois_fuera_de_la_rejilla_se_cuentan_aparte():
    df = pd.concat([pois_en((5, 5, "school", "school")),
                    pd.DataFrame([{"category": "school", "subcategory": "school", "latitude": 40.0, "longitude": 14.5},
                                  {"category": None, "subcategory": "x", "latitude": 35.9, "longitude": 14.5}])],
                   ignore_index=True)
    cc = CellCounts.from_pois(df)
    assert cc.n_total == 2 and cc.n_fuera == 1 and cc.total_grid().sum() == 1       # sin categoría se descarta; el de fuera, aparte


def test_sin_pois_los_conteos_estan_vacios_pero_las_consultas_funcionan():
    cc = CellCounts.from_pois(pd.DataFrame())
    assert cc.pairs() == [] and cc.total_grid().sum() == 0 and cc.grid([Selector("x")]).shape == grid.SHAPE
    assert cc.count_in_area([Selector("x")]) == 0 and cc.to_frame().empty


def test_exclude_quita_del_conteo_lo_que_cumple_el_objetivo():
    cc = CellCounts.from_pois(pois_en((8, 8, "food_drink", "cafe"), (8, 8, "food_drink", "bar")))
    assert cc.grid([Selector("food_drink")], exclude=[selector("food_drink", "bar")])[8, 8] == 1
    assert cc.count_in_area([Selector("food_drink")], exclude=[Selector("food_drink")]) == 0


def test_la_tabla_celda_por_subcategoria():
    cc = CellCounts.from_pois(pois_en((10, 10, "food_drink", "cafe"), (10, 10, "food_drink", "cafe"), (30, 30, "school", "school")))
    activas = grid.active_mask(cc.total_grid(), anillo=0)
    tabla = cc.to_frame(activas)
    assert list(tabla.index) == ["r10c10", "r30c30"] and tabla.index.name == "cell_id"
    assert tabla.loc["r10c10", "food_drink|cafe"] == 2 and tabla.loc["r30c30", "school|school"] == 1
    assert tabla.to_numpy().sum() == 3 and tabla.dtypes.map(lambda d: d.kind).eq("i").all()
    assert len(cc.to_frame()) == 2295                                               # sin máscara: todas las celdas
