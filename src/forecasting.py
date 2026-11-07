"""Pronóstico horario del % de mediciones en 'Alta demora'.

Un único sitio para el modelo, que usan tanto el dashboard (streamlit_app/dashboards/
predictive_modeling_dashboard.py) como la herramienta de validación (tools/validate_forecast.py):
así lo que se valida es exactamente lo que se muestra.

Por qué SARIMA con diferenciación estacional y la serie en escala 0-100
-----------------------------------------------------------------------
Medido sobre la base real (tools/validate_forecast.py, ver README):
  * El ARIMA estacional anterior, (p,d,q)x(1,0,1,24) sobre la serie en escala 0-1, no convergía:
    los 4 candidatos se detenían en el tope de 50 iteraciones del optimizador (`warnflag=1`),
    con el AR estacional pegado a ~0,99 (casi una raíz unitaria que se cancela con el MA ~-0,9) y
    `sigma2` ~ 1e-4, una escala mala para el optimizador. Convergía en 10 de 35 cortes de validación.
  * Pasar la parte estacional a diferenciación (D=1) es lo que pide esa casi raíz unitaria, y escalar
    la serie a 0-100 arregla la escala: (1,0,1)x(0,1,1,24) converge en 35 de 35 cortes, con 11-35
    iteraciones, y es el mejor de los ARIMA probados.
  * Pero NINGÚN ARIMA mejora de forma demostrable a la referencia más simple (la media de cada hora
    del día): ver VALIDATION_NOTE. Por eso el dashboard dibuja esa referencia junto al pronóstico.
"""

from typing import Optional

import numpy as np
import pandas as pd

SEASONAL_PERIOD = 24
ORDER = (1, 0, 1)
SEASONAL_ORDER = (0, 1, 1, SEASONAL_PERIOD)
SCALE = 100          # la serie (0-1) se ajusta en escala 0-100: con 0-1, sigma2 ~ 1e-4 y el optimizador sufre
MAXITER = 200        # converge en 11-35 iteraciones; el tope solo es una red de seguridad
HORIZON = 24

# Resultado de tools/validate_forecast.py sobre la base real (35 cortes diarios, ago-oct 2026). Es una
# fotografía con fecha: se vuelve a calcular ejecutando la herramienta.
VALIDATION_NOTE = (
    "Validación con 35 cortes (ajustar con el pasado y pronosticar las 24 h siguientes; tools/validate_forecast.py, "
    "6-nov-2026): este modelo converge en 35/35 y su error (MAE 0,0233) es estadísticamente indistinguible del de la "
    "referencia más simple, la media de cada hora del día (0,0222; diferencia +0,0011 ± 0,0019, IC 95 %). "
    "O sea: aquí el ARIMA no aporta evidencia de ser mejor que la referencia."
)


def hourly_share(alta: pd.Series) -> pd.Series:
    """Serie horaria regular (con NaN en las horas sin datos) del % de 'Alta demora'.

    `alta` es una serie 0/1 indexada por timestamp (UTC). Las horas sin mediciones quedan en NaN: el
    equipo anfitrión se apaga y esos huecos NO se inventan.
    """
    return alta.sort_index().resample("1h").mean()


def hourly_profile(series: pd.Series) -> pd.Series:
    """Media de cada hora del día (0-23, UTC) sobre las horas OBSERVADAS de `series`."""
    obs = series.dropna()
    return obs.groupby(obs.index.hour).mean()


def profile_forecast(series: pd.Series, horizon_index: pd.DatetimeIndex) -> pd.Series:
    """Referencia: para cada hora del horizonte, la media histórica de esa hora del día."""
    perfil = hourly_profile(series)
    media = series.dropna().mean()
    return pd.Series([perfil.get(h.hour, media) for h in horizon_index], index=horizon_index)


def fit_sarima(series: pd.Series, max_gap_hours: int = 3):
    """Ajusta el SARIMA sobre `series` (0-1, con NaN) y devuelve el resultado de statsmodels.

    Solo se interpolan huecos de hasta `max_gap_hours` horas seguidas; los demás siguen siendo NaN y el
    modelo de espacio de estados los trata como datos faltantes (no se rellenan).

    La optimización (lo que gasta memoria) se hace con low_memory=True: mismo pronóstico y ~la mitad de
    memoria (~405 MB en vez de ~870 MB). PERO low_memory=True deja el intervalo de confianza del pronóstico
    en NaN (error que ya tenía el ARIMA anterior: la banda del gráfico no se dibujaba). Por eso, con los
    parámetros ya estimados, se hace una única pasada `smooth` completa, barata, que sí lo calcula. Se
    conserva en `mle_retvals` el diagnóstico de convergencia de la optimización.
    """
    from statsmodels.tsa.arima.model import ARIMA

    y = series.interpolate(limit=max_gap_hours) * SCALE
    modelo = ARIMA(y, order=ORDER, seasonal_order=SEASONAL_ORDER)
    ajuste = modelo.fit(low_memory=True, method_kwargs={"maxiter": MAXITER})
    completo = modelo.smooth(ajuste.params)
    completo.mle_retvals = ajuste.mle_retvals
    return completo


def forecast_sarima(series: pd.Series, steps: int = HORIZON, max_gap_hours: int = 3, alpha: float = 0.2) -> dict:
    """Pronóstico a `steps` horas, en la escala original (0-1).

    Devuelve: mean (Serie), ci (DataFrame lower/upper al nivel 1-alpha), converged (bool), iterations (int).
    """
    res = fit_sarima(series, max_gap_hours)
    pred = res.get_forecast(steps=steps)
    ret = res.mle_retvals or {}
    return {
        "mean": pred.predicted_mean / SCALE,
        "ci": pred.conf_int(alpha=alpha) / SCALE,
        "converged": bool(ret.get("converged", False)),
        "iterations": ret.get("iterations"),
    }


def mae(pred, real) -> Optional[float]:
    """Error absoluto medio solo sobre las posiciones donde `real` existe (no es NaN)."""
    pred, real = np.asarray(pred, dtype=float), np.asarray(real, dtype=float)
    ok = ~np.isnan(real)
    return float(np.mean(np.abs(pred[ok] - real[ok]))) if ok.any() else None
