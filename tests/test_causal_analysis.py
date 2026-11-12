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

from src.analytics.causal_analysis import CausalAnalysis, _matched_smd, _nearest_control, _smd  # noqa: E402

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


def test_sin_marca_de_tiempo_ni_covariables_no_hay_ajuste():
    """Sin timestamp, ruta ni covariables no hay con qué ajustar: ni propensity score ni estratificación (`None`),
    pero el análisis sin ajustar sí. Antes bastaba con que faltaran `hour`/`day_of_week`/`average_speed_kmh`."""
    r = CausalAnalysis(_datos(extra=False).drop(columns="timestamp")).weather_impact_causal()
    assert r["propensity_score_matching"] is None and r["stratified_adjusted"] is None
    assert r["adjusted_conclusion"] is None and "stratified_analysis" in r


def test_con_marca_de_tiempo_se_ajusta_aunque_no_existan_las_columnas_hour_y_day_of_week():
    """Regresión: el 'PSM' solo corría si existían las columnas hour/day_of_week/average_speed_kmh, que en los datos
    reales casi nunca existen. Ahora hora, día y semana se derivan del timestamp."""
    r = CausalAnalysis(_datos(extra=False)).weather_impact_causal()
    assert (
        r["propensity_score_matching"]["status"] == "calculated" and r["stratified_adjusted"]["status"] == "calculated"
    )
    assert r["adjusted_conclusion"] and "not proof of causality" in r["adjusted_conclusion"]


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


# ---------------------------------------------------------------------------
# Estimación ajustada: estratificación exacta y propensity-score matching REAL
# ---------------------------------------------------------------------------


def _panel(efecto=0.0, dias=60, seed=0, desfase_ruta=0.0, efecto_ruta=0.0):
    """Panel con dos rutas donde el calor y el tráfico dependen de la HORA (confusor). `efecto` = minutos por °C de
    anomalía (calor por encima de lo habitual para esa hora). Con `desfase_ruta`/`efecto_ruta`, la ruta A sale de un
    origen más cálido y es más rápida: la ruta confunde, sin que el calor tenga efecto alguno."""
    rng = np.random.default_rng(seed)
    filas = []
    inicio = pd.Timestamp("2026-09-01", tz="UTC")
    for d in range(dias):
        anomalia_dia = rng.normal(0, 2)
        for h in range(24):
            ciclo = 8 * np.sin((h - 9) / 24 * 2 * np.pi)
            punta = 6 * np.exp(-((h - 8) ** 2) / 8) + 5 * np.exp(-((h - 18) ** 2) / 8)
            for ruta, signo in (("A", 1), ("B", -1)):
                anomalia = anomalia_dia + rng.normal(0, 0.7)
                filas.append(
                    {
                        "timestamp": inicio + pd.Timedelta(days=d, hours=h),
                        "origin": ruta,
                        "destination": "Z",
                        "data_source": "tomtom",
                        "origin_temperature": 20 + ciclo + anomalia + signo * desfase_ruta,
                        "travel_time_min": 12 + signo * efecto_ruta + punta + efecto * anomalia + rng.normal(0, 0.5),
                    }
                )
    return pd.DataFrame(filas)


def test_la_estratificacion_recupera_un_efecto_conocido():
    """Con efecto 0,5 min/°C de anomalía, la diferencia entre 'más calor de lo habitual' y 'menos' es ~0,5 × 3,4 °C
    (esperado ~1,7; medido 1,59): se recupera y el intervalo excluye el 0."""
    r = CausalAnalysis(_panel(efecto=0.5)).stratified_adjusted(n_boot=200)
    assert r["status"] == "calculated" and 1.3 < r["att"] < 1.9 and r["ci_excludes_zero"]


def test_la_estratificacion_sin_efecto_no_inventa_uno_aunque_la_hora_confunda():
    """El calor y el tráfico dependen de la hora; sin efecto verdadero, el estimador ajustado da ~0."""
    r = CausalAnalysis(_panel(efecto=0.0)).stratified_adjusted(n_boot=200)
    assert abs(r["att"]) < 0.1 and r["ci_95"][0] <= 0.0 + 0.06 and r["ci_95"][1] >= -0.06


def test_la_ruta_confunde_y_la_estratificacion_la_neutraliza():
    """La ruta A es más cálida y 4 min más rápida, pero el calor NO tiene efecto: sin ajustar sale -4,4 min; con la ruta
    en los estratos, ~0; sin la ruta en los estratos, el sesgo vuelve (es lo que pasaba con los datos reales)."""
    ca = CausalAnalysis(_panel(efecto=0.0, desfase_ruta=1.5, efecto_ruta=-4.0))
    con_ruta, sin_ruta = ca.stratified_adjusted(n_boot=200), ca.stratified_adjusted(strata=["hour", "week"], n_boot=200)
    assert con_ruta["naive_difference"] < -3.5 and abs(con_ruta["att"]) < 0.2
    assert sin_ruta["att"] < -3.5


def test_estratificacion_descarta_las_tratadas_sin_controles_en_su_estrato_y_lo_cuenta():
    r = CausalAnalysis(_panel(efecto=0.0, dias=10)).stratified_adjusted(
        strata=["origin", "destination", "hour", "week"]
    )
    assert 0 < r["share_used"] <= 1 and r["n_used"] <= r["n_treated"] and r["n_strata_used"] > 0
    assert r["strata_on"] == ["origin", "destination", "hour", "week"]


def test_estratificacion_sin_soporte_comun_da_error():
    """Si cada estrato tiene solo tratadas o solo controles (aquí, una columna que separa los dos grupos), no hay
    comparación posible."""
    df = _panel(dias=10)
    df["grupo"] = (df["origin_temperature"] > df["origin_temperature"].median()).astype(str)
    r = CausalAnalysis(df).stratified_adjusted(strata=["grupo"], treatment="above_median")
    assert "no common support" in r["error"]


def test_las_columnas_de_estrato_desconocidas_dan_error_en_vez_de_romper():
    ca = CausalAnalysis(_panel(dias=10))
    assert "Unknown stratification column" in ca.stratified_adjusted(strata=["no_existe"])["error"]
    assert "Unknown stratification column" in ca.propensity_score_matching(exact=["no_existe"])["error"]


@pytest.mark.parametrize("metodo", ["stratified_adjusted", "propensity_score_matching"])
def test_errores_de_los_estimadores_ajustados(metodo):
    ca = CausalAnalysis(_panel(dias=10))
    assert "Unknown treatment" in getattr(ca, metodo)(treatment="otro")["error"]
    assert "Missing columns" in getattr(ca, metodo)(weather_col="no_existe")["error"]
    pocos = CausalAnalysis(_panel(dias=10).head(20))
    assert getattr(pocos, metodo)() == {"error": "Insufficient data"}
    constante = _panel(dias=10)
    constante["origin_temperature"] = 20.0
    assert getattr(CausalAnalysis(constante), metodo)()["error"] == "No variation in treatment"


def test_la_estratificacion_sin_columnas_de_estrato_avisa():
    sin = _panel(dias=10).drop(columns=["timestamp", "origin", "destination", "data_source"])
    assert "No stratification columns" in CausalAnalysis(sin).stratified_adjusted()["error"]


def test_el_psm_es_un_emparejamiento_real_y_no_la_diferencia_de_medias():
    """Regresión: antes se calculaban los propensity scores y no se usaban; el 'PSM' era la diferencia de medias entre
    tratadas y controles. Con la ruta confundiendo (-4,4 sin ajustar), el emparejamiento exacto por ruta la reduce mucho.
    """
    r = CausalAnalysis(_panel(efecto=0.0, desfase_ruta=1.5, efecto_ruta=-4.0)).propensity_score_matching(n_boot=100)
    assert r["status"] == "calculated" and r["naive_difference"] < -3.5
    assert abs(r["att"]) < 0.25 * abs(r["naive_difference"])
    assert r["exact_match_on"] == ["origin", "destination", "data_source"]


def test_el_psm_avisa_cuando_su_equilibrio_es_pobre_y_no_se_fia_de_si_mismo():
    """Con un propensity score casi constante el emparejamiento es casi aleatorio y puede no equilibrar (King y
    Nielsen, 2019). El diagnóstico lo detecta y el texto lo advierte en vez de presentar el número como bueno."""
    r = CausalAnalysis(_panel(efecto=0.0, desfase_ruta=1.5, efecto_ruta=-4.0)).propensity_score_matching(n_boot=100)
    b = r["balance"]
    assert b["quality"] == "poor" and not b["balanced"] and b["max_abs_smd_after"] >= 0.25
    assert "WARNING" in r["interpretation"] and "do not rely" in r["interpretation"]


def test_con_la_mediana_global_el_tratamiento_queda_determinado_por_la_hora_y_el_equilibrio_falla():
    """'Por encima de la mediana global' es casi 'es de día': sin solapamiento, el PSM no equilibra (SMD ~1)."""
    r = CausalAnalysis(_panel(efecto=0.0)).propensity_score_matching(treatment="above_median", n_boot=100)
    assert r["balance"]["quality"] == "poor" and r["balance"]["max_abs_smd_after"] > 0.5


def test_el_psm_informa_del_equilibrio_antes_y_despues_y_de_las_peores_covariables():
    r = CausalAnalysis(_panel(efecto=0.5)).propensity_score_matching(n_boot=100)
    b = r["balance"]
    assert {
        "max_abs_smd_before",
        "max_abs_smd_after",
        "mean_abs_smd_before",
        "mean_abs_smd_after",
        "quality",
        "worst_after",
    } <= set(b)
    assert len(b["worst_after"]) == 5 and b["quality"] in ("good", "acceptable", "poor")
    assert r["n_matched"] <= r["n_treated"] and 0 < r["share_matched"] <= 1 and r["caliper"] > 0


def test_el_psm_no_ajusta_por_consecuencias_del_trafico():
    """La velocidad media es CONSECUENCIA del tiempo de viaje: ajustar por ella sesga. Por defecto no entra."""
    df = _panel(efecto=0.5, dias=20)
    df["average_speed_kmh"] = 60 - df["travel_time_min"]
    r = CausalAnalysis(df).propensity_score_matching(n_boot=50)
    # (la fuente no aparece: en este panel solo hay una, su indicador es constante y se descarta)
    assert "average" not in " ".join(r["covariates"]) and set(r["covariates"]) == {"dia", "hora", "ruta", "semana"}


def test_el_psm_es_determinista_con_la_misma_semilla_y_el_intervalo_contiene_el_efecto():
    ca = CausalAnalysis(_panel(efecto=0.5, dias=30))
    a, b = ca.propensity_score_matching(n_boot=80, seed=3), ca.propensity_score_matching(n_boot=80, seed=3)
    assert a["att"] == b["att"] and a["ci_95"] == b["ci_95"]
    assert a["ci_95"][0] <= a["att"] <= a["ci_95"][1]


def test_el_intervalo_por_dias_es_mas_ancho_que_uno_que_trata_cada_medicion_como_independiente():
    """Las mediciones de un mismo día comparten el mismo golpe: remuestrear días completos da un intervalo más honesto."""
    rng = np.random.default_rng(0)
    dias, por_dia = 40, 48
    golpe = rng.normal(0, 1, dias)
    diff = np.repeat(golpe, por_dia) + rng.normal(0, 0.5, dias * por_dia)
    df = pd.DataFrame(
        {"timestamp": pd.to_datetime(np.repeat(pd.date_range("2026-09-01", periods=dias, tz="UTC"), por_dia))}
    )
    lo, hi = CausalAnalysis._cluster_bootstrap(diff, df, np.arange(len(diff)), 500, 0)
    ingenuo = np.quantile([rng.choice(diff, len(diff)).mean() for _ in range(500)], [0.025, 0.975])
    assert (hi - lo) > 3 * (ingenuo[1] - ingenuo[0])


def test_smd_de_dos_grupos_iguales_desplazados_y_con_pesos():
    base = np.random.default_rng(0).normal(0, 1, (4000, 1))
    assert abs(_smd(base, base.copy(), None)[0]) < 1e-12
    assert _smd(base + 1.0, base, None)[0] == pytest.approx(1.0, abs=0.02)  # un desvío típico de diferencia
    pesos = np.zeros(4000)
    pesos[:2000] = 1 / 2000  # solo cuenta la mitad de los controles
    assert _smd(base[:2000], base, pesos)[0] == pytest.approx(0.0, abs=1e-12)
    constante = np.ones((10, 1))
    assert _smd(constante, constante, None)[0] == 0.0  # sin varianza: 0, no NaN


def test_la_matriz_de_ajuste_deriva_hora_dia_semana_ruta_y_fuente():
    ca = CausalAnalysis(_panel(dias=14))
    X = ca._adjustment_matrix(ca.df)
    prefijos = {c.split("_")[0] for c in X.columns}
    assert prefijos == {"hora", "dia", "semana", "ruta", "fuente"} or prefijos == {"hora", "dia", "semana", "ruta"}
    assert X.shape[0] == len(ca.df) and (X.std() > 0).all()  # sin columnas constantes


def test_una_covariable_numerica_con_pocos_valores_es_categorica_y_con_muchos_se_estandariza():
    df = pd.DataFrame({"hora": np.arange(200) % 24, "continua": np.random.default_rng(0).normal(50, 10, 200)})
    X = CausalAnalysis(pd.DataFrame({"travel_time_min": [1.0]}))._adjustment_matrix(df, ["hora", "continua"])
    assert sum(c.startswith("hora_") for c in X.columns) == 23  # 24 valores -> 23 indicadores (drop_first)
    assert abs(X["continua"].mean()) < 1e-9 and X["continua"].std() == pytest.approx(1.0, abs=0.01)


def test_sin_nada_con_que_ajustar_la_matriz_es_none():
    ca = CausalAnalysis(pd.DataFrame({"travel_time_min": [1.0, 2.0], "origin_temperature": [20.0, 21.0]}))
    assert ca._adjustment_matrix(ca.df) is None


def test_ningun_texto_presenta_una_asociacion_como_causa():
    """Los datos son observacionales: las salidas hablan de asociación y avisan de que no es prueba de causalidad."""
    ca = CausalAnalysis(_panel(efecto=0.5, dias=20))
    textos = [
        ca.weather_impact_causal()["adjusted_conclusion"],
        ca.weather_impact_causal()["conclusion"],
        ca.weather_impact_causal()["stratified_analysis"]["effect_interpretation"],
        ca.weather_intervention_simulation()["interpretation"],
        ca.route_intervention_effectiveness(ca.df)["intervention_effect"]["interpretation"],
        ca.propensity_score_matching(n_boot=30)["interpretation"],
    ]
    for t in textos:
        assert " causes " not in t and "caused" not in t and "causal effect" not in t, t
    assert all("associated" in t or "difference" in t or "change" in t for t in textos)
    assert "not proof of causality" in textos[0]


def test_weather_impact_causal_incluye_los_dos_estimadores_ajustados():
    r = CausalAnalysis(_panel(efecto=0.5, dias=20)).weather_impact_causal()
    assert (
        r["stratified_adjusted"]["status"] == "calculated" and r["propensity_score_matching"]["status"] == "calculated"
    )
    assert r["adjusted_conclusion"] == r["stratified_adjusted"]["interpretation"]


def _confusor_continuo(n=3000, seed=0, efecto=0.0):
    """El calor depende de un confusor continuo `x` y el tiempo de viaje también; `efecto` = minutos por °C."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n)
    temperatura = 3 * x + rng.normal(0, 1, n)
    return pd.DataFrame(
        {
            "x": x,
            "origin_temperature": temperatura,
            "travel_time_min": 10 + 2 * x + efecto * temperatura + rng.normal(0, 0.5, n),
        }
    )


def _psm_continuo(df, **kw):
    return CausalAnalysis(df).propensity_score_matching(
        covariates=["x"], treatment="above_median", exact=[], n_boot=100, **kw
    )


def test_el_psm_ajusta_un_confusor_continuo_cuando_hay_solapamiento():
    """Donde el propensity score SÍ varía, el emparejamiento hace su trabajo: la diferencia sin ajustar (+3) se reduce a
    ~0 y el equilibrio pasa de SMD 2,3 a ~0,05."""
    r = _psm_continuo(_confusor_continuo())
    assert r["naive_difference"] > 2.5 and abs(r["att"]) < 0.2
    b = r["balance"]
    assert b["max_abs_smd_before"] > 1.0 and b["max_abs_smd_after"] < 0.1 and b["quality"] == "good" and b["balanced"]
    assert "WARNING" not in r["interpretation"] and "acceptable" not in r["interpretation"]


def test_el_psm_con_confusor_continuo_recupera_un_efecto_positivo():
    r = _psm_continuo(_confusor_continuo(efecto=0.5))
    assert r["att"] > 0.8 and r["ci_excludes_zero"]


def test_el_caliper_descarta_las_tratadas_sin_pareja_cercana_y_sin_el_el_sesgo_reaparece():
    """Sin caliper se empareja a todas, también a las que no tienen un control parecido, y el estimador se sesga."""
    df = _confusor_continuo()
    con, sin = _psm_continuo(df), _psm_continuo(df, caliper_sd=100)
    assert con["share_matched"] < 0.8 and sin["share_matched"] == 1.0
    assert abs(sin["att"]) > 3 * abs(con["att"])
    assert (
        _psm_continuo(df, caliper_sd=0.02)["share_matched"] < con["share_matched"]
    )  # un caliper más estrecho descarta más


def test_el_equilibrio_pondera_cada_control_por_las_veces_que_se_usa():
    """Emparejamiento con reemplazo: un control usado dos veces pesa el doble. Tratadas x=1,1,1; controles x=1 (usado
    2 veces) y x=100 (1 vez): la media ponderada es 34, no 50,5."""
    x = np.array([[1.0], [1.0], [1.0], [1.0], [100.0]])
    despues = _matched_smd(x, np.array([0, 1, 2]), np.array([3, 3, 4]))
    esperado = _smd(x[[0, 1, 2]], x[[3, 4]], np.array([2 / 3, 1 / 3]))
    np.testing.assert_allclose(despues, esperado)
    assert abs(despues[0]) > 0.5


def test_una_covariable_constante_no_cuenta_como_ajuste():
    """Una variable sin variación se descarta de la matriz: no puede ajustar nada."""
    df = _confusor_continuo(n=200)
    df["constante"] = 5.0
    assert CausalAnalysis(df)._adjustment_matrix(df, ["constante"]).shape[1] == 0
    assert "No adjustment covariates" in CausalAnalysis(df).propensity_score_matching(covariates=["constante"])["error"]


def test_el_vecino_mas_cercano_se_elige_entre_los_dos_lados():
    """Controles separados (0, 1, 5, 10): cada tratada se empareja con el más próximo, venga de la izquierda o de la
    derecha, y los extremos se quedan con el control del borde."""
    controles = np.array([0.0, 1.0, 5.0, 10.0])
    elegidos = _nearest_control(np.array([0.9, 4.0, 7.4, 7.6, -3.0, 99.0]), controles)
    assert elegidos.tolist() == [1, 2, 2, 3, 0, 3]
    assert _nearest_control(np.array([3.0]), np.array([1.0, 5.0])).tolist() in (
        [0],
        [1],
    )  # empate: cualquiera de los dos
    assert _nearest_control(np.array([2.9]), np.array([1.0, 5.0])).tolist() == [0]
