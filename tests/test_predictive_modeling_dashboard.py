"""Pruebas de la preparación de datos del dashboard de modelado predictivo.

Regresión: con datos reales, unas pocas filas (OpenWeather falló en ese ciclo)
tienen el clima en NULL, y una sola basta para que `LogisticRegression` lance
`Input X contains NaN`. Esa excepción cortaba toda la vista Analyst.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamlit_app.dashboards import predictive_modeling_dashboard as pm


def _datos(n=240, filas_sin_clima=(3, 50, 51), seed=0):
    rng = np.random.default_rng(seed)
    descripciones = ["clear sky", "few clouds", "broken clouds", "light rain", "mist"]
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-09-01", periods=n, freq="h", tz="UTC"),
            "origin": np.where(np.arange(n) % 2 == 0, "Msida", "Valletta"),
            "destination": np.where(np.arange(n) % 2 == 0, "Gzira", "Sliema"),
            "data_source": np.where(np.arange(n) % 3 == 0, "tomtom", "ors"),
            "distance_km": np.where(np.arange(n) % 2 == 0, 2.0, 4.0),
            "origin_temperature": rng.uniform(15, 30, n),
            "origin_humidity": rng.uniform(40, 90, n),
            "destination_temperature": rng.uniform(15, 30, n),
            "destination_humidity": rng.uniform(40, 90, n),
            "origin_weather": [descripciones[i % 5] for i in range(n)],
            "destination_weather": [descripciones[(i + 1) % 5] for i in range(n)],
            "travel_time_min": rng.uniform(5, 30, n),
            "average_speed_kmh": rng.uniform(20, 50, n),
        }
    )
    df["mobility_level"] = np.where(df["travel_time_min"] > 20, "Alta demora", "Movilidad normal")
    for i in filas_sin_clima:  # OpenWeather no respondió en ese ciclo
        df.loc[i, ["origin_temperature", "origin_humidity", "origin_weather"]] = np.nan
    return df


def test_clima_ausente_no_se_convierte_en_lluvia():
    """Una fila sin clima queda como NaN en el grupo de clima, no como «lluvia»."""
    d = pm._engineer_features(_datos())
    assert d.loc[3, "origin_weather_grp"] != d.loc[3, "origin_weather_grp"]  # NaN, no "lluvia"
    assert d["origin_weather_grp"].isna().sum() == 3


def test_descripciones_conocidas_y_desconocidas_se_agrupan_como_antes():
    """Las descripciones de clima conocidas y las desconocidas se agrupan igual que antes del cambio."""
    d = pm._engineer_features(_datos(filas_sin_clima=()))
    por_desc = d.groupby("origin_weather")["origin_weather_grp"].first()
    assert por_desc["clear sky"] == "despejado"
    assert por_desc["few clouds"] == "parcialmente_nublado"
    assert por_desc["broken clouds"] == "nublado"
    assert por_desc["light rain"] == "lluvia"  # no está en WEATHER_GROUPS
    assert por_desc["mist"] == "lluvia"


def test_complete_cases_excluye_solo_las_filas_sin_clima():
    """`_complete_cases` descarta solo las filas sin clima y no modifica el DataFrame original."""
    d = pm._engineer_features(_datos(n=240, filas_sin_clima=(3, 50, 51)))
    limpio = pm._complete_cases(d)
    assert len(limpio) == 237
    assert limpio[pm.MODEL_FEATURE_COLS].notna().all().all()
    # el dato original no se muta: las 3 filas siguen en d (las usan forecast y clustering)
    assert len(d) == 240


def test_sin_filas_incompletas_no_se_pierde_nada():
    """Si no hay filas incompletas, `_complete_cases` conserva todas."""
    d = pm._engineer_features(_datos(filas_sin_clima=()))
    assert len(pm._complete_cases(d)) == len(d)


def test_regresion_no_falla_con_filas_sin_clima():
    """La regresión se ajusta sin fallar aunque haya filas sin clima."""
    d = pm._engineer_features(_datos())
    res = pm._fit_regression(d)
    assert res is not None


def test_clasificacion_no_falla_con_filas_sin_clima():
    """El caso exacto del bug: 'Input X contains NaN' en LogisticRegression."""
    d = pm._engineer_features(_datos())
    res = pm._fit_classification(d)
    assert res is not None


def test_el_temporal_y_el_clustering_conservan_las_filas_sin_clima():
    """Su tiempo de viaje es válido: no deben pasar por _complete_cases."""
    d = pm._engineer_features(_datos())
    res = pm._fit_clustering(d, 2)
    assert res["agg"]["n"].sum() == len(d)  # contó las 240 filas, no 237


def _ultimas(d, n_test):
    """Las `n_test` filas completas más recientes, ordenadas por fecha."""
    return pm._complete_cases(d).sort_values("timestamp").tail(n_test)


def test_la_particion_cronologica_entrena_con_lo_antiguo_y_evalua_con_lo_reciente():
    """El 80 % más antiguo entrena y el 20 % más reciente evalúa, aunque las filas lleguen desordenadas."""
    d = pm._engineer_features(_datos(filas_sin_clima=())).sample(frac=1, random_state=1)  # barajado
    ordenado, es_entrenamiento = pm._particion_cronologica(d)
    assert es_entrenamiento.sum() == 192 and (~es_entrenamiento).sum() == 48  # 240 filas: 80 % / 20 %
    assert ordenado["timestamp"][es_entrenamiento].max() < ordenado["timestamp"][~es_entrenamiento].min()


def test_un_mismo_ciclo_no_se_reparte_entre_entrenamiento_y_prueba():
    """Las rutas de un ciclo comparten marca de tiempo: caen todas del mismo lado del corte, no una en cada."""
    d = pm._engineer_features(_datos(n=240, filas_sin_clima=()))
    d["timestamp"] = (
        d["timestamp"].iloc[::7].repeat(7).to_numpy()[:240]
    )  # ciclos de 7 rutas: el corte (fila 192) cae a mitad de uno
    ordenado, es_entrenamiento = pm._particion_cronologica(d)
    en_los_dos = set(ordenado["timestamp"][es_entrenamiento]) & set(ordenado["timestamp"][~es_entrenamiento])
    assert not en_los_dos


def test_la_regresion_se_evalua_con_las_filas_mas_recientes():
    """El conjunto de prueba de la regresión son exactamente las filas más recientes (con clima), no una muestra al azar."""
    d = pm._engineer_features(_datos(n=240, filas_sin_clima=(3, 50, 51)))
    res = pm._fit_regression(d)
    esperado = _ultimas(d, 48)["travel_time_min"].to_numpy()  # 237 filas con clima: 189 / 48
    assert len(res["y_test"]) == 48 and np.allclose(res["y_test"], esperado)


def test_la_clasificacion_se_evalua_con_las_filas_mas_recientes():
    """Igual en la clasificación: el tramo de prueba es el final de la serie."""
    d = pm._engineer_features(_datos(n=240, filas_sin_clima=(3, 50, 51)))
    res = pm._fit_classification(d)
    esperado = (_ultimas(d, 48)["mobility_level"] == "Alta demora").astype(int).to_numpy()
    assert res["n_train"] == 189 and res["n_test"] == 48 and np.array_equal(res["y_test"], esperado)


def test_la_validacion_cruzada_de_la_clasificacion_respeta_el_orden_temporal(monkeypatch):
    """La elección de `max_features` valida con `TimeSeriesSplit` (cada pliegue prueba con filas posteriores a las que
    entrena, por orden de filas), no con pliegues barajados: si no, el AUC de validación cruzada vuelve a ser optimista. Corta por filas, no por fecha: un ciclo puede quedar a caballo entre dos tramos de un pliegue (como mucho uno).
    """
    vistos = []
    original = pm.GridSearchCV

    def espia(*args, **kwargs):
        vistos.append(kwargs["cv"])
        return original(*args, **kwargs)

    monkeypatch.setattr(pm, "GridSearchCV", espia)
    pm._fit_classification.clear()  # la función está cacheada: sin esto no se ejecutaría el ajuste
    pm._fit_classification(pm._engineer_features(_datos()))
    assert len(vistos) == 1 and isinstance(vistos[0], pm.TimeSeriesSplit) and vistos[0].n_splits == 5


def test_el_orden_de_llegada_de_las_filas_no_cambia_la_particion():
    """La base entrega las filas de la más reciente a la más antigua: el resultado no debe depender de ello."""
    d = pm._engineer_features(_datos())
    a = pm._fit_regression(d)
    b = pm._fit_regression(d.iloc[::-1])
    assert np.allclose(a["y_test"], b["y_test"])
