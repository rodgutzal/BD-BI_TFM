"""Tests de los perfiles de negocio, las tres lentes y las variables con control de fuga (src/ml/*)
y de la herramienta tools/measure_lens_variance.py."""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.locations import LOCATIONS  # noqa: E402
from src.ml import business_profiles as bp  # noqa: E402
from src.ml import features, grid  # noqa: E402
from src.ml.cell_counts import CellCounts, Selector, selector  # noqa: E402
from src.ml.lenses import compute_lenses, lens_coverage  # noqa: E402
from src.ml.osm_context import CONTEXTO  # noqa: E402
from src.poi_client import CATEGORY_TAGS  # noqa: E402

# tools/ no es un paquete: se carga el script por ruta.
_spec = importlib.util.spec_from_file_location("measure_lens_variance", ROOT / "tools" / "measure_lens_variance.py")
mlv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mlv)


def pois_en(*celdas):
    filas = []
    for fila, col, cat, sub in celdas:
        lat, lon = grid.cell_center(fila, col)
        filas.append({"category": cat, "subcategory": sub, "latitude": float(lat), "longitude": float(lon)})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Perfiles por defecto
# ---------------------------------------------------------------------------

def test_hay_un_perfil_por_cada_categoria_de_overpass():
    assert set(bp.DEFAULT_PROFILES) == set(CATEGORY_TAGS)


@pytest.mark.parametrize("clave", sorted(bp.DEFAULT_PROFILES))
def test_cada_perfil_es_coherente(clave):
    p = bp.DEFAULT_PROFILES[clave]
    assert p.key == clave and p.nombre and len(p.competencia_directa) > 0 and not p.personalizado
    assert set(p.segmentos) <= set(bp.SEGMENTOS_POI) and set(p.proveedores) <= set(bp.PROVEEDORES_POI)
    for s in p.competencia_directa + p.competencia_indirecta:
        assert s.category in CATEGORY_TAGS


def test_los_selectores_de_segmentos_y_proveedores_usan_categorias_reales():
    for sels in list(bp.SEGMENTOS_POI.values()) + list(bp.PROVEEDORES_POI.values()):
        for s in sels:
            assert s.category in set(CATEGORY_TAGS) | set(CONTEXTO)         # POIs de Overpass o contexto de la fase 1b


def test_residentes_usan_edificios_y_los_distribuidores_sanitarios_siguen_sin_proxy():
    assert [s.category for s in bp.SEGMENTOS_POI["residentes"]] == ["edificio"]
    assert bp.PROVEEDORES_POI["distribuidores_sanitarios"] == ()                # sin etiqueta en OSM: sin datos


def test_perfil_inexistente_lanza_error():
    with pytest.raises(ValueError, match="Categoría sin perfil"):
        bp.get_default_profile("zapateria")


def test_el_comercio_generico_no_cuenta_las_oficinas_como_competencia():
    p = bp.get_default_profile("business")
    assert not any(s.matches("business", "company") for s in p.competencia_directa)
    assert any(s.matches("business", "bakery") for s in p.competencia_directa)


# ---------------------------------------------------------------------------
# Ajustes del usuario
# ---------------------------------------------------------------------------

def test_ajustar_no_modifica_el_perfil_por_defecto():
    base = bp.get_default_profile("food_drink")
    nuevo, avisos = bp.apply_overrides(base, segmentos=("turistas",))
    assert nuevo.segmentos == ("turistas",) and nuevo.personalizado and avisos == []
    assert base.segmentos != nuevo.segmentos and not base.personalizado


def test_una_lente_no_puede_quedar_vacia_y_se_conserva_el_valor_por_defecto():
    base = bp.get_default_profile("food_drink")
    nuevo, avisos = bp.apply_overrides(base, competencia_directa=(), segmentos=(), proveedores=())
    assert nuevo.competencia_directa == base.competencia_directa
    assert nuevo.segmentos == base.segmentos and nuevo.proveedores == base.proveedores
    assert len(avisos) == 3 and all("no puede quedar vacía" in a for a in avisos)


def test_una_lente_que_ya_estaba_vacia_por_defecto_puede_seguir_vacia():
    base = bp.get_default_profile("leisure")                  # sin proveedores por defecto
    nuevo, avisos = bp.apply_overrides(base, proveedores=())
    assert nuevo.proveedores == () and avisos == []


def test_los_nombres_desconocidos_se_descartan_con_aviso():
    base = bp.get_default_profile("food_drink")
    nuevo, avisos = bp.apply_overrides(base, segmentos=("turistas", "marcianos"), proveedores=("mayoristas", "dragones"))
    assert nuevo.segmentos == ("turistas",) and nuevo.proveedores == ("mayoristas",)
    assert any("marcianos" in a for a in avisos) and any("dragones" in a for a in avisos)


def test_quitar_mas_de_la_mitad_de_la_competencia_avisa_de_optimismo():
    base = bp.get_default_profile("food_drink")                # elementos: food_drink(*) + 3 sustitutos = 4
    ligero, avisos = bp.apply_overrides(base, competencia_indirecta=())          # quita 3 de 4 = 75 %
    assert bp.desviacion_competencia(ligero, base) == pytest.approx(0.75)
    assert any("más de la mitad" in a for a in avisos)
    poco, avisos2 = bp.apply_overrides(base, competencia_indirecta=(selector("business", "convenience", "deli"),))
    assert bp.desviacion_competencia(poco, base) == pytest.approx(0.25) and avisos2 == []     # quita 1 de 4


def test_anadir_competencia_no_cuenta_como_desviacion():
    base = bp.get_default_profile("food_drink")
    mas, avisos = bp.apply_overrides(base, competencia_indirecta=base.competencia_indirecta + (selector("business", "kiosk"),))
    assert bp.desviacion_competencia(mas, base) == 0.0 and avisos == []


def test_el_perfil_por_defecto_tiene_desviacion_cero_y_cambiarlo_todo_da_uno():
    base = bp.get_default_profile("food_drink")
    assert bp.desviacion_competencia(base) == 0.0
    otro, _ = bp.apply_overrides(base, competencia_directa=(selector("school"),), competencia_indirecta=(selector("mall"),))
    assert bp.desviacion_competencia(otro, base) == 1.0


def test_el_umbral_de_aviso_es_la_mitad():
    assert bp.UMBRAL_DESVIACION == 0.5


# ---------------------------------------------------------------------------
# Lentes
# ---------------------------------------------------------------------------

@pytest.fixture
def escena():
    """Un restaurante en (20,20), una carnicería en (20,21), un mayorista lejano y una oficina en (20,19)."""
    return CellCounts.from_pois(pois_en(
        (20, 20, "food_drink", "restaurant"), (20, 21, "business", "butcher"), (20, 19, "business", "company"),
        (35, 40, "business", "wholesale")))


def test_la_competencia_se_pondera_por_vecindad(escena):
    lentes = compute_lenses(escena, bp.get_default_profile("food_drink"))
    assert lentes.loc["r20c20", "competencia_directa"] == 1.0          # la propia celda
    assert lentes.loc["r20c21", "competencia_directa"] == 0.5          # celda vecina
    assert lentes.loc["r20c22", "competencia_directa"] == 0.25         # anillo 2


def test_solo_salen_las_celdas_activas_y_el_indice_es_cell_id(escena):
    lentes = compute_lenses(escena, bp.get_default_profile("food_drink"))
    assert lentes.index.name == "cell_id" and "r20c20" in lentes.index and "r00c00" not in lentes.index
    todas = np.ones(grid.SHAPE, dtype=bool)
    assert len(compute_lenses(escena, bp.get_default_profile("food_drink"), todas)) == 2295


def test_segmento_sin_pois_es_nan_y_no_cero(escena):
    lentes = compute_lenses(escena, bp.get_default_profile("food_drink"))
    assert lentes["mercado_residentes"].isna().all()                    # sin proxy: 'no lo sabemos'
    assert lentes["mercado_estudiantes"].isna().all()                   # hay perfil pero ningún colegio en los datos
    assert lentes.loc["r20c20", "mercado_oficinistas"] == 0.5           # la oficina está en la celda vecina
    assert lentes.loc["r20c19", "mercado_oficinistas"] == 1.0


def test_cero_y_sin_datos_son_cosas_distintas(escena):
    lentes = compute_lenses(escena, bp.get_default_profile("food_drink"))
    lejos = lentes.loc["r35c40"]                       # activa por el mayorista; sin oficinas cerca
    assert lejos["mercado_oficinistas"] == 0.0 and np.isnan(lejos["mercado_residentes"])


def test_proveedores_total_y_diversidad(escena):
    lentes = compute_lenses(escena, bp.get_default_profile("food_drink"))
    fila = lentes.loc["r20c20"]
    assert fila["proveedores_carnicerias"] == 0.5 and fila["proveedores_total"] == 0.5
    assert fila["proveedores_diversidad"] == pytest.approx(1 / 7)       # 1 de los 7 tipos del perfil está presente
    assert lentes.loc["r35c40", "proveedores_mayoristas"] == 1.0


def test_el_apoyo_cuenta_pois_sin_ponderar_en_la_celda_y_sus_8_vecinas(escena):
    lentes = compute_lenses(escena, bp.get_default_profile("food_drink"))
    assert lentes.loc["r20c20", "apoyo_competencia"] == 1            # el restaurante
    assert lentes.loc["r20c21", "apoyo_competencia"] == 1
    assert lentes.loc["r20c22", "apoyo_competencia"] == 0            # a 2 celdas: fuera del apoyo (solo celda+anillo 1)


def test_un_poi_cuenta_en_una_sola_lente_la_competencia_manda():
    """Precedencia: un bar es competencia de un restaurante y NO también 'vida nocturna'; una panadería, aquí
    proveedor, tampoco es competencia."""
    cc = CellCounts.from_pois(pois_en((20, 20, "food_drink", "bar"), (20, 20, "leisure", "nightclub"),
                                      (20, 21, "business", "bakery")))
    lentes = compute_lenses(cc, bp.get_default_profile("food_drink"))
    fila = lentes.loc["r20c20"]
    assert fila["competencia_directa"] == 1.0 + 0.0                    # el bar; la discoteca no es food_drink
    assert fila["mercado_vida_nocturna"] == 1.0                        # SOLO la discoteca, no el bar
    assert fila["proveedores_panaderias"] == 0.5


def test_los_museos_no_son_a_la_vez_competencia_y_turistas_en_ocio():
    cc = CellCounts.from_pois(pois_en((20, 20, "leisure", "museum")))
    lentes = compute_lenses(cc, bp.get_default_profile("leisure"))
    assert lentes.loc["r20c20", "competencia_directa"] == 1.0
    assert lentes["mercado_turistas"].isna().all()                     # sin hoteles no se puede medir (circular)


def test_lentes_con_datos_cuenta_cuantas_lentes_se_pueden_calcular():
    cc = CellCounts.from_pois(pois_en((20, 20, "hospital", "pharmacy"), (20, 20, "business", "company")))
    lentes = compute_lenses(cc, bp.get_default_profile("hospital"))
    fila = lentes.loc["r20c20"]
    assert fila["datos_competencia"] and fila["datos_mercado"] and not fila["datos_proveedores"]
    assert fila["lentes_con_datos"] == 2 and np.isnan(fila["proveedores_total"])


def test_ajustar_el_perfil_cambia_la_lente_sin_tocar_los_datos(escena):
    base = bp.get_default_profile("food_drink")
    sin_oficinistas, _ = bp.apply_overrides(base, segmentos=("turistas",))
    a = compute_lenses(escena, base).loc["r20c20", "mercado_total"]
    b = compute_lenses(escena, sin_oficinistas)
    assert a == 0.5 and ("mercado_total" not in b or np.isnan(b.loc["r20c20", "mercado_total"]))


def test_con_cero_pois_las_lentes_no_fallan():
    lentes = compute_lenses(CellCounts.from_pois(pd.DataFrame()), bp.get_default_profile("food_drink"))
    assert lentes.empty


def test_cobertura_de_las_lentes(escena):
    cob = lens_coverage(escena, bp.get_default_profile("food_drink")).set_index(["lente", "nombre"])["pois"]
    assert cob[("proveedores", "mayoristas")] == 1 and cob[("proveedores", "carnicerias")] == 1
    assert cob[("mercado", "oficinistas")] == 1 and cob[("mercado", "residentes")] == 0
    assert cob[("competencia", "directa")] == 1


# ---------------------------------------------------------------------------
# Variables con control de fuga
# ---------------------------------------------------------------------------

OBJETIVO = [Selector("food_drink")]


def test_las_variables_no_incluyen_el_objetivo_ni_en_la_celda_ni_en_la_vecindad():
    """Control de fuga: mover o añadir restaurantes NO cambia ninguna variable (si cambiara, el modelo
    de oferta esperada copiaría su propia etiqueta)."""
    base = pois_en((20, 20, "school", "school"), (21, 21, "business", "bakery"), (20, 20, "food_drink", "cafe"))
    con_mas = pd.concat([base, pois_en((20, 21, "food_drink", "bar"), (22, 22, "food_drink", "pub"))], ignore_index=True)
    a = features.build_features(CellCounts.from_pois(base), OBJETIVO, mask=np.ones(grid.SHAPE, dtype=bool))
    b = features.build_features(CellCounts.from_pois(con_mas), OBJETIVO, mask=np.ones(grid.SHAPE, dtype=bool))
    pd.testing.assert_frame_equal(a, b)
    assert not any(c.startswith("food_drink") and a[c].sum() > 0 for c in a.columns)


def test_las_otras_categorias_si_entran_en_la_celda_y_en_los_anillos():
    cc = CellCounts.from_pois(pois_en((20, 20, "school", "school"), (20, 21, "school", "school"), (20, 22, "school", "school")))
    f = features.build_features(cc, OBJETIVO).loc["r20c20"]
    assert f["school_celda"] == 1 and f["school_anillo1"] == 1 and f["school_anillo2"] == 1


def test_nombres_y_numero_de_variables():
    f = features.build_features(CellCounts.from_pois(pois_en((20, 20, "school", "school"))), OBJETIVO)
    assert f.shape[1] == 7 * 3 + 3 and {"dist_centro_m", "pob_suavizada", "tiempo_viaje_suavizado"} <= set(f.columns)
    assert f["pob_suavizada"].isna().all() and f["tiempo_viaje_suavizado"].isna().all()       # sin zones


def test_el_objetivo_cuenta_solo_la_propia_celda():
    cc = CellCounts.from_pois(pois_en((20, 20, "food_drink", "cafe"), (20, 20, "food_drink", "bar"), (20, 21, "food_drink", "cafe")))
    y = features.target_counts(cc, OBJETIVO)
    assert y["r20c20"] == 2 and y["r20c21"] == 1 and y.name == "objetivo"


def test_distancia_al_centro_de_zona_mas_cercano():
    lat, lon = LOCATIONS["Msida"].latitude, LOCATIONS["Msida"].longitude
    fila, col = (int(x[0]) for x in grid.cell_index(lat, lon))
    f = features.build_features(CellCounts.from_pois(pois_en((fila, col, "school", "school"))), OBJETIVO)
    assert f.loc[grid.cell_id(fila, col), "dist_centro_m"] < 250


def test_poblacion_y_accesibilidad_suavizadas_con_las_zonas():
    zonas = pd.DataFrame({"demanda": {z: 1000.0 * (i + 1) for i, z in enumerate(LOCATIONS)},
                          "tiempo_viaje_prom": {z: 10.0 + i for i, z in enumerate(LOCATIONS)}})
    lat, lon = LOCATIONS["Valletta"].latitude, LOCATIONS["Valletta"].longitude
    fila, col = (int(x[0]) for x in grid.cell_index(lat, lon))
    f = features.build_features(CellCounts.from_pois(pois_en((fila, col, "school", "school"))), OBJETIVO, zonas)
    v = f.loc[grid.cell_id(fila, col)]
    assert zonas["demanda"].min() <= v["pob_suavizada"] <= zonas["demanda"].max()
    assert abs(v["pob_suavizada"] - zonas.loc["Valletta", "demanda"]) < abs(v["pob_suavizada"] - zonas.loc["Marsaskala", "demanda"])
    assert zonas["tiempo_viaje_prom"].min() <= v["tiempo_viaje_suavizado"] <= zonas["tiempo_viaje_prom"].max()


def test_una_zona_sin_dato_se_omite_y_los_pesos_se_renormalizan():
    zonas = pd.DataFrame({"demanda": {z: 5000.0 for z in LOCATIONS}})
    zonas.loc["Msida", "demanda"] = np.nan
    f = features.build_features(CellCounts.from_pois(pois_en((25, 17, "school", "school"))), OBJETIVO, zonas)
    assert f["pob_suavizada"].iloc[0] == pytest.approx(5000.0)


# ---------------------------------------------------------------------------
# Herramienta de medición
# ---------------------------------------------------------------------------

def _crear_db(ruta, filas):
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE pois (id INTEGER PRIMARY KEY, category TEXT, subcategory TEXT, latitude REAL, longitude REAL)")
    con.executemany("INSERT INTO pois (category, subcategory, latitude, longitude) VALUES (?,?,?,?)", filas)
    con.commit()
    con.close()


def test_la_herramienta_lee_en_solo_lectura(tmp_path):
    db = tmp_path / "t.db"
    lat, lon = grid.cell_center(20, 20)
    _crear_db(db, [("food_drink", "cafe", float(lat), float(lon))])
    antes = db.read_bytes()
    pois = mlv.load_pois(db)
    assert len(pois) == 1 and db.read_bytes() == antes and [p.name for p in tmp_path.iterdir()] == ["t.db"]


def test_describe_lens_excluye_nan_y_los_cuenta_aparte():
    d = mlv.describe_lens(pd.Series([0.0, 0.0, 2.0, 4.0, np.nan]))
    assert d["n"] == 4 and d["sin_datos"] == 1 and d["pct_cero"] == 0.5 and d["media"] == 1.5
    assert d["cv"] == pytest.approx(d["desv"] / 1.5) and d["max"] == 4.0
    assert mlv.describe_lens(pd.Series([np.nan, np.nan])) == {"n": 0, "sin_datos": 2}


def test_la_serie_constante_no_da_cv_infinito():
    assert np.isnan(mlv.describe_lens(pd.Series([0.0, 0.0, 0.0]))["cv"])


def test_cuadrante_de_oportunidad():
    # mercado alto y competencia baja en 1 de cada 4 celdas cuando son independientes
    lentes = pd.DataFrame({"mercado_total": [1, 1, 9, 9], "competencia_directa": [1, 9, 1, 9]})
    assert mlv.opportunity_share(lentes) == 0.25
    correlacionadas = pd.DataFrame({"mercado_total": [1, 2, 8, 9], "competencia_directa": [1, 2, 8, 9]})
    assert mlv.opportunity_share(correlacionadas) == 0.0
    assert np.isnan(mlv.opportunity_share(pd.DataFrame({"mercado_total": [np.nan], "competencia_directa": [1]})))


def test_la_herramienta_imprime_un_informe_por_perfil(tmp_path, capsys):
    db = tmp_path / "t.db"
    rng = np.random.default_rng(0)
    filas = []
    for _ in range(300):
        f, c = int(rng.integers(15, 30)), int(rng.integers(12, 28))
        lat, lon = grid.cell_center(f, c)
        cat, sub = [("food_drink", "cafe"), ("business", "company"), ("business", "butcher"), ("school", "school")][int(rng.integers(0, 4))]
        filas.append((cat, sub, float(lat), float(lon)))
    _crear_db(db, filas)
    assert mlv.main(["--db", str(db)]) == 0
    salida = capsys.readouterr().out
    assert "celdas activas" in salida and "Restaurante, café o bar (food_drink)" in salida
    assert salida.count("===") == 2 * len(bp.DEFAULT_PROFILES) and "Spearman entre lentes" in salida
