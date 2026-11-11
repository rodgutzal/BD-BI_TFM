"""
Valida el pronóstico horario de 'Alta demora' con una validación de origen móvil (rolling origin).

Para cada corte (medianoche UTC) ajusta el modelo SOLO con lo anterior al corte, pronostica las 24 h
siguientes y mide el error sobre las horas de ese día que SÍ tienen dato. Compara el SARIMA del dashboard
(src/forecasting.py) con referencias triviales:
  - perfil horario      media de cada hora del día en el entrenamiento
  - mismo hora de ayer  el valor de hace 24 h (el perfil si falta)
  - media global, y persistencia del último valor observado.
La comparación es PAREADA por corte (diferencia de MAE frente al perfil horario, con su intervalo de
confianza al 95 %): con pocos cortes y datos con huecos, una diferencia pequeña puede ser ruido.

Es de SOLO LECTURA: abre la base con `immutable=1` (no crea archivos ni escribe). Con el stack apagado.

Uso (desde la raíz del proyecto):
    python tools/validate_forecast.py                    # los cortes elegibles (unos 4 min con 35 cortes)
    python tools/validate_forecast.py --max-cuts 10      # más rápido
    python tools/validate_forecast.py --include-legacy   # añade el ARIMA anterior (no converge) para comparar
"""

import argparse
import sqlite3
import sys
import time
import warnings
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import forecasting  # noqa: E402

DEFAULT_DB = ROOT / "data" / "mobility.db"
PERFIL = "Perfil horario (media por hora del día)"
AYER = "Mismo hora de ayer (el perfil si falta)"
MEDIA = "Media global del entrenamiento"
PERSISTENCIA = "Último valor observado"
SARIMA = "SARIMA del dashboard (src/forecasting.py)"
LEGACY = "ARIMA anterior (escala 0-1, tope de 50 iteraciones)"


def load_hourly_share(db_path: Path, since: str = "2026-08-01") -> pd.Series:
    """Serie horaria del % de 'Alta demora' (con NaN en las horas sin dato), en solo lectura."""
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?immutable=1", uri=True)
    try:
        df = pd.read_sql(
            "SELECT timestamp, mobility_level FROM route_measurements WHERE timestamp >= ?", conn, params=(since,)
        )
    finally:
        conn.close()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    df["alta"] = (df["mobility_level"] == "Alta demora").astype(int)
    return forecasting.hourly_share(df.set_index("timestamp")["alta"])


def eligible_cutoffs(
    series: pd.Series, horizon: int = 24, min_future_obs: int = 12, min_train_obs: int = 168
) -> List[pd.Timestamp]:
    """Medianoches UTC en las que el horizonte tiene al menos `min_future_obs` horas observadas y el
    pasado al menos `min_train_obs` (por defecto 168 = una semana de horas con dato)."""
    cortes = []
    for d in pd.date_range(
        series.index[0].ceil("D"), series.index[-1].floor("D") - pd.Timedelta(hours=horizon), freq="1D", tz="UTC"
    ):
        futuro = series[d : d + pd.Timedelta(hours=horizon - 1)]
        pasado = series[: d - pd.Timedelta(hours=1)]
        if futuro.notna().sum() >= min_future_obs and pasado.notna().sum() >= min_train_obs:
            cortes.append(d)
    return cortes


def baseline_forecasts(series: pd.Series, cutoff: pd.Timestamp, horizon: int = 24) -> Dict[str, np.ndarray]:
    """Las referencias triviales para el horizonte que empieza en `cutoff`, usando solo datos anteriores."""
    pasado = series[: cutoff - pd.Timedelta(hours=1)]
    horizonte = pd.date_range(cutoff, periods=horizon, freq="1h", tz="UTC")
    obs = pasado.dropna()
    perfil = forecasting.profile_forecast(pasado, horizonte).values
    ayer = series.reindex(horizonte - pd.Timedelta(hours=24)).values  # [cutoff-24h, cutoff-1h]: todo pasado
    return {
        PERFIL: perfil,
        AYER: np.where(np.isnan(ayer), perfil, ayer),
        MEDIA: np.full(horizon, obs.mean()),
        PERSISTENCIA: np.full(horizon, obs.iloc[-1]),
    }


def _legacy_forecast(pasado: pd.Series, horizon: int) -> Tuple[np.ndarray, bool]:
    """El ARIMA anterior del dashboard, tal cual: (1,1,1)x(1,0,1,24), escala 0-1, tope por defecto de iteraciones."""
    from statsmodels.tsa.arima.model import ARIMA

    res = ARIMA(pasado.interpolate(limit=3), order=(1, 1, 1), seasonal_order=(1, 0, 1, 24)).fit(low_memory=True)
    return res.get_forecast(steps=horizon).predicted_mean.values, bool((res.mle_retvals or {}).get("converged"))


def evaluate(
    series: pd.Series,
    cutoffs: List[pd.Timestamp],
    horizon: int = 24,
    include_legacy: bool = False,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Tuple[pd.DataFrame, Dict[str, List[bool]]]:
    """Error de cada modelo en cada corte. Devuelve (DataFrame corte/modelo/n/mae/rmse, banderas de convergencia)."""
    filas, conv = [], {SARIMA: []}
    if include_legacy:
        conv[LEGACY] = []
    for i, d in enumerate(cutoffs):
        pasado = series[: d - pd.Timedelta(hours=1)]
        real = series.reindex(pd.date_range(d, periods=horizon, freq="1h", tz="UTC")).values
        ok = ~np.isnan(real)
        preds = baseline_forecasts(series, d, horizon)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                fc = forecasting.forecast_sarima(pasado, steps=horizon)
                preds[SARIMA], converged = fc["mean"].values, fc["converged"]
            except Exception:
                preds[SARIMA], converged = np.full(horizon, np.nan), False
            conv[SARIMA].append(converged)
            if include_legacy:
                try:
                    preds[LEGACY], c = _legacy_forecast(pasado, horizon)
                except Exception:
                    preds[LEGACY], c = np.full(horizon, np.nan), False
                conv[LEGACY].append(c)
        for nombre, p in preds.items():
            e = np.asarray(p, dtype=float)[ok] - real[ok]
            filas.append(
                {
                    "corte": d.strftime("%Y-%m-%d"),
                    "modelo": nombre,
                    "n": int(ok.sum()),
                    "mae": float(np.mean(np.abs(e))),
                    "rmse": float(np.sqrt(np.mean(e**2))),
                }
            )
        if progress:
            progress(i + 1, len(cutoffs))
    return pd.DataFrame(filas), conv


def summarize(results: pd.DataFrame) -> pd.DataFrame:
    """Tabla por modelo: MAE y RMSE medios, y la diferencia PAREADA de MAE frente al perfil horario con su IC 95 %."""
    pivot = results.pivot(index="corte", columns="modelo", values="mae")
    base = pivot[PERFIL]
    filas = []
    for modelo in pivot.columns:
        g = results[results["modelo"] == modelo]
        fila = {"modelo": modelo, "MAE": g["mae"].mean(), "RMSE": g["rmse"].mean()}
        if modelo != PERFIL:
            dif = (pivot[modelo] - base).dropna()
            se = dif.std(ddof=1) / np.sqrt(len(dif)) if len(dif) > 1 else np.nan
            fila.update(
                {
                    "dif_vs_perfil": dif.mean(),
                    "ic95": 1.96 * se,
                    "gana_al_perfil": int((dif < 0).sum()),
                    "cortes": len(dif),
                }
            )
            if np.isnan(se):
                fila["veredicto"] = "sin datos suficientes"
            elif abs(dif.mean()) <= 1.96 * se:
                fila["veredicto"] = "indistinguible del perfil"
            else:
                fila["veredicto"] = "PEOR que el perfil" if dif.mean() > 0 else "MEJOR que el perfil"
        filas.append(fila)
    return pd.DataFrame(filas).sort_values("MAE").reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB), help=f"ruta de la base (default: {DEFAULT_DB})")
    ap.add_argument("--max-cuts", type=int, default=None, help="limita el número de cortes (repartidos por el periodo)")
    ap.add_argument("--include-legacy", action="store_true", help="añade el ARIMA anterior (no converge) para comparar")
    args = ap.parse_args(argv)

    series = load_hourly_share(Path(args.db))
    cortes = eligible_cutoffs(series)
    if not cortes:
        print("No hay cortes elegibles: faltan datos.", file=sys.stderr)
        return 1
    if args.max_cuts and args.max_cuts < len(cortes):
        paso = len(cortes) / args.max_cuts
        cortes = [cortes[int(i * paso)] for i in range(args.max_cuts)]
    print(
        f"Serie: {len(series)} horas, {int(series.notna().sum())} con dato | cortes: {len(cortes)} "
        f"({cortes[0]:%Y-%m-%d} a {cortes[-1]:%Y-%m-%d}) | horizonte 24 h"
    )

    t0 = time.perf_counter()
    results, conv = evaluate(
        series,
        cortes,
        include_legacy=args.include_legacy,
        progress=lambda i, n: print(f"\r   corte {i}/{n}", end="", flush=True),
    )
    print(f"\r   evaluación: {time.perf_counter() - t0:.0f} s{' ' * 20}")

    tabla = summarize(results)
    print("\nError sobre las horas observadas, en puntos de proporción 0-1 (menos es mejor):")
    for _, r in tabla.iterrows():
        extra = (
            f" | vs perfil {r['dif_vs_perfil']:+.4f} ± {r['ic95']:.4f}, gana en {int(r['gana_al_perfil'])}/{int(r['cortes'])}: {r['veredicto']}"
            if "dif_vs_perfil" in r and not pd.isna(r.get("dif_vs_perfil"))
            else " | (referencia)"
        )
        print(f"   {r['modelo']:55} MAE={r['MAE']:.4f}  RMSE={r['RMSE']:.4f}{extra}")
    print("\nConvergencia:")
    for m, v in conv.items():
        print(f"   {m:55} {sum(v)}/{len(v)} cortes")
    print(f"\nEscala de referencia: la serie tiene media {series.mean():.3f} y desviación típica {series.std():.3f}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
