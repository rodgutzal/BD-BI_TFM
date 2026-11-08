"""Tests de la fase 1 del ML de recomendación: lectura de datos en solo lectura (src/ml/data_access.py), modelos de
oferta esperada (src/ml/models.py), validación espacial (src/ml/validation.py) y tools/validate_location_model.py."""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_poisson_deviance

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.locations import LOCATIONS  # noqa: E402
from src.ml import data_access, grid, models, validation  # noqa: E402
from src.ml.features import CATEGORIAS  # noqa: E402

# tools/ no es un paquete: se carga el script por ruta.
_spec = importlib.util.spec_from_file_location("validate_location_model", ROOT / "tools" / "validate_location_model.py")
vlm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vlm)


def crear_db(ruta, pois=(), foursquare=None, rutas=None, poblacion=None):
    con = sqlite3.connect(ruta)
    con.execute("CREATE TABLE pois (id INTEGER PRIMARY KEY, category TEXT, subcategory TEXT, latitude REAL, longitude REAL)")
    con.executemany("INSERT INTO pois (category, subcategory, latitude, longitude) VALUES (?,?,?,?)", list(pois))
    con.execute("CREATE TABLE zone_demographics (zone_name TEXT, population INTEGER)")
    con.executemany("INSERT INTO zone_demographics VALUES (?,?)", list((poblacion or {}).items()))
    con.execute("CREATE TABLE route_measurements (origin TEXT, destination TEXT, travel_time_min REAL)")
    con.executemany("INSERT INTO route_measurements VALUES (?,?,?)", list(rutas or []))
    if foursquare is not None:
        con.execute("CREATE TABLE pois_foursquare (category TEXT, subcategory TEXT, name TEXT, latitude REAL, longitude REAL)")
        con.executemany("INSERT INTO pois_foursquare VALUES (?,?,?,?,?)", foursquare)
    con.commit()
    con.close()


def datos_sinteticos(n_filas=18, n_cols=22, semilla=0):
    """X, y de una rejilla pequeña: el conteo depende de la densidad de otras categorías (señal real) más ruido."""
    rng = np.random.default_rng(semilla)
    filas, cols = np.meshgrid(np.arange(n_filas) + 10, np.arange(n_cols) + 10, indexing="ij")
    filas, cols = filas.ravel(), cols.ravel()
    ids = [grid.cell_id(f, c) for f, c in zip(filas, cols)]
    X = pd.DataFrame({f"{cat}_{z}": rng.poisson(1.5, len(ids)).astype(float) for cat in CATEGORIAS
                      for z in ("celda", "anillo1", "anillo2")}, index=pd.Index(ids, name="cell_id"))
    X["dist_centro_m"] = rng.uniform(0, 3000, len(ids))
    X["pob_suavizada"] = rng.uniform(5000, 25000, len(ids))
    X["tiempo_viaje_suavizado"] = rng.uniform(5, 20, len(ids))
    y = rng.poisson(0.2 + 1.2 * X["school_celda"].to_numpy() + 0.8 * X["sport_anillo1"].to_numpy())
    return X, y.astype(float)


# ---------------------------------------------------------------------------
# Lectura de datos
# ---------------------------------------------------------------------------

def test_la_lectura_es_de_solo_lectura(tmp_path):
    db = tmp_path / "t.db"
    crear_db(db, pois=[("food_drink", "cafe", 35.9, 14.5)], foursquare=[("restaurant", "x", "A", 35.9, 14.5)])
    antes = db.read_bytes()
    assert len(data_access.load_pois(db)) == 1 and len(data_access.load_pois_foursquare(db)) == 1
    data_access.load_zone_table(db)
    assert db.read_bytes() == antes and [p.name for p in tmp_path.iterdir()] == ["t.db"]


def test_foursquare_es_opcional(tmp_path):
    db = tmp_path / "t.db"
    crear_db(db)                                              # sin tabla pois_foursquare
    f = data_access.load_pois_foursquare(db)
    assert f.empty and list(f.columns) == ["category", "subcategory", "name", "latitude", "longitude"]


def test_tabla_de_zonas_con_poblacion_y_tiempo_de_viaje(tmp_path):
    db = tmp_path / "t.db"
    crear_db(db, poblacion={"Msida": 1000, "Gzira": 2000},
             rutas=[("Msida", "Gzira", 10.0), ("Msida", "Gzira", 20.0), ("Msida", "Sliema", 30.0), ("Sliema", "Gzira", 5.0)])
    z = data_access.load_zone_table(db)
    assert list(z.index) == list(LOCATIONS) and z.loc["Msida", "demanda"] == 1000
    # Msida toca (Msida→Gzira: media 15) y (Msida→Sliema: 30): promedio de rutas = 22,5
    assert z.loc["Msida", "tiempo_viaje_prom"] == pytest.approx(22.5)
    assert z.loc["Gzira", "tiempo_viaje_prom"] == pytest.approx((15.0 + 5.0) / 2)
    assert np.isnan(z.loc["Valletta", "demanda"]) and np.isnan(z.loc["Valletta", "tiempo_viaje_prom"])      # sin dato ≠ 0


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------

def test_la_densidad_suma_las_categorias_en_log():
    X, _ = datos_sinteticos(3, 3)
    d = models.densidad(X)
    assert list(d.columns) == ["densidad_celda", "densidad_anillo1", "densidad_anillo2"]
    esperado = np.log1p(sum(X[f"{c}_celda"] for c in CATEGORIAS))
    np.testing.assert_allclose(d["densidad_celda"], esperado)


def test_cada_modelo_usa_solo_sus_variables():
    X, y = datos_sinteticos(10, 12)
    cambiada = X.copy()
    cambiada["pob_suavizada"] = cambiada["pob_suavizada"] * 10 + 7          # no es 'solo_distancia' ni 'solo_densidad'
    for nombre in ("solo_distancia", "solo_densidad"):
        a = models.fit_predict(nombre, X, y, X)
        b = models.fit_predict(nombre, X, y, cambiada)
        np.testing.assert_allclose(a, b, err_msg=nombre)
    assert not np.allclose(models.fit_predict("solo_poblacion", X, y, X), models.fit_predict("solo_poblacion", X, y, cambiada))


@pytest.mark.parametrize("nombre", models.TODOS)
def test_las_predicciones_son_positivas_y_tienen_una_por_fila(nombre):
    X, y = datos_sinteticos(10, 12)
    p = models.fit_predict(nombre, X.iloc[:80], y[:80], X.iloc[80:])
    assert p.shape == (len(X) - 80,) and (p >= models.MIN_ESPERADO).all() and np.isfinite(p).all()


def test_una_linea_base_sin_su_unica_variable_degrada_a_la_media():
    """Regresión: sin demografía cargada la población llega toda NaN, se descarta y solo_poblacion fallaba con KeyError."""
    X, y = datos_sinteticos(10, 12)
    X["pob_suavizada"] = np.nan
    p = models.fit_predict("solo_poblacion", X.iloc[:80], y[:80], X.iloc[80:])
    np.testing.assert_allclose(p, models.fit_predict("media", X.iloc[:80], y[:80], X.iloc[80:]))


def test_la_media_es_el_promedio_de_entrenamiento():
    X, y = datos_sinteticos(8, 8)
    assert models.fit_predict("media", X, y, X)[0] == pytest.approx(y.mean())


def test_fit_predict_es_determinista_con_la_misma_semilla():
    X, y = datos_sinteticos(10, 12)
    for nombre in ("boosting", "mlp"):
        np.testing.assert_allclose(models.fit_predict(nombre, X, y, X, seed=3), models.fit_predict(nombre, X, y, X, seed=3))


def test_modelo_desconocido_lanza_error():
    X, y = datos_sinteticos(5, 5)
    with pytest.raises(ValueError, match="Modelo desconocido"):
        models.fit_predict("magia", X, y, X)
    with pytest.raises(ValueError):
        models.columnas_de("magia", X)


def test_el_boosting_aprende_la_senal_y_gana_a_la_media():
    X, y = datos_sinteticos(20, 24)
    entrenar, probar = np.arange(len(y)) % 5 != 0, np.arange(len(y)) % 5 == 0
    dev = {n: validation.poisson_deviance(y[probar], models.fit_predict(n, X[entrenar], y[entrenar], X[probar])).mean()
           for n in ("media", "boosting")}
    assert dev["boosting"] < dev["media"] * 0.9


@pytest.mark.parametrize("nombre", ["boosting", "mlp", "solo_densidad"])
def test_una_variable_toda_nan_no_rompe_el_ajuste(nombre):
    """Regresión: sin datos de rutas la accesibilidad llega toda NaN y el boosting fallaba al discretizarla
    (ValueError: window shape cannot be larger than input array shape)."""
    X, y = datos_sinteticos(10, 12)
    X["tiempo_viaje_suavizado"] = np.nan
    p = models.fit_predict(nombre, X.iloc[:80], y[:80], X.iloc[80:])
    assert len(p) == len(X) - 80 and np.isfinite(p).all()


def test_el_conjunto_da_media_y_dispersion():
    X, y = datos_sinteticos(10, 12)
    e = models.fit_predict_ensemble("boosting", X, y, X, n=5, seed=1)
    assert set(e) == {"esperado", "desv", "p10", "p90"} and all(len(v) == len(X) for v in e.values())
    assert (e["desv"] >= 0).all() and (e["p10"] <= e["p90"]).all() and e["desv"].sum() > 0
    una = models.fit_predict_ensemble("boosting", X, y, X, n=1, seed=1)
    assert (una["desv"] == 0).all()


# ---------------------------------------------------------------------------
# Validación espacial
# ---------------------------------------------------------------------------

def test_las_celdas_de_un_bloque_comparten_etiqueta_y_el_desplazamiento_la_cambia():
    filas, cols = np.array([0, 0, 3, 3, 4, 4]), np.array([0, 3, 0, 3, 0, 4])
    etiquetas = validation.block_labels(filas, cols)
    assert etiquetas[0] == etiquetas[1] == etiquetas[2] == etiquetas[3]            # 4x4 celdas
    assert len({etiquetas[3], etiquetas[4], etiquetas[5]}) == 3
    assert validation.block_labels([3], [3], offset=(1, 1))[0] != validation.block_labels([3], [3])[0]


def test_los_pliegues_no_parten_un_bloque_y_estan_equilibrados():
    X, _ = datos_sinteticos(18, 22)
    f, c = validation.positions(X.index)
    etiquetas = validation.block_labels(f, c)
    pliegues = validation.assign_folds(etiquetas, 5, np.random.default_rng(0))
    for bloque in np.unique(etiquetas):
        assert len(set(pliegues[etiquetas == bloque])) == 1                         # un bloque, un único pliegue
    bloques_por_pliegue = [len(set(etiquetas[pliegues == k])) for k in range(5)]
    assert max(bloques_por_pliegue) - min(bloques_por_pliegue) <= 1
    np.testing.assert_array_equal(pliegues, validation.assign_folds(etiquetas, 5, np.random.default_rng(0)))


def test_la_desviacion_de_poisson_coincide_con_scikit_learn_y_los_casos_limite():
    y, mu = np.array([1.0, 3.0, 5.0]), np.array([2.0, 2.5, 6.0])
    assert validation.poisson_deviance(y, mu).mean() == pytest.approx(mean_poisson_deviance(y, mu))
    assert validation.poisson_deviance([0.0], [2.0])[0] == pytest.approx(4.0)       # y=0 -> 2μ
    assert validation.poisson_deviance([4.0], [4.0])[0] == pytest.approx(0.0)
    assert np.isfinite(validation.poisson_deviance([3.0], [0.0])).all()             # μ=0 se recorta, no explota


def test_precision_en_las_k_primeras_y_spearman():
    y = np.arange(10.0)
    assert validation.precision_at_k(y, y, 3) == 1.0
    assert validation.precision_at_k(y, -y, 3) == 0.0
    assert validation.precision_at_k(y, y, 99) == 1.0                              # k mayor que n se recorta
    assert validation.spearman(y, y) == pytest.approx(1.0) and np.isnan(validation.spearman(y, np.ones(10)))


def test_evaluate_devuelve_predicciones_fuera_de_muestra_para_todas_las_celdas():
    X, y = datos_sinteticos(14, 18)
    ev = validation.evaluate(X, y, nombres=("media", "solo_densidad", "boosting"), repeats=3, n_folds=4, seed=1, k_top=10)
    assert ev.oof["boosting"].shape == (3, len(y)) and (ev.oof["boosting"] > 0).all()
    assert len(ev.metricas) == 3 * 3 and set(ev.metricas["modelo"]) == {"media", "solo_densidad", "boosting"}
    resumen = validation.summarize(ev)
    assert list(resumen.index)[0] == "boosting" and resumen["desviacion"].is_monotonic_increasing


def test_la_prediccion_de_una_celda_no_usa_su_propio_valor():
    """Fuera de muestra de verdad: cambiar el valor real de una celda no cambia su propia predicción."""
    X, y = datos_sinteticos(14, 18)
    alterada = y.copy()
    alterada[40] += 50
    a = validation.evaluate(X, y, nombres=("boosting",), repeats=2, n_folds=4, seed=1)
    b = validation.evaluate(X, alterada, nombres=("boosting",), repeats=2, n_folds=4, seed=1)
    assert a.oof["boosting"][0, 40] == b.oof["boosting"][0, 40] and a.oof["boosting"][1, 40] == b.oof["boosting"][1, 40]


def test_el_bootstrap_de_bloques_con_predicciones_identicas_da_cero():
    y = np.arange(40.0) % 5
    bloques = np.repeat(np.arange(8), 5)
    r = validation.block_bootstrap_diff(y, np.full(40, 2.0), np.full(40, 2.0), bloques, n_boot=200)
    assert r == {"diferencia": 0.0, "ic_inf": 0.0, "ic_sup": 0.0}


def test_el_bootstrap_detecta_una_mejora_uniforme_y_es_prudente_si_solo_hay_un_bloque_mejor():
    y = np.tile([0.0, 1.0, 2.0, 3.0, 4.0], 20)
    bloques = np.repeat(np.arange(20), 5)
    bueno = y + 0.01
    malo = np.full(100, 2.0)
    uniforme = validation.block_bootstrap_diff(y, bueno, malo, bloques, n_boot=500, seed=1)
    assert uniforme["ic_sup"] < 0
    # la mejora existe solo en el bloque 0: con pocos bloques que la sostienen, el intervalo debe incluir el 0
    a, b = np.full(100, 2.0), np.full(100, 2.0)
    a[:5] = y[:5] + 0.01
    solo_uno = validation.block_bootstrap_diff(y, a, b, bloques, n_boot=500, seed=1)
    assert solo_uno["diferencia"] < 0 and solo_uno["ic_sup"] >= 0
    assert validation.block_bootstrap_diff(y, bueno, malo, bloques, n_boot=500, seed=1) == uniforme       # determinista


def _evaluacion(y, oof, bloques=None):
    nombres = list(oof)
    return validation.Evaluation(nombres, np.asarray(y, float), {k: np.asarray(v, float) for k, v in oof.items()},
                                 np.repeat(np.arange(len(y) // 5), 5) if bloques is None else bloques,
                                 pd.DataFrame(), 5)


def test_decide_publica_solo_si_el_intervalo_queda_por_debajo_de_cero():
    y = np.tile([0.0, 1.0, 2.0, 3.0, 4.0], 20)
    ev = _evaluacion(y, {"media": [np.full(100, 2.3)], "solo_distancia": [np.full(100, 2.2)], "solo_poblacion": [np.full(100, 2.4)],
                         "solo_densidad": [np.full(100, 2.0)], "boosting": [y + 0.05], "mlp": [np.full(100, 2.0)]})
    d = validation.decide(ev, n_boot=300)
    assert d["mejor_baseline"] == "solo_densidad" and d["ganador"] == "boosting"
    assert d["comparaciones"]["boosting"]["veredicto"] == "mejora"
    assert d["comparaciones"]["mlp"]["veredicto"] == "indistinguible" and d["comparaciones"]["mlp"]["diferencia"] == 0.0


def test_decide_sin_mejora_clara_no_hay_ganador_y_marca_al_que_empeora():
    y = np.tile([0.0, 1.0, 2.0, 3.0, 4.0], 20)
    base = np.full(100, 2.0)
    ev = _evaluacion(y, {"media": [base], "solo_distancia": [base], "solo_poblacion": [base], "solo_densidad": [base],
                         "boosting": [base], "mlp": [np.full(100, 0.2)]})
    d = validation.decide(ev, n_boot=300)
    assert d["ganador"] is None and d["comparaciones"]["boosting"]["veredicto"] == "indistinguible"
    assert d["comparaciones"]["mlp"]["veredicto"] == "peor"


def test_decide_no_depende_de_cuantas_repeticiones_se_promedien():
    """Regresión: antes se promediaban las predicciones entre repeticiones y DESPUÉS se calculaba la desviación. Un
    candidato muy inestable (cada repetición falla mucho, pero en promedio acierta) salía como 'mejora' solo por ser
    un conjunto de modelos, y el veredicto cambiaba con el número de repeticiones."""
    y = np.tile([1.0, 2.0, 3.0, 4.0, 5.0], 20)
    inestable = np.stack([y * 1.9, y * 0.1] * 3)                      # cada repetición es mala; su media es y (perfecta)
    razonable = np.stack([y * 1.2] * 6)
    ev = _evaluacion(y, {"media": razonable, "solo_distancia": razonable, "solo_poblacion": razonable,
                         "solo_densidad": razonable, "boosting": inestable, "mlp": razonable})
    d = validation.decide(ev, n_boot=300)
    assert d["comparaciones"]["boosting"]["veredicto"] != "mejora" and d["ganador"] is None


def test_la_brecha_relativa_no_premia_solo_a_las_celdas_grandes():
    esperado, observado = np.array([75.0, 7.0]), np.array([18.0, 0.0])
    absoluta = esperado - observado
    relativa = validation.brecha_relativa(esperado, observado)
    assert absoluta[0] > 8 * absoluta[1]                                 # en bruto, la celda grande parece 8 veces mejor
    assert relativa[0] == pytest.approx(57 / np.sqrt(76)) and relativa[0] < 3 * relativa[1]
    assert validation.brecha_relativa([4.0], [4.0])[0] == 0.0


def test_auc_y_artefacto_de_cartografia():
    score = np.array([0.1, 0.2, 0.8, 0.9])
    assert validation.auc_presence(score, [0, 0, 1, 1]) == 1.0
    assert validation.auc_presence(score, [1, 1, 1, 1]) != validation.auc_presence(score, [1, 1, 1, 1])      # NaN
    brecha = np.array([9.0, 8.0, 1.0, 0.0])
    r = validation.gap_artifact_share(brecha, osm=[0, 2, 1, 0], fsq=[3, 0, 2, 0], k=2)
    assert r["top_k"] == 0.5 and r["referencia"] == pytest.approx(2 / 3)    # celdas con locales: 3; fsq>osm en 2


# ---------------------------------------------------------------------------
# Herramienta
# ---------------------------------------------------------------------------

def test_conteos_de_foursquare_por_celda():
    f, c = 20, 20
    lat, lon = grid.cell_center(f, c)
    fsq = pd.DataFrame({"category": ["restaurant", "restaurant", "retail", "restaurant"], "latitude": [lat, lat, lat, 40.0],
                        "longitude": [lon, lon, lon, lon]})
    index = pd.Index([grid.cell_id(20, 20), grid.cell_id(5, 5)])
    np.testing.assert_array_equal(vlm.fsq_cell_counts(fsq, ("restaurant",), index), [2, 0])
    np.testing.assert_array_equal(vlm.fsq_cell_counts(fsq, ("retail", "restaurant"), index), [3, 0])


def test_zona_mas_cercana():
    f, c = (int(x[0]) for x in grid.cell_index(LOCATIONS["Valletta"].latitude, LOCATIONS["Valletta"].longitude))
    assert vlm.zona_mas_cercana(f, c) == "Valletta"


def _db_para_la_herramienta(tmp_path):
    db = tmp_path / "t.db"
    rng = np.random.default_rng(0)
    pois, fsq = [], []
    for _ in range(900):
        f, c = int(rng.integers(12, 34)), int(rng.integers(10, 32))
        lat, lon = grid.cell_center(f, c)
        cat, sub = [("food_drink", "cafe"), ("business", "bakery"), ("school", "school"), ("sport", "sports_centre"),
                    ("business", "company")][int(rng.integers(0, 5))]
        pois.append((cat, sub, float(lat), float(lon)))
        if cat == "food_drink" and rng.random() < 0.4:
            fsq.append(("restaurant", "x", "R", float(lat), float(lon)))
    crear_db(db, pois=pois, foursquare=fsq, poblacion={z: 5000 + 1000 * i for i, z in enumerate(LOCATIONS)},
             rutas=[(o, d, 8.0 + i) for i, (o, d) in enumerate([("Msida", "Gzira"), ("Gzira", "Sliema"), ("Valletta", "Msida")])])
    return db


def test_la_herramienta_valida_un_objetivo_de_punta_a_punta(tmp_path, capsys):
    db = _db_para_la_herramienta(tmp_path)
    antes = db.read_bytes()
    assert vlm.main(["--db", str(db), "--target", "food_drink", "--repeats", "2", "--folds", "3", "--boot", "50"]) == 0
    salida = capsys.readouterr().out
    assert "Restaurante, café o bar (food_drink)" in salida and "Mejor línea base" in salida and "DECISIÓN" in salida
    assert "Contraste con Foursquare" in salida and "brecha absoluta" in salida and "brecha RELATIVA" in salida
    assert db.read_bytes() == antes and [p.name for p in tmp_path.iterdir()] == ["t.db"]


def test_run_target_devuelve_todo_lo_necesario(tmp_path):
    db = _db_para_la_herramienta(tmp_path)
    from src.ml.cell_counts import CellCounts
    r = vlm.run_target("business", CellCounts.from_pois(data_access.load_pois(db)), data_access.load_zone_table(db),
                       data_access.load_pois_foursquare(db), repeats=2, n_folds=3, n_boot=50, seed=0, k_top=10)
    assert len(r["esperado"]) == len(r["y"]) == len(r["brecha"]) == len(r["X"])
    assert r["modelo_brecha"] in models.CANDIDATOS and set(r["resumen"].index) == set(models.TODOS)
    np.testing.assert_allclose(r["brecha"], r["esperado"] - r["y"])
    assert r["decision"]["mejor_baseline"] in models.BASELINES


def test_la_herramienta_sin_foursquare_no_hace_el_contraste(tmp_path, capsys):
    db = tmp_path / "t.db"
    lat, lon = grid.cell_center(20, 20)
    pois = [("food_drink", "cafe", float(lat), float(lon))] * 3 + [("school", "school", float(lat), float(lon))] * 3
    rng = np.random.default_rng(1)
    for _ in range(400):
        f, c = int(rng.integers(12, 34)), int(rng.integers(10, 32))
        la, lo = grid.cell_center(f, c)
        pois.append((["food_drink", "school", "sport"][int(rng.integers(0, 3))], "x", float(la), float(lo)))
    crear_db(db, pois=pois, poblacion={z: 5000 for z in LOCATIONS})
    assert vlm.main(["--db", str(db), "--target", "food_drink", "--repeats", "2", "--folds", "3", "--boot", "30"]) == 0
    assert "sin datos de Foursquare" in capsys.readouterr().out
