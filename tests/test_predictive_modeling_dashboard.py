"""Pruebas de la preparación de datos del dashboard de modelado predictivo.

Regresión: con datos reales, unas pocas filas (OpenWeather falló en ese ciclo)
tienen el clima en NULL, y una sola basta para que `LogisticRegression` lance
`Input X contains NaN`. Esa excepción cortaba toda la vista Analyst.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamlit_app.dashboards import predictive_modeling_dashboard as pm


def _datos(n=240, filas_sin_clima=(3, 50, 51), seed=0):
    rng = np.random.default_rng(seed)
    descripciones = ["clear sky", "few clouds", "broken clouds", "light rain", "mist"]
    df = pd.DataFrame({
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
    })
    df["mobility_level"] = np.where(df["travel_time_min"] > 20, "Alta demora", "Movilidad normal")
    for i in filas_sin_clima:   # OpenWeather no respondió en ese ciclo
        df.loc[i, ["origin_temperature", "origin_humidity", "origin_weather"]] = np.nan
    return df


def test_clima_ausente_no_se_convierte_en_lluvia():
    d = pm._engineer_features(_datos())
    assert d.loc[3, "origin_weather_grp"] != d.loc[3, "origin_weather_grp"]   # NaN, no "lluvia"
    assert d["origin_weather_grp"].isna().sum() == 3


def test_descripciones_conocidas_y_desconocidas_se_agrupan_como_antes():
    d = pm._engineer_features(_datos(filas_sin_clima=()))
    por_desc = d.groupby("origin_weather")["origin_weather_grp"].first()
    assert por_desc["clear sky"] == "despejado"
    assert por_desc["few clouds"] == "parcialmente_nublado"
    assert por_desc["broken clouds"] == "nublado"
    assert por_desc["light rain"] == "lluvia"      # no está en WEATHER_GROUPS
    assert por_desc["mist"] == "lluvia"


def test_complete_cases_excluye_solo_las_filas_sin_clima():
    d = pm._engineer_features(_datos(n=240, filas_sin_clima=(3, 50, 51)))
    limpio = pm._complete_cases(d)
    assert len(limpio) == 237
    assert limpio[pm.MODEL_FEATURE_COLS].notna().all().all()
    # el dato original no se muta: las 3 filas siguen en d (las usan forecast y clustering)
    assert len(d) == 240


def test_sin_filas_incompletas_no_se_pierde_nada():
    d = pm._engineer_features(_datos(filas_sin_clima=()))
    assert len(pm._complete_cases(d)) == len(d)


def test_regresion_no_falla_con_filas_sin_clima():
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
    assert res["agg"]["n"].sum() == len(d)      # contó las 240 filas, no 237
