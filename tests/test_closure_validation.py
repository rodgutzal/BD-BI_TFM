"""Tests de la validación del estudio de riesgo de cierre (fase 4, protocolo 3.M de docs/DISENO_ML_RECOMENDACION.md).

Datos sintéticos: cada test fija una regla del protocolo (modelos fijados, líneas base que solo usan sus variables, validación
espacial por bloques con el patrón de semillas de la fase 1, AUC por repetición y luego promedio, remuestreo de bloques,
intervalos del 97,5 %, mejor línea base elegida una vez, regla de decisión con desigualdades estrictas).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import closure_features as cf  # noqa: E402
from src.ml import closure_validation as cv  # noqa: E402
from src.ml import grid, validation  # noqa: E402


def datos(n=400, semilla=0, efecto_densidad=0.0, efecto_categoria=0.0, efecto_distancia=0.0, efecto_cadena=0.0):
    """Locales sintéticos repartidos por la rejilla con variables coherentes con el protocolo y una etiqueta con señal opcional."""
    rng = np.random.default_rng(semilla)
    filas = rng.integers(8, grid.N_ROWS - 8, n)
    cols = rng.integers(8, grid.N_COLS - 8, n)
    categoria = rng.integers(0, len(cf.CATEGORIAS), n)
    X = pd.DataFrame(0.0, index=range(n), columns=list(cf.COLUMNAS))
    for i, c in enumerate(cf.COLUMNAS_CATEGORIA):
        X[c] = (categoria == i).astype(float)
    X["n_total_250"] = rng.poisson(4, n).astype(float)
    X["n_misma_250"] = np.minimum(rng.poisson(1, n), X["n_total_250"]).astype(float)
    X["n_total_500"] = X["n_total_250"] + rng.poisson(8, n)
    X["n_misma_500"] = np.minimum(X["n_misma_250"] + rng.poisson(2, n), X["n_total_500"]).astype(float)
    X["dist_misma_m"] = rng.uniform(10, 1000, n)
    X["cadena"] = (rng.random(n) < 0.1).astype(float)
    z = (
        -1.0
        + efecto_densidad * (X["n_total_500"] - X["n_total_500"].mean()) / X["n_total_500"].std()
        + efecto_categoria * (categoria % 2)
        + efecto_distancia * (X["dist_misma_m"] - X["dist_misma_m"].mean()) / X["dist_misma_m"].std()
        + efecto_cadena * X["cadena"]
    )
    y = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)
    return X, y, filas, cols


# ---- constantes del protocolo --------------------------------------------------------------------------------------------------
def test_los_parametros_fijados_son_los_del_protocolo():
    assert (cv.N_REPETICIONES, cv.N_PLIEGUES, cv.N_REMUESTREOS, cv.NIVEL, cv.SEMILLA) == (10, 5, 2000, 0.975, 0)
    assert cv.MIN_POSITIVOS_DESCRIPTIVOS == 30
    assert cv.CANDIDATOS == ("logistica", "boosting") and cv.LINEAS_BASE == ("solo_categoria", "solo_densidad")
    assert cv.PARAMETROS_LOGISTICA == {"C": 1.0, "max_iter": 2000}  # sin `penalty` (deprecado en scikit-learn 1.8)
    assert cv.PARAMETROS_BOOSTING == {
        "n_estimators": 150,
        "max_depth": 2,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "min_samples_leaf": 10,
    }


# ---- modelos ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("modelo", cv.MODELOS)
def test_cada_modelo_da_probabilidades_validas_y_deterministas(modelo):
    X, y, *_ = datos()
    p1 = cv.ajustar_predecir(modelo, X.iloc[:300], y[:300], X.iloc[300:], semilla=3)
    p2 = cv.ajustar_predecir(modelo, X.iloc[:300], y[:300], X.iloc[300:], semilla=3)
    assert p1.shape == (100,) and ((p1 >= 0) & (p1 <= 1)).all() and np.array_equal(p1, p2)


def test_un_modelo_desconocido_es_un_error():
    X, y, *_ = datos(50)
    with pytest.raises(ValueError, match="Modelo desconocido"):
        cv.ajustar_predecir("magia", X, y, X, 0)


def test_la_logistica_es_la_del_protocolo_con_las_cinco_numericas_estandarizadas():
    """Reproduce a mano: estandarizar las 5 numéricas (no la cadena ni las categorías), L2 por defecto, C=1, max_iter=2000."""
    X, y, *_ = datos()
    ent, prueba = X.iloc[:300], X.iloc[300:]
    escala = StandardScaler().fit(ent[list(cf.COLUMNAS_NUMERICAS)])
    resto = list(cf.COLUMNAS_CATEGORIA) + [cf.COLUMNA_CADENA]
    Z_e = np.hstack([escala.transform(ent[list(cf.COLUMNAS_NUMERICAS)]), ent[resto].to_numpy()])
    Z_p = np.hstack([escala.transform(prueba[list(cf.COLUMNAS_NUMERICAS)]), prueba[resto].to_numpy()])
    esperada = LogisticRegression(C=1.0, max_iter=2000).fit(Z_e, y[:300]).predict_proba(Z_p)[:, 1]
    assert np.allclose(cv.ajustar_predecir("logistica", ent, y[:300], prueba, 0), esperada)


def test_la_logistica_no_depende_de_la_escala_de_las_numericas_porque_las_estandariza():
    X, y, *_ = datos()
    grande = X.copy()
    grande[list(cf.COLUMNAS_NUMERICAS)] = grande[list(cf.COLUMNAS_NUMERICAS)] * 1000
    a = cv.ajustar_predecir("logistica", X.iloc[:300], y[:300], X.iloc[300:], 0)
    b = cv.ajustar_predecir("logistica", grande.iloc[:300], y[:300], grande.iloc[300:], 0)
    assert np.allclose(a, b, atol=1e-8)


def test_el_boosting_usa_los_hiperparametros_fijados_y_la_semilla_de_la_repeticion(monkeypatch):
    X, y, *_ = datos()
    capturado = {}
    original = GradientBoostingClassifier

    class Espia(original):
        def __init__(self, **kwargs):
            capturado.update(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(cv, "GradientBoostingClassifier", Espia)
    cv.ajustar_predecir("boosting", X.iloc[:300], y[:300], X.iloc[300:], semilla=7)
    assert capturado == {**cv.PARAMETROS_BOOSTING, "random_state": 7}


def test_solo_categoria_usa_la_tasa_de_cierre_de_cada_categoria_del_entrenamiento():
    X = pd.DataFrame(0.0, index=range(8), columns=list(cf.COLUMNAS))
    X.loc[[0, 1, 2, 3], "cat_school"] = 1.0
    X.loc[[4, 5, 6, 7], "cat_business"] = 1.0
    y = np.array([1, 1, 0, 0, 1, 0, 0, 0])
    prueba = pd.DataFrame(0.0, index=range(3), columns=list(cf.COLUMNAS))
    prueba.loc[0, "cat_school"] = 1.0
    prueba.loc[1, "cat_business"] = 1.0
    prueba.loc[2, "cat_sport"] = 1.0  # categoría que no está en el entrenamiento
    p = cv.ajustar_predecir("solo_categoria", X, y, prueba, 0)
    assert np.allclose(p, [0.5, 0.25, 3 / 8])  # 2/4, 1/4 y la tasa global (3/8) para la categoría no vista


def test_solo_categoria_ignora_el_resto_de_variables():
    X, y, *_ = datos()
    otra = X.copy()
    for c in list(cf.COLUMNAS_NUMERICAS) + [cf.COLUMNA_CADENA]:
        otra[c] = np.random.default_rng(1).permutation(otra[c].to_numpy())
    a = cv.ajustar_predecir("solo_categoria", X.iloc[:300], y[:300], X.iloc[300:], 0)
    b = cv.ajustar_predecir("solo_categoria", otra.iloc[:300], y[:300], otra.iloc[300:], 0)
    assert np.array_equal(a, b)


def test_solo_densidad_usa_solo_los_cuatro_recuentos_con_log_1_mas_n():
    X, y, *_ = datos()
    otra = X.copy()
    for c in list(cf.COLUMNAS_CATEGORIA) + ["dist_misma_m", cf.COLUMNA_CADENA]:
        otra[c] = np.random.default_rng(2).permutation(otra[c].to_numpy())
    a = cv.ajustar_predecir("solo_densidad", X.iloc[:300], y[:300], X.iloc[300:], 0)
    b = cv.ajustar_predecir("solo_densidad", otra.iloc[:300], y[:300], otra.iloc[300:], 0)
    assert np.array_equal(a, b)
    logs = np.log1p(X[list(cf.COLUMNAS_DENSIDAD)].to_numpy())
    escala = StandardScaler().fit(logs[:300])
    esperada = (
        LogisticRegression(C=1.0, max_iter=2000)
        .fit(escala.transform(logs[:300]), y[:300])
        .predict_proba(escala.transform(logs[300:]))[:, 1]
    )
    assert np.allclose(a, esperada)


def test_la_logistica_y_el_boosting_si_usan_todas_las_variables():
    """Con señal en TODAS las variables, cambiar cualquiera de ellas cambia las predicciones de los dos candidatos."""
    X, y, *_ = datos(1200, efecto_densidad=1.0, efecto_categoria=1.0, efecto_distancia=1.0, efecto_cadena=2.0)
    # Invertir el orden de una columna rompe su relación con la etiqueta (sumar una constante no: la estandarización la absorbe).
    columnas = ["cat_school", "n_total_250", "n_misma_250", "n_total_500", "n_misma_500", "dist_misma_m", "cadena"]
    for modelo in ("logistica", "boosting"):
        base = cv.ajustar_predecir(modelo, X.iloc[:900], y[:900], X.iloc[900:], 0)
        for columna in columnas:
            otra = X.copy()
            otra[columna] = otra[columna].to_numpy()[::-1]
            cambiada = cv.ajustar_predecir(modelo, otra.iloc[:900], y[:900], otra.iloc[900:], 0)
            assert not np.array_equal(base, cambiada), f"{modelo} ignora {columna}"


# ---- validación espacial por bloques ---------------------------------------------------------------------------------------
def test_la_validacion_es_espacial_con_el_patron_de_semillas_de_la_fase_1(monkeypatch):
    """En cada repetición `r`: `default_rng(semilla + r)`, dos desplazamientos `integers(0, 4)` y el mismo `rng` para los
    pliegues. Ningún bloque (de la cuadrícula desplazada) tiene locales en entrenamiento y en prueba a la vez, y cada local se
    predice exactamente una vez por repetición."""
    X, y, filas, cols = datos(300)
    llamadas = []
    monkeypatch.setattr(
        cv,
        "ajustar_predecir",
        lambda nombre, Xe, ye, Xp, semilla: llamadas.append((nombre, list(Xe.index), list(Xp.index), semilla))
        or np.full(len(Xp), 0.3),
    )
    cv.validar(X, y, filas, cols, nombres=("logistica",), repeticiones=3, pliegues=5, semilla=10)
    assert len(llamadas) == 3 * 5
    for r in range(3):
        rng = np.random.default_rng(10 + r)
        desplazamiento = (int(rng.integers(0, 4)), int(rng.integers(0, 4)))
        etiquetas = validation.block_labels(filas, cols, desplazamiento)
        pliegue_de = validation.assign_folds(etiquetas, 5, rng)
        de_la_repeticion = llamadas[r * 5 : (r + 1) * 5]
        pruebas = [set(p) for _, _, p, _ in de_la_repeticion]
        assert sum(len(p) for p in pruebas) == len(y) and set().union(*pruebas) == set(
            range(len(y))
        )  # cada local una vez
        for (_, ent, prueba, semilla), f in zip(de_la_repeticion, range(5)):
            assert semilla == 10 + r
            assert set(prueba) == set(np.flatnonzero(pliegue_de == f))
            assert not (set(etiquetas[ent]) & set(etiquetas[prueba]))  # ningún bloque en los dos lados


def test_validar_devuelve_una_matriz_por_modelo_sin_huecos_y_es_determinista():
    X, y, filas, cols = datos(300, efecto_densidad=1.0)
    a = cv.validar(X, y, filas, cols, repeticiones=2)
    b = cv.validar(X, y, filas, cols, repeticiones=2)
    assert set(a) == set(cv.MODELOS)
    for n in cv.MODELOS:
        assert a[n].shape == (2, 300) and not np.isnan(a[n]).any() and np.array_equal(a[n], b[n])


def test_validar_se_niega_ante_longitudes_distintas_o_un_entrenamiento_de_una_clase():
    X, y, filas, cols = datos(100)
    with pytest.raises(ValueError, match="longitudes distintas"):
        cv.validar(X, y[:50], filas, cols)
    with pytest.raises(ValueError, match="una sola clase"):
        cv.validar(X, np.zeros(100, dtype=int), filas, cols, repeticiones=1)


# ---- AUC por repetición y después promedio -------------------------------------------------------------------------------------
def test_auc_por_filas_coincide_con_scikit_learn_incluso_con_empates():
    rng = np.random.default_rng(0)
    y = (rng.random(200) < 0.3).astype(int)
    P = np.round(rng.random((4, 200)), 1)  # muchos empates
    esperado = [roc_auc_score(y, fila) for fila in P]
    assert np.allclose(cv.auc_por_filas(y, P), esperado)


def test_auc_con_una_sola_clase_es_nan():
    assert np.isnan(cv.auc_por_filas(np.zeros(5, dtype=int), np.random.rand(2, 5))).all()
    assert np.isnan(cv.auc_por_filas(np.ones(5, dtype=int), np.random.rand(2, 5))).all()


def test_el_auc_se_calcula_por_repeticion_y_despues_se_promedia_no_se_promedian_las_predicciones():
    """Dos repeticiones que se ordenan en sentidos opuestos: el promedio de AUC es 0,5 solo si cada AUC es 1 y 0; promediando
    las predicciones saldría otra cosa (aquí 0,5 también, pero con empates): se comprueba contra el cálculo por repetición.
    """
    y = np.array([0, 0, 1, 1])
    P = np.array([[0.1, 0.2, 0.8, 0.9], [0.9, 0.2, 0.3, 0.1]])
    por_repeticion = np.mean([roc_auc_score(y, P[0]), roc_auc_score(y, P[1])])
    assert cv.auc_medio(y, P) == pytest.approx(por_repeticion)
    assert cv.auc_medio(y, P) != pytest.approx(
        roc_auc_score(y, P.mean(axis=0))
    )  # distinto de promediar las predicciones


# ---- remuestreo de bloques e intervalos -----------------------------------------------------------------------------------------
def test_el_remuestreo_es_de_bloques_enteros_y_descarta_las_replicas_de_una_sola_clase():
    """Un único bloque contiene todos los positivos: las réplicas que no lo eligen tienen una sola clase y se descartan. Si se
    remuestrearan locales sueltos casi nunca pasaría."""
    n_bloques = 10
    bloques = np.repeat(np.arange(n_bloques), 20)
    y = (bloques == 0).astype(int)
    oof = {"m": np.random.default_rng(0).random((2, len(y)))}
    replicas, descartadas = cv.remuestrear_por_bloques(y, oof, bloques, n_remuestreos=400, semilla=0)
    esperado_sin_el_bloque_0 = 0.9**10  # prob. de no elegir el bloque 0 en 10 sorteos
    assert 0.15 < descartadas / 400 < 0.6 and abs(descartadas / 400 - esperado_sin_el_bloque_0) < 0.1
    assert len(replicas["m"]) == 400 - descartadas and not np.isnan(replicas["m"]).any()


def test_el_remuestreo_usa_los_bloques_de_la_cuadricula_sin_desplazar_y_es_reproducible():
    X, y, filas, cols = datos(200, efecto_densidad=1.5)
    oof = cv.validar(X, y, filas, cols, nombres=("logistica",), repeticiones=2)
    bloques = validation.block_labels(filas, cols)  # sin desplazar
    a, _ = cv.remuestrear_por_bloques(y, oof, bloques, 50, semilla=0)
    b, _ = cv.remuestrear_por_bloques(y, oof, bloques, 50, semilla=0)
    c, _ = cv.remuestrear_por_bloques(y, oof, bloques, 50, semilla=1)
    assert np.array_equal(a["logistica"], b["logistica"]) and not np.array_equal(a["logistica"], c["logistica"])


def test_el_intervalo_es_del_97_5_por_ciento_percentiles_1_25_y_98_75():
    valores = np.arange(0, 1001, dtype=float)
    bajo, alto = cv.intervalo(valores)
    assert bajo == pytest.approx(12.5) and alto == pytest.approx(987.5)
    bajo95, alto95 = cv.intervalo(valores, nivel=0.95)
    assert (bajo95, alto95) == (pytest.approx(25.0), pytest.approx(975.0))


# ---- mejor línea base y decisión -------------------------------------------------------------------------------------------------
def test_la_mejor_linea_base_es_la_de_mayor_auc_medio_y_en_empate_la_de_categoria():
    y = np.array([0, 0, 1, 1])
    buena, mala = np.array([[0.1, 0.2, 0.8, 0.9]]), np.array([[0.9, 0.2, 0.3, 0.1]])
    assert cv.mejor_linea_base(y, {"solo_categoria": buena, "solo_densidad": mala}) == "solo_categoria"
    assert cv.mejor_linea_base(y, {"solo_categoria": mala, "solo_densidad": buena}) == "solo_densidad"
    assert cv.mejor_linea_base(y, {"solo_categoria": buena, "solo_densidad": buena}) == "solo_categoria"


@pytest.mark.parametrize(
    "inf_auc, inf_dif, a, b",
    [
        (0.51, 0.01, True, True),
        (0.51, 0.0, True, False),
        (0.5, 0.01, False, True),
        (0.5, 0.0, False, False),
        (0.49, 0.2, False, True),
        (0.9, -0.01, True, False),
    ],
)
def test_la_decision_exige_limites_inferiores_estrictamente_mayores(inf_auc, inf_dif, a, b):
    """(a) límite inferior del AUC > 0,5 y (b) límite inferior de la diferencia > 0; la igualdad NO cumple."""
    auc = {c: {"ic": [inf_auc, 0.9]} for c in cv.CANDIDATOS}
    dif = {c: {"ic": [inf_dif, 0.2]} for c in cv.CANDIDATOS}
    d = cv.decidir(auc, dif)
    assert all(v == {"a": a, "b": b, "cumple": a and b} for v in d.values())


def test_basta_con_que_un_candidato_cumpla_ambas_condiciones():
    auc = {"logistica": {"ic": [0.6, 0.7]}, "boosting": {"ic": [0.4, 0.7]}}
    dif = {"logistica": {"ic": [0.01, 0.1]}, "boosting": {"ic": [0.01, 0.1]}}
    d = cv.decidir(auc, dif)
    assert d["logistica"]["cumple"] and not d["boosting"]["cumple"]


# ---- evaluación completa -----------------------------------------------------------------------------------------------------------
def test_con_una_senal_que_las_lineas_base_no_explican_el_resultado_es_utilizable():
    """La señal está en la distancia a la competencia de la misma categoría, que ninguna línea base trivial usa."""
    X, y, filas, cols = datos(900, semilla=1, efecto_distancia=1.5)
    r = cv.evaluar(X, y, filas, cols, repeticiones=3, n_remuestreos=150)
    assert r["utilizable"] and r["auc"]["logistica"]["ic"][0] > 0.5
    assert r["decision"]["logistica"] == {"a": True, "b": True, "cumple": True}
    assert r["n"] == 900 and r["positivos"] == int(y.sum()) and r["bloques"] > 10
    assert set(r["auc"]) == set(cv.MODELOS) and set(r["decision"]) == set(cv.CANDIDATOS)
    assert r["remuestreos"] == {"pedidos": 150, "descartados_por_una_sola_clase": 0}


def test_sin_senal_no_es_utilizable():
    X, y, filas, cols = datos(700, semilla=2)
    r = cv.evaluar(X, y, filas, cols, repeticiones=3, n_remuestreos=150)
    assert not r["utilizable"]


def test_una_senal_que_ya_explica_la_categoria_no_basta_porque_hay_que_mejorar_la_linea_base_trivial():
    """El AUC supera 0,5 (condición a) pero un modelo con todas las variables no mejora a la tasa por categoría (condición b):
    es el caso que motivó añadir (b) al protocolo."""
    X, y, filas, cols = datos(900, semilla=3, efecto_categoria=2.5)
    r = cv.evaluar(X, y, filas, cols, repeticiones=3, n_remuestreos=150)
    assert r["mejor_linea_base"] == "solo_categoria"
    assert r["auc"]["logistica"]["ic"][0] > 0.5  # (a) se cumple
    assert not r["decision"]["logistica"]["b"] and not r["utilizable"]  # (b) no


def test_una_senal_que_ya_explica_la_densidad_tampoco_basta():
    """Mismo caso con la línea base de densidad: la señal está en el recuento a 500 m, que esa base ya usa."""
    X, y, filas, cols = datos(900, semilla=5, efecto_densidad=2.0)
    r = cv.evaluar(X, y, filas, cols, repeticiones=3, n_remuestreos=150)
    assert r["mejor_linea_base"] == "solo_densidad"
    assert r["auc"]["logistica"]["ic"][0] > 0.5 and not r["decision"]["logistica"]["b"] and not r["utilizable"]


def test_la_diferencia_es_pareada_con_el_mismo_remuestreo_y_la_media_es_la_de_los_datos():
    X, y, filas, cols = datos(400, semilla=4, efecto_densidad=1.0)
    r = cv.evaluar(X, y, filas, cols, repeticiones=2, n_remuestreos=100)
    mejor = r["mejor_linea_base"]
    for c in cv.CANDIDATOS:
        assert r["diferencia_con_la_mejor_linea_base"][c]["media"] == pytest.approx(
            r["auc"][c]["media"] - r["auc"][mejor]["media"]
        )


def test_el_resultado_no_contiene_ningun_dato_por_local():
    X, y, filas, cols = datos(300)
    r = cv.evaluar(X, y, filas, cols, repeticiones=2, n_remuestreos=50)

    def hojas(o):
        if isinstance(o, dict):
            for v in o.values():
                yield from hojas(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                yield from hojas(v)
        else:
            yield o

    assert len(list(hojas(r))) < 100  # solo agregados: un puñado de números, no una fila por local


def test_tasa_por_categoria():
    poblacion = pd.DataFrame({"categoria": ["school", "school", "school", "business", "business"]})
    t = {f["categoria"]: f for f in cv.tasa_por_categoria(poblacion, [1, 0, 0, 1, 1])}
    assert (t["school"]["locales"], t["school"]["cierres"]) == (3, 1) and t["school"]["tasa"] == pytest.approx(1 / 3)
    assert t["business"]["tasa"] == 1.0 and t["sport"] == {
        "categoria": "sport",
        "locales": 0,
        "cierres": 0,
        "tasa": None,
    }


# ---- orquestación de `evaluar`: lo que las mutaciones mostraron sin cubrir ---------------------------------------------------
def _stub_validar(monkeypatch, n):
    rng = np.random.default_rng(0)
    monkeypatch.setattr(cv, "validar", lambda *a, **k: {m: rng.random((2, n)) for m in cv.MODELOS})


def test_evaluar_es_utilizable_si_basta_con_un_candidato(monkeypatch):
    """La regla fijada es «al menos un candidato»: con solo uno cumpliendo, el resultado es utilizable."""
    X, y, filas, cols = datos(200)
    monkeypatch.setattr(
        cv,
        "decidir",
        lambda auc, dif: {
            "logistica": {"a": True, "b": True, "cumple": True},
            "boosting": {"a": True, "b": False, "cumple": False},
        },
    )
    assert cv.evaluar(X, y, filas, cols, repeticiones=2, n_remuestreos=20)["utilizable"] is True
    monkeypatch.setattr(
        cv,
        "decidir",
        lambda auc, dif: {c: {"a": True, "b": False, "cumple": False} for c in cv.CANDIDATOS},
    )
    assert cv.evaluar(X, y, filas, cols, repeticiones=2, n_remuestreos=20)["utilizable"] is False


def test_evaluar_remuestrea_los_bloques_de_la_cuadricula_sin_desplazar(monkeypatch):
    X, y, filas, cols = datos(200)
    vistos = {}
    real = cv.remuestrear_por_bloques

    def espia(y_, oof, bloques, n_remuestreos, semilla):
        vistos["bloques"] = np.asarray(bloques)
        vistos["semilla"] = semilla
        return real(y_, oof, bloques, n_remuestreos, semilla)

    monkeypatch.setattr(cv, "remuestrear_por_bloques", espia)
    r = cv.evaluar(X, y, filas, cols, repeticiones=2, n_remuestreos=20, semilla=0)
    assert np.array_equal(vistos["bloques"], validation.block_labels(filas, cols)) and vistos["semilla"] == 0
    assert r["bloques"] == len(np.unique(validation.block_labels(filas, cols)))


def test_la_diferencia_con_la_mejor_linea_base_se_calcula_replica_a_replica(monkeypatch):
    """Pareada: si el candidato es siempre la base + 0,1 en cada réplica, la diferencia es 0,1 en TODAS (intervalo degenerado).
    Emparejar mal las réplicas (o remuestrear aparte) daría un intervalo ancho."""
    X, y, filas, cols = datos(200)
    _stub_validar(monkeypatch, len(y))
    base = np.random.default_rng(1).uniform(0.4, 0.6, 50)
    replicas = {"solo_categoria": base, "solo_densidad": base - 0.2, "logistica": base + 0.1, "boosting": base + 0.1}
    monkeypatch.setattr(cv, "remuestrear_por_bloques", lambda *a, **k: (replicas, 0))
    monkeypatch.setattr(cv, "mejor_linea_base", lambda y_, oof: "solo_categoria")
    r = cv.evaluar(X, y, filas, cols, repeticiones=2, n_remuestreos=50)
    for c in cv.CANDIDATOS:
        assert r["diferencia_con_la_mejor_linea_base"][c]["ic"] == [pytest.approx(0.1), pytest.approx(0.1)]
