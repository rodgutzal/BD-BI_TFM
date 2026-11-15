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
from src.ml import places
from src.ml.cell_counts import CellCounts, selector, selector_except  # noqa: E402

DATA_ML = ROOT / "data" / "ml"
FOOD = bp.get_default_profile("food_drink")


def punto(fila, col, cat, sub):
    lat, lon = grid.cell_center(fila, col)
    return {"category": cat, "subcategory": sub, "latitude": float(lat), "longitude": float(lon)}


@pytest.fixture(scope="module")
def counts():
    filas = (
        [punto(10, 10 + i, "food_drink", "restaurant") for i in range(6)]
        + [punto(10, 10 + i, "food_drink", "bar") for i in range(3)]
        + [punto(11, 10 + i, "business", "convenience") for i in range(4)]
        + [punto(11, 10, "business", "company")]
        + [punto(12, 10 + i, "edificio", "apartments") for i in range(5)]
        + [punto(12, 10, "transporte", "bus_stop")]
        + [punto(12, 10, "leisure", "")]
    )
    return CellCounts.from_pois(pd.DataFrame(filas))


@pytest.fixture(scope="module")
def datos():
    return panorama.read_panorama(DATA_ML), panorama.read_counts(DATA_ML)


@pytest.fixture(scope="module")
def datos_con_brecha(datos_ml_con_brecha):
    """Como `datos`, pero con una brecha SINTÉTICA: la tabla publicada ya no trae brecha (docs/DATOS_Y_LICENCIAS.md)."""
    return panorama.read_panorama(datos_ml_con_brecha), panorama.read_counts(datos_ml_con_brecha)


# ---- opciones ----------------------------------------------------------------------------------------------------
def test_expand_selectors_separa_las_subcategorias_y_etiqueta_el_resto():
    """Cada subcategoría de un selector queda por separado; una categoría entera y un «todo salvo» tienen su etiqueta."""
    e = pv.expand_selectors(
        [selector("business", "bakery", "pastry"), selector("food_drink"), selector_except("business", "company", "it")]
    )
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
    assert "food_drink: bar" in opciones  # se puede añadir algo más fino


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
    perfil, avisos = pv.custom_profile(
        FOOD, opciones, directa, list(reversed(indirecta)), list(reversed(seg)), list(reversed(prov))
    )
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
def test_la_tabla_publicada_ya_no_tiene_brecha_en_ninguna_categoria(datos):
    guardado, _ = datos
    for clave in bp.DEFAULT_PROFILES:
        assert pv.gap_table(guardado, clave) == (None, "", False), clave


def test_gap_table_solo_existe_para_las_categorias_con_brecha(datos_con_brecha):
    """Con una brecha (sintética) en food_drink y business (no validada), hospital no tiene."""
    guardado, _ = datos_con_brecha
    for clave in ("food_drink", "business"):
        tabla, modelo, validada = pv.gap_table(guardado, clave)
        assert (
            tabla is not None and list(tabla.columns) == list(panorama.COLUMNAS_BRECHA) and modelo and validada is False
        )
    assert pv.gap_table(guardado, "hospital") == (None, "", False)


def test_la_vista_por_defecto_coincide_con_la_tabla_guardada(datos):
    """Recalcular el perfil por defecto desde los conteos da las lentes del panorama guardado."""
    guardado, counts = datos
    for clave, perfil in bp.DEFAULT_PROFILES.items():
        vista = pv.compute_view(counts, perfil, guardado, clave)
        g = guardado[guardado["perfil"] == clave].set_index("cell_id")
        assert list(vista.index) == list(g.index)
        for col in ("competencia_directa", "mercado_total", "proveedores_total", "confianza"):
            np.testing.assert_allclose(
                vista[col].to_numpy(dtype=float), g[col].to_numpy(dtype=float), rtol=1e-5, equal_nan=True
            )


def test_un_perfil_distinto_cambia_las_lentes_pero_no_la_brecha(datos_con_brecha):
    """Quitar la competencia indirecta baja la competencia directa+indirecta pero la brecha sigue siendo la precalculada."""
    guardado, counts = datos_con_brecha
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
    base, vista = pv.compute_view(counts, FOOD, guardado, "food_drink"), pv.compute_view(
        counts, perfil, guardado, "food_drink"
    )
    assert "mercado_turistas" not in vista and "mercado_turistas" in base
    assert not np.allclose(base["mercado_total"], vista["mercado_total"])


# ---- filtro de oportunidad y capas -------------------------------------------------------------------------------
def _vista_min(mercado, competencia, confianza):
    return pd.DataFrame(
        {"pct_mercado_total": mercado, "pct_competencia_directa": competencia, "confianza_nivel": confianza}
    )


def test_filtro_de_oportunidad_en_los_umbrales():
    """Mercado ≥ 0,75 y competencia ≤ 0,25 (inclusivos) y confianza no baja."""
    v = _vista_min([0.75, 0.74, 0.9, 0.9, 0.9], [0.25, 0.1, 0.26, 0.0, 0.0], ["alta", "alta", "alta", "baja", "media"])
    assert pv.opportunity_mask(v).tolist() == [True, False, False, False, True]


def test_filtro_de_oportunidad_ignora_las_celdas_sin_datos():
    """Un NaN en un percentil nunca cuenta como oportunidad."""
    v = _vista_min([np.nan, 0.9], [0.1, np.nan], ["alta", "alta"])
    assert not pv.opportunity_mask(v).any()


def test_la_tabla_publicada_no_ofrece_la_capa_de_brecha(datos):
    guardado, counts = datos
    for clave, perfil in bp.DEFAULT_PROFILES.items():
        assert pv.CAPA_BRECHA not in pv.available_layers(pv.compute_view(counts, perfil, guardado, clave)), clave


def test_capas_disponibles_omiten_lo_que_no_tiene_datos(datos_con_brecha):
    """La brecha solo es una capa si la categoría la tiene; una lente toda NaN no se ofrece."""
    guardado, counts = datos_con_brecha
    con = pv.compute_view(counts, FOOD, guardado, "food_drink")
    sin = pv.compute_view(counts, bp.get_default_profile("hospital"), guardado, "hospital")
    assert pv.CAPA_BRECHA in pv.available_layers(con) and pv.CAPA_BRECHA not in pv.available_layers(sin)
    assert pv.available_layers(con)[0] == "Competencia directa (conteo ponderado)"
    sin_mercado = sin.assign(mercado_total=np.nan)
    assert "Mercado (índice 0-1)" not in pv.available_layers(sin_mercado)


def test_layer_values_devuelve_la_columna_correcta(datos_con_brecha):
    """Cada capa muestra su columna; la de brecha, la brecha relativa."""
    guardado, counts = datos_con_brecha
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

    codigo = (
        "import sys; sys.path.insert(0, sys.argv[1]); import src.ml.panorama_view; "
        "sys.exit(1 if any(m.split('.')[0] == 'sklearn' for m in sys.modules) else 0)"
    )
    assert subprocess.run([sys.executable, "-c", codigo, str(ROOT)]).returncode == 0


# ---- lugar, celdas por zona y exportación ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def vista_comida(datos):
    guardado, conteos = datos
    return pv.attach_places(pv.compute_view(conteos, FOOD, guardado, "food_drink"), places.read_places(DATA_ML))


def test_el_radio_de_la_zona_es_el_del_puntaje_por_zona():
    """Las celdas de una zona se toman con el mismo radio con el que el puntaje cuenta su competencia."""
    from src.location_scoring import DEFAULT_POI_RADIUS_M

    assert pv.RADIO_ZONA_M == DEFAULT_POI_RADIUS_M


def test_attach_places_rotula_con_la_localidad_y_sin_ella_queda_vacia(vista_comida):
    assert vista_comida["localidad"].ne("").mean() > 0.95
    sin = pv.attach_places(vista_comida.drop(columns="localidad"), None)
    assert (sin["localidad"] == "").all()
    fila = vista_comida[vista_comida["localidad"] != ""].iloc[0]
    assert pv.cell_label(fila.name, fila).startswith(f"{fila['localidad']} · {fila.name} (zona de referencia: ")
    assert pv.cell_label(fila.name, sin.loc[fila.name]).startswith(f"{fila.name} · {fila['zona_cercana']} (")


def test_zone_cells_son_las_del_radio_y_una_celda_puede_estar_en_dos_zonas(vista_comida):
    from src.locations import LOCATIONS

    msida = pv.zone_cells(vista_comida, "Msida")
    d = grid.haversine_m(
        LOCATIONS["Msida"].latitude,
        LOCATIONS["Msida"].longitude,
        vista_comida["lat"].to_numpy(),
        vista_comida["lon"].to_numpy(),
    )
    assert msida.sum() == (d <= pv.RADIO_ZONA_M).sum() > 0
    assert (msida & pv.zone_cells(vista_comida, "Gzira")).any()  # están a menos de 1,5 km: se solapan
    with pytest.raises(ValueError):
        pv.zone_cells(vista_comida, "Atlantis")


def test_candidate_cells_pone_las_estrella_primero_y_excluye_la_confianza_baja(vista_comida):
    sub = pv.candidate_cells(vista_comida, "Valletta")
    assert (
        len(sub) > 0
        and (sub["confianza_nivel"] != "baja").all()
        and pv.zone_cells(vista_comida, "Valletta")[sub.index].all()
    )
    estrella = list(sub["oportunidad"])
    assert estrella == sorted(estrella, reverse=True)  # primero las ★, luego el resto
    resto = sub.loc[~sub["oportunidad"], "mercado_total"].dropna()
    assert resto.is_monotonic_decreasing  # y por mercado de mayor a menor
    assert set(pv.candidate_cells(vista_comida, "Valletta").index) <= set(pv.candidate_cells(vista_comida, None).index)


def test_candidates_table_trae_lugar_lentes_y_enlace(vista_comida):
    tabla = pv.candidates_table(pv.candidate_cells(vista_comida, "Valletta").head(5))
    assert list(tabla.columns) == [
        "★",
        "Lugar",
        "Competencia directa",
        "Mercado (0-1)",
        "Proveedores",
        "Confianza",
        "Mapa",
    ]
    assert tabla.index.name == "Celda" and tabla["Mapa"].str.startswith("https://www.openstreetmap.org/?mlat=").all()
    assert (tabla["Lugar"] != "").all()


def test_zone_summary_tiene_una_fila_por_zona_con_las_estrella_que_hay(vista_comida):
    from src.locations import LOCATIONS

    resumen = pv.zone_summary(vista_comida)
    assert list(resumen.index) == list(LOCATIONS)
    assert (resumen["Celdas activas"] > 0).all()
    assert (resumen["Celdas ★"] <= resumen["Celdas activas"]).all()
    for zona in resumen.index:  # coincide con contarlas a mano
        dentro = pv.zone_cells(vista_comida, zona)
        assert resumen.loc[zona, "Celdas ★"] == pv.opportunity_mask(vista_comida)[dentro].sum()


def test_export_frame_lleva_el_perfil_y_solo_las_celdas_pedidas(vista_comida):
    ids = list(pv.candidate_cells(vista_comida, "Valletta").index[:3])
    df = pv.export_frame(vista_comida, ids + ["r99c99"], FOOD)  # un id que no existe se ignora
    assert list(df.index) == ids and df.index.name == "cell_id"
    assert (df["perfil"] == FOOD.nombre).all() and not df["perfil_personalizado"].any()
    assert {
        "localidad",
        "lat",
        "lon",
        "competencia_directa",
        "mercado_total",
        "confianza_nivel",
        "enlace_mapa",
        "fuente",
    } <= set(df.columns)
    assert df["fuente"].str.contains("OpenStreetMap").all()


def test_export_csv_se_puede_releer_con_acentos(vista_comida):
    ids = list(pv.candidate_cells(vista_comida, None).index[:4])
    datos = pv.export_csv(pv.export_frame(vista_comida, ids, FOOD))
    assert datos.startswith(b"\xef\xbb\xbf")  # BOM para Excel
    releido = pd.read_csv(__import__("io").BytesIO(datos), encoding="utf-8-sig", index_col="cell_id")
    assert list(releido.index) == ids and releido["localidad"].notna().all()
