"""Tests de src/analytics/causal_analysis.py con datos sintéticos de efecto conocido.

Ojo con lo que NO prueban: el módulo estima asociaciones en datos observacionales (no experimentales); estos
tests comprueban que los cálculos recuperan un efecto conocido y que los casos límite se manejan, no que el
resultado sea causal.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analytics.causal_analysis import CausalAnalysis  # noqa: E402

EFECTO = 0.5  # minutos por °C en los datos sintéticos


def _datos(n=300, efecto=EFECTO, ruido=1.0, seed=0, extra=True):
    rng = np.random.default_rng(seed)
    temp = rng.uniform(15, 35, n)
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-09-01", periods=n, freq="1h", tz="UTC"),
            "origin_temperature": temp,
            "travel_time_min": 10 + efecto * temp + rng.normal(0, ruido, n),
        }
    )
    if extra:
        df["hour"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.dayofweek
        df["average_speed_kmh"] = rng.uniform(20, 40, n)
    return df


# ---- inicialización ----


def test_el_constructor_ordena_por_tiempo_parsea_utc_y_no_modifica_el_original():
    """El constructor ordena por tiempo, interpreta los timestamps en UTC y no modifica el DataFrame original."""
    df = _datos(40).sample(frac=1, random_state=1)
    antes = df.copy()
    ca = CausalAnalysis(df)
    assert ca.df["timestamp"].is_monotonic_increasing and str(ca.df["timestamp"].dt.tz) == "UTC"
    pd.testing.assert_frame_equal(df, antes)


# ---- weather_impact_causal ----


def test_recupera_un_efecto_positivo_conocido():
    """Sobre datos con un efecto positivo conocido de la temperatura, el análisis lo recupera: correlación alta, diferencia entre grupos significativa y conclusión de evidencia muy fuerte."""
    r = CausalAnalysis(_datos()).weather_impact_causal()
    assert r["sample_size"] == 300 and r["outcome"] == "travel_time_min"
    assert r["treatment"].startswith("High temperature (>")
    assert r["correlation"]["coefficient"] > 0.9 and r["correlation"]["significant"]
    est = r["stratified_analysis"]
    assert est["high_temp_mean"] > est["low_temp_mean"] and est["effect_size"] > 3  # ~0,5 x 10 °C de diferencia
    assert est["significant"] and est["p_value"] < 0.001
    assert r["conclusion"].startswith("Very strong evidence")
    assert r["propensity_score_matching"]["status"] == "calculated"


def test_sin_efecto_no_sale_significativo():
    """Sin efecto real, ni la correlación ni el análisis estratificado salen significativos y la conclusión es de evidencia débil."""
    r = CausalAnalysis(_datos(efecto=0.0, ruido=3.0, seed=3)).weather_impact_causal()
    assert not r["stratified_analysis"]["significant"] and not r["correlation"]["significant"]
    assert r["conclusion"].startswith("Weak evidence")


def test_un_efecto_negativo_lleva_signo_negativo():
    """Un efecto negativo da coeficiente de correlación y tamaño del efecto con signo negativo."""
    r = CausalAnalysis(_datos(efecto=-0.5)).weather_impact_causal()
    assert r["correlation"]["coefficient"] < -0.9 and r["stratified_analysis"]["effect_size"] < 0


def test_sin_variables_de_ajuste_no_hay_propensity_score():
    """Sin variables de ajuste no se calcula el propensity score (`None`), pero el análisis estratificado sí."""
    r = CausalAnalysis(_datos(extra=False)).weather_impact_causal()
    assert r["propensity_score_matching"] is None and "stratified_analysis" in r


def test_usa_otra_columna_de_clima_si_se_pide():
    """Se puede analizar otra columna de clima distinta de la temperatura, por ejemplo la humedad."""
    df = _datos()
    df["origin_humidity"] = 100 - df["origin_temperature"]
    r = CausalAnalysis(df).weather_impact_causal("origin_humidity")
    assert r["correlation"]["coefficient"] < -0.9


def test_ignora_las_filas_con_nulos_y_exige_30_filas():
    """Las filas con nulos se descartan del tamaño de muestra y con menos de 30 filas útiles devuelve «Insufficient data»."""
    df = _datos(100)
    df.loc[:19, "origin_temperature"] = np.nan
    assert CausalAnalysis(df).weather_impact_causal()["sample_size"] == 80
    assert CausalAnalysis(_datos(25)).weather_impact_causal() == {"error": "Insufficient data"}


def test_columnas_ausentes_devuelven_error():
    """Si falta una columna necesaria o se pide una que no existe, devuelve un error «Missing columns»."""
    assert (
        "Missing columns"
        in CausalAnalysis(_datos().drop(columns="origin_temperature")).weather_impact_causal()["error"]
    )
    assert "Missing columns" in CausalAnalysis(_datos()).weather_impact_causal("no_existe")["error"]


# ---- weather_intervention_simulation ----


def test_la_simulacion_recupera_el_coeficiente_y_escenarios_coherentes():
    """La simulación recupera el coeficiente de temperatura y sus escenarios (de -5 a +5 °C) son coherentes: el cambio es proporcional, nulo en +0 y creciente."""
    r = CausalAnalysis(_datos(ruido=0.2)).weather_intervention_simulation()
    assert r["temperature_effect"] == pytest.approx(EFECTO, abs=0.02) and r["effect_unit"] == "minutes per °C"
    esc = r["scenarios"]
    assert list(esc) == ["-5.0°C", "-2.5°C", "+0.0°C", "+2.5°C", "+5.0°C"]
    assert esc["+5.0°C"]["time_change"] == pytest.approx(5 * EFECTO, abs=0.1)
    assert esc["-5.0°C"]["time_change"] == pytest.approx(-5 * EFECTO, abs=0.1)
    assert esc["+0.0°C"]["time_change"] == pytest.approx(0, abs=1e-9)  # la recta pasa por la media
    cambios = [v["time_change"] for v in esc.values()]
    assert cambios == sorted(cambios)


def test_la_simulacion_valida_los_datos():
    """La simulación devuelve error si falta la columna de temperatura o si hay pocos datos."""
    assert (
        "not available"
        in CausalAnalysis(_datos().drop(columns="origin_temperature")).weather_intervention_simulation()["error"]
    )
    assert CausalAnalysis(_datos(20)).weather_intervention_simulation() == {"error": "Insufficient data"}


# ---- route_intervention_effectiveness ----


def _antes_despues(n=100, salto=-3.0, seed=0):
    rng = np.random.default_rng(seed)
    t = 15 + rng.normal(0, 1, n)
    t[int(n * 0.75) :] += salto  # el último 25 % es el "después"
    return pd.DataFrame({"travel_time_min": t})


def test_mide_una_mejora_antes_despues():
    """Mide una intervención que mejora el tiempo de viaje: efecto negativo, significativo, grande y con los tamaños de muestra de antes y después."""
    r = CausalAnalysis(_datos(40)).route_intervention_effectiveness(_antes_despues())
    efecto = r["intervention_effect"]
    assert efecto["effect_size"] == pytest.approx(-3.0, abs=0.7) and efecto["direction"] == "improvement"
    assert r["statistical_significance"]["significant"] and r["statistical_significance"]["effect_magnitude"] == "large"
    assert r["sample_sizes"] == {"before": 75, "after": 25}


def test_una_degradacion_se_marca_como_tal():
    """Una intervención que empeora el tiempo de viaje se marca como degradación con efecto positivo."""
    r = CausalAnalysis(_datos(40)).route_intervention_effectiveness(_antes_despues(salto=+3.0))
    assert r["intervention_effect"]["direction"] == "degradation" and r["intervention_effect"]["effect_size"] > 0


def test_sin_cambio_no_es_significativo_y_el_efecto_es_despreciable():
    """Sin cambio entre antes y después, el resultado no es significativo y el efecto es despreciable o pequeño."""
    r = CausalAnalysis(_datos(40)).route_intervention_effectiveness(_antes_despues(salto=0.0, seed=5))
    assert not r["statistical_significance"]["significant"]
    assert r["statistical_significance"]["effect_magnitude"] in ("negligible", "small")


def test_intervencion_valida_columna_y_tamano_de_los_periodos():
    """La evaluación de una intervención devuelve error si falta `travel_time_min` o si el periodo tiene muy pocos datos."""
    ca = CausalAnalysis(_datos(40))
    assert ca.route_intervention_effectiveness(pd.DataFrame({"x": [1, 2]})) == {"error": "Missing travel_time_min"}
    assert (
        "Insufficient data"
        in ca.route_intervention_effectiveness(pd.DataFrame({"travel_time_min": range(20)}))["error"]
    )


def test_serie_constante_no_divide_por_cero():
    """Con una serie constante, la d de Cohen es 0 y no se divide entre cero."""
    r = CausalAnalysis(_datos(40)).route_intervention_effectiveness(pd.DataFrame({"travel_time_min": [10.0] * 100}))
    assert r["statistical_significance"]["cohens_d"] == 0


# ---- confounding_analysis ----


def test_detecta_la_hora_como_confusor_cuando_afecta_a_temperatura_y_trafico():
    """La hora del día se detecta como confusor de severidad alta cuando influye a la vez en la temperatura y en el tráfico."""
    n = 240
    hora = np.tile(np.arange(24), n // 24)
    df = pd.DataFrame(
        {"hour": hora, "origin_temperature": 10 + hora * 0.8, "travel_time_min": 5 + hora * 0.5, "day_of_week": 0}
    )
    c = CausalAnalysis(df).confounding_analysis()["identified_confounders"]
    assert [x["variable"] for x in c] == ["hour"] and c[0]["severity"] == "high"


def test_la_hora_no_es_confusor_si_solo_afecta_a_una_de_las_dos_variables():
    """Un confusor debe afectar al tratamiento Y al resultado: con solo uno de los dos no se marca."""
    hora = np.tile(np.arange(24), 10)
    rng = np.random.default_rng(0)
    solo_temperatura = pd.DataFrame(
        {"hour": hora, "origin_temperature": 10 + hora * 0.8, "travel_time_min": rng.normal(10, 0.1, 240)}
    )
    solo_trafico = pd.DataFrame(
        {"hour": hora, "origin_temperature": rng.normal(20, 0.1, 240), "travel_time_min": 5 + hora * 0.5}
    )
    for df in (solo_temperatura, solo_trafico):
        assert CausalAnalysis(df).confounding_analysis()["identified_confounders"] == []


def test_detecta_el_dia_de_la_semana_si_el_trafico_varia_mas_de_un_20_por_ciento():
    """El día de la semana se detecta como confusor si el tráfico varía más de un 20 % entre días."""
    df = pd.DataFrame({"day_of_week": [0, 1, 2, 3, 4, 5, 6] * 10, "travel_time_min": [10, 10, 10, 10, 10, 30, 30] * 10})
    c = CausalAnalysis(df).confounding_analysis()["identified_confounders"]
    assert [x["variable"] for x in c] == ["day_of_week"]


def test_sin_confusores_la_lista_esta_vacia_y_hay_recomendaciones():
    """Sin confusores la lista queda vacía, pero se devuelven consejos y recomendación de método; con datos insuficientes también queda vacía."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "hour": rng.integers(0, 24, 200),
            "origin_temperature": rng.normal(20, 3, 200),
            "travel_time_min": rng.normal(10, 0.1, 200),
            "day_of_week": rng.integers(0, 7, 200),
        }
    )
    r = CausalAnalysis(df).confounding_analysis()
    assert r["identified_confounders"] == [] and r["advice"] and r["method_recommendation"]
    assert CausalAnalysis(pd.DataFrame({"x": [1]})).confounding_analysis()["identified_confounders"] == []


# ---- interpretaciones ----


@pytest.mark.parametrize(
    "p, texto", [(0.0005, "Very strong"), (0.005, "Strong evidence"), (0.03, "Moderate"), (0.2, "Weak")]
)
def test_interpretacion_del_p_valor(p, texto):
    """El texto de interpretación del efecto cambia según el p-valor (parametrizado) y siempre incluye el efecto con su signo."""
    assert CausalAnalysis._interpret_causal_effect(1.5, p).startswith(texto)
    assert "+1.50" in CausalAnalysis._interpret_causal_effect(1.5, p)


@pytest.mark.parametrize(
    "d, etiqueta",
    [
        (0.0, "negligible"),
        (0.19, "negligible"),
        (0.2, "small"),
        (0.5, "medium"),
        (0.79, "medium"),
        (0.8, "large"),
        (2.0, "large"),
    ],
)
def test_interpretacion_de_cohen(d, etiqueta):
    """La etiqueta de magnitud de la d de Cohen (parametrizado) corresponde a cada valor de d."""
    assert CausalAnalysis._interpret_cohens_d(d) == etiqueta
