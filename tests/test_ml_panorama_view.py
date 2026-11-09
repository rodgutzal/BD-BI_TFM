"""Tests de la fase 2b, parte sin interfaz (src/ml/panorama_view.py): opciones de competencia, perfil personalizado con sus
avisos, panorama recalculado con ese perfil, brecha precalculada que no cambia con el perfil y filtro de oportunidad."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import business_profiles as bp  # noqa: E402
from src.ml import grid, panorama  # noqa: E402
from src.ml import panorama_view as pv  # noqa: E402
from src.ml.cell_counts import CellCounts, Selector, selector, selector_except  # noqa: E402
from src.ml.lenses import compute_lenses  # noqa: E402

DATA_ML = ROOT / "data" / "ml"
FOOD = bp.get_default_profile("food_drink")


def punto(fila, col, cat, sub):
    lat, lon = grid.cell_center(fila, col)
    return {"category": cat, "subcategory": sub, "latitude": float(lat), "longitude": float(lon)}


@pytest.fixture(scope="module")
def counts():
    filas = ([punto(10, 10 + i, "food_drink", "restaurant") for i in range(6)]
             + [punto(10, 10 + i, "food_drink", "bar") for i in range(3)]
             + [punto(11, 10 + i, "business", "convenience") for i in range(4)]
             + [punto(11, 10, "business", "company")]
             + [punto(12, 10 + i, "edificio", "apartments") for i in range(5)]
             + [punto(12, 10, "transporte", "bus_stop")]
             + [punto(12, 10, "leisure", "")])
    return CellCounts.from_pois(pd.DataFrame(filas))


@pytest.fixture(scope="module")
def datos():
    return panorama.read_panorama(DATA_ML), panorama.read_counts(DATA_ML)


# ---- opciones ----------------------------------------------------------------------------------------------------
def test_expand_selectors_separa_las_subcategorias_y_etiqueta_el_resto():
    """Cada subcategoría de un selector queda por separado; una categoría entera y un «todo salvo» tienen su etiqueta."""
    e = pv.expand_selectors([selector("business", "bakery", "pastry"), selector("food_drink"), selector_except("business", "company", "it")])
    assert "business: bakery" in e and "business: pastry" in e
    assert "food_drink (toda la categoría)" in e
    assert any(k.startswith("business (todo salvo 2 subcategorías") and "company" in k for k in e)
    assert e["business: bakery"] == selector("business", "bakery")


def test_expandir_no_cambia_lo_que_se_cuenta(counts):
    """La unión de los selectores expandidos cuenta lo mismo que los originales: dividir no altera el perfil."""
    for perfil in bp.DEFAULT_PROFILES.values():
        for original in (perfil.competencia_directa, perfil.competencia_indirecta):
            expandidos = tuple(pv.expand_selectors(original).values())
            np.testing.assert_array_equal(counts.grid(original), counts.grid(expandidos))


def test_available_pairs_omite_el_contexto_y_lo_vacio(counts):
    """Edificios y transporte no son comercios: no se ofrecen como competencia. La subcategoría vacía se etiqueta."""
    pares = pv.available_pairs(counts)
    assert "food_drink: restaurant" in pares and "business: convenience" in pares
    assert not any(k.startswith(("edificio", "transporte")) for k in pares)
    assert "leisure: (sin subcategoría)" in pares and pares["leisure: (sin subcategoría)"].matches("leisure", "")


def test_competition_options_incluye_los_defectos_y_son_disjuntos(counts):
    """Los valores por defecto de directa e indirecta están entre las opciones y no se solapan."""
    opciones, directa, indirecta = pv.competition_options(FOOD, counts)
    assert set(directa) | set(indirecta) <= set(opciones) and not set(directa) & set(indirecta)
    assert directa == ["food_drink (toda la categoría)"] and "business: convenience" in indirecta
    assert "food_drink: bar" in opciones                       # se puede añadir algo más fino


def _por_defecto(counts, perfil=FOOD):
    opciones, directa, indirecta = pv.competition_options(perfil, counts)
    return opciones, directa, indirecta, list(perfil.segmentos), list(perfil.proveedores)


# ---- perfil personalizado ----------------------------------------------------------------------------------------
def test_sin_cambios_devuelve_el_perfil_por_defecto_sin_avisos(counts):
    """Si el usuario no toca nada, el perfil es el de por defecto (no personalizado) y no hay ningún aviso."""
    perfil, avisos = pv.custom_profile(FOOD, *_por_defecto(counts))
    assert perfil is FOOD and not perfil.personalizado and avisos == []


def test_el_orden_de_la_seleccion_no_cuenta_como_cambio(counts):
    """Elegir lo mismo en otro orden no hace personalizado el perfil."""
    opciones, directa, indirecta, seg, prov = _por_defecto(counts)
    perfil, avisos = pv.custom_profile(FOOD, opciones, directa, list(reversed(indirecta)), list(reversed(seg)), list(reversed(prov)))
    assert not perfil.personalizado and avisos == []


def test_cambiar_un_segmento_personaliza_el_perfil(counts):
    """Quitar un segmento da un perfil personalizado con ese segmento menos, sin avisos si es razonable."""
    opciones, directa, indirecta, seg, prov = _por_defecto(counts)
    perfil, avisos = pv.custom_profile(FOOD, opciones, directa, indirecta, [s for s in seg if s != "turistas"], prov)
    assert perfil.personalizado and "turistas" not in perfil.segmentos and avisos == []


def test_quitar_todos_los_segmentos_conserva_los_de_por_defecto_y_avisa(counts):
    """Una lente que el perfil tiene no puede quedar vacía: se conserva y se avisa."""
    opciones, directa, indirecta, seg, prov = _por_defecto(counts)
    perfil, avisos = pv.custom_profile(FOOD, opciones, directa, indirecta, [], prov)
    assert set(perfil.segmentos) == set(FOOD.segmentos) and any("no puede quedar vacía" in a for a in avisos)


def test_quitar_toda_la_competencia_directa_avisa(counts):
    """Sin competencia directa se conserva la de por defecto, con aviso."""
    opciones, directa, indirecta, seg, prov = _por_defecto(counts)
    perfil, avisos = pv.custom_profile(FOOD, opciones, [], indirecta, seg, prov)
    assert perfil.competencia_directa == FOOD.competencia_directa and any("competencia directa" in a for a in avisos)


def test_quitar_mas_de_la_mitad_de_la_competencia_avisa_del_optimismo(counts):
    """Quitar la competencia indirecta (3 de 4 elementos) supera el umbral y avisa de que el panorama será más optimista."""
    opciones, directa, indirecta, seg, prov = _por_defecto(counts)
    perfil, avisos = pv.custom_profile(FOOD, opciones, directa, [], seg, prov)
    assert perfil.personalizado and any("más de la mitad" in a for a in avisos)
    assert pv.deviation(perfil, FOOD) == pytest.approx(0.75)


def test_anadir_competencia_no_avisa_de_optimismo(counts):
    """Añadir competencia hace el panorama más conservador: personaliza el perfil pero sin aviso."""
    opciones, directa, indirecta, seg, prov = _por_defecto(counts)
    perfil, avisos = pv.custom_profile(FOOD, opciones, directa, indirecta + ["leisure: (sin subcategoría)"], seg, prov)
    assert perfil.personalizado and avisos == [] and pv.deviation(perfil, FOOD) == 0.0


def test_un_elemento_en_directa_e_indirecta_cuenta_solo_como_directa(counts):
    """Si se elige en las dos, se avisa y solo cuenta una vez (en la directa)."""
    opciones, directa, indirecta, seg, prov = _por_defecto(counts)
    perfil, avisos = pv.custom_profile(FOOD, opciones, directa + ["business: convenience"], indirecta, seg, prov)
    assert any("directa e indirecta a la vez" in a for a in avisos)
    assert selector("business", "convenience") in perfil.competencia_directa
    assert not any(s.matches("business", "convenience") for s in perfil.competencia_indirecta)


def test_same_profile_distingue_competencia_segmentos_y_proveedores():
    """Cualquiera de las tres definiciones distinta hace que los perfiles no sean el mismo."""
    from dataclasses import replace
    base = FOOD
    assert pv.same_profile(base, replace(base, personalizado=True))
    assert not pv.same_profile(base, replace(base, segmentos=base.segmentos[:-1]))
    assert not pv.same_profile(base, replace(base, proveedores=base.proveedores[:-1]))
    assert not pv.same_profile(base, replace(base, competencia_indirecta=()))


# ---- panorama con el perfil --------------------------------------------------------------------------------------
def test_gap_table_solo_existe_para_las_categorias_con_brecha(datos):
    """food_drink y business tienen brecha (no validada); hospital no."""
    guardado, _ = datos
    for clave in ("food_drink", "business"):
        tabla, modelo, validada = pv.gap_table(guardado, clave)
        assert tabla is not None and list(tabla.columns) == list(panorama.COLUMNAS_BRECHA) and modelo and validada is False
    assert pv.gap_table(guardado, "hospital") == (None, "", False)


def test_la_vista_por_defecto_coincide_con_la_tabla_guardada(datos):
    """Recalcular el perfil por defecto desde los conteos da las lentes del panorama guardado."""
    guardado, counts = datos
    for clave, perfil in bp.DEFAULT_PROFILES.items():
        vista = pv.compute_view(counts, perfil, guardado, clave)
        g = guardado[guardado["perfil"] == clave].set_index("cell_id")
        assert list(vista.index) == list(g.index)
        for col in ("competencia_directa", "mercado_total", "proveedores_total", "confianza"):
            np.testing.assert_allclose(vista[col].to_numpy(dtype=float), g[col].to_numpy(dtype=float), rtol=1e-5, equal_nan=True)


def test_un_perfil_distinto_cambia_las_lentes_pero_no_la_brecha(datos):
    """Quitar la competencia indirecta baja la competencia directa+indirecta pero la brecha sigue siendo la precalculada."""
    guardado, counts = datos
    base = pv.compute_view(counts, FOOD, guardado, "food_drink")
    opciones, directa, _ = pv.competition_options(FOOD, counts)
    perfil, _ = pv.custom_profile(FOOD, opciones, directa, [], FOOD.segmentos, FOOD.proveedores)
    vista = pv.compute_view(counts, perfil, guardado, "food_drink")
    assert (vista["competencia_indirecta"] == 0).all() and (base["competencia_indirecta"] > 0).any()
    pd.testing.assert_frame_equal(vista[list(panorama.COLUMNAS_BRECHA)], base[list(panorama.COLUMNAS_BRECHA)])
    assert not vista["brecha_validada"].any()


def test_un_segmento_menos_cambia_el_mercado(datos):
    """Con solo «residentes» el índice de mercado es el de residentes escalado, distinto del combinado."""
    guardado, counts = datos
    perfil, _ = pv.custom_profile(FOOD, *_por_defecto(counts)[:3], ["residentes"], FOOD.proveedores)
    base, vista = pv.compute_view(counts, FOOD, guardado, "food_drink"), pv.compute_view(counts, perfil, guardado, "food_drink")
    assert "mercado_turistas" not in vista and "mercado_turistas" in base
    assert not np.allclose(base["mercado_total"], vista["mercado_total"])


# ---- filtro de oportunidad y capas -------------------------------------------------------------------------------
def _vista_min(mercado, competencia, confianza):
    return pd.DataFrame({"pct_mercado_total": mercado, "pct_competencia_directa": competencia, "confianza_nivel": confianza})


def test_filtro_de_oportunidad_en_los_umbrales():
    """Mercado ≥ 0,75 y competencia ≤ 0,25 (inclusivos) y confianza no baja."""
    v = _vista_min([0.75, 0.74, 0.9, 0.9, 0.9], [0.25, 0.1, 0.26, 0.0, 0.0], ["alta", "alta", "alta", "baja", "media"])
    assert pv.opportunity_mask(v).tolist() == [True, False, False, False, True]


def test_filtro_de_oportunidad_ignora_las_celdas_sin_datos():
    """Un NaN en un percentil nunca cuenta como oportunidad."""
    v = _vista_min([np.nan, 0.9], [0.1, np.nan], ["alta", "alta"])
    assert not pv.opportunity_mask(v).any()


def test_capas_disponibles_omiten_lo_que_no_tiene_datos(datos):
    """La brecha solo es una capa si la categoría la tiene; una lente toda NaN no se ofrece."""
    guardado, counts = datos
    con = pv.compute_view(counts, FOOD, guardado, "food_drink")
    sin = pv.compute_view(counts, bp.get_default_profile("hospital"), guardado, "hospital")
    assert pv.CAPA_BRECHA in pv.available_layers(con) and pv.CAPA_BRECHA not in pv.available_layers(sin)
    assert pv.available_layers(con)[0] == "Competencia directa (conteo ponderado)"
    sin_mercado = sin.assign(mercado_total=np.nan)
    assert "Mercado (índice 0-1)" not in pv.available_layers(sin_mercado)


def test_layer_values_devuelve_la_columna_correcta(datos):
    """Cada capa muestra su columna; la de brecha, la brecha relativa."""
    guardado, counts = datos
    v = pv.compute_view(counts, FOOD, guardado, "food_drink")
    for capa, (col, _) in pv.CAPAS.items():
        assert pv.layer_values(v, capa)[0].equals(v[col])
    assert pv.layer_values(v, pv.CAPA_BRECHA)[0].equals(v["brecha_relativa"])


def test_cell_label_incluye_celda_zona_y_distancia():
    """La etiqueta de la lista de celdas dice dónde está."""
    fila = pd.Series({"zona_cercana": "Sliema", "dist_zona_m": 412.4})
    assert pv.cell_label("r30c10", fila) == "r30c10 · Sliema (412 m del centro de zona)"


def test_el_modulo_no_importa_scikit_learn():
    """La interfaz usa este módulo en el contenedor del dashboard, que no carga scikit-learn."""
    import subprocess
    codigo = ("import sys; sys.path.insert(0, sys.argv[1]); import src.ml.panorama_view; "
              "sys.exit(1 if any(m.split('.')[0] == 'sklearn' for m in sys.modules) else 0)")
    assert subprocess.run([sys.executable, "-c", codigo, str(ROOT)]).returncode == 0
