"""Tests del pronóstico horario (src/forecasting.py) y de su validación (tools/validate_forecast.py)."""

import sqlite3
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib.util  # noqa: E402

from src import forecasting  # noqa: E402

# tools/ no es un paquete (no tiene __init__.py): se carga el script por ruta.
_spec = importlib.util.spec_from_file_location("validate_forecast", ROOT / "tools" / "validate_forecast.py")
vf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vf)


def _serie(dias=30, huecos=True, ruido=0.01, seed=0):
    """Serie horaria con ciclo diario claro y, opcionalmente, 'noches apagadas' como NaN."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-09-01", periods=dias * 24, freq="1h", tz="UTC")
    base = 0.25 + 0.10 * np.sin((idx.hour - 9) / 24 * 2 * np.pi)
    s = pd.Series(base + rng.normal(0, ruido, len(idx)), index=idx)
    if huecos:
        # 3 horas seguidas: es lo que se interpola (max_gap_hours=3). Una hora que NUNCA se observa en
        # ningún día no se puede pronosticar (con diferenciación estacional sale ~0): limitación conocida.
        s[(idx.hour >= 1) & (idx.hour <= 3)] = np.nan
    return s


def test_el_sarima_converge_y_pronostica_en_escala_original():
    """El pronóstico a 24 h converge (antes no lo hacía), queda en la escala 0-1 y el IC lo envuelve."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")           # un ConvergenceWarning haría fallar el test
        fc = forecasting.forecast_sarima(_serie())
    assert fc["converged"] is True
    assert len(fc["mean"]) == 24 and fc["mean"].between(0, 0.6).all()
    assert (fc["ci"].iloc[:, 0] <= fc["mean"]).all() and (fc["mean"] <= fc["ci"].iloc[:, 1]).all()


def test_el_sarima_aprende_el_ciclo_diario():
    """Con un ciclo diario claro, el pronóstico sigue el perfil mejor que una media plana."""
    s = _serie(dias=30, ruido=0.005)
    fc = forecasting.forecast_sarima(s)
    horizonte = fc["mean"].index
    real = 0.25 + 0.10 * np.sin((horizonte.hour - 9) / 24 * 2 * np.pi)
    assert forecasting.mae(fc["mean"].values, real) < forecasting.mae(np.full(24, s.mean()), real)


def test_las_horas_sin_dato_no_se_inventan():
    """hourly_share deja NaN en las horas sin mediciones; solo se interpolan huecos cortos al ajustar."""
    ts = pd.to_datetime(["2026-09-01 00:10", "2026-09-01 00:40", "2026-09-01 05:20"], utc=True)
    s = forecasting.hourly_share(pd.Series([1, 0, 1], index=ts))
    assert s.iloc[0] == 0.5 and s.iloc[5] == 1.0
    assert s.iloc[1:5].isna().all() and len(s) == 6


def test_perfil_horario_y_su_pronostico():
    """La referencia usa la media de cada hora del día; para una hora sin historia cae a la media global."""
    idx = pd.date_range("2026-09-01", periods=48, freq="1h", tz="UTC")
    s = pd.Series(np.where(idx.hour == 3, 0.4, 0.1), index=idx)
    s[idx.hour == 7] = np.nan
    perfil = forecasting.hourly_profile(s)
    assert perfil[3] == pytest.approx(0.4) and 7 not in perfil.index
    horizonte = pd.date_range("2026-09-03", periods=24, freq="1h", tz="UTC")
    p = forecasting.profile_forecast(s, horizonte)
    assert p[horizonte[3]] == pytest.approx(0.4)
    assert p[horizonte[7]] == pytest.approx(s.dropna().mean())


def test_mae_ignora_las_posiciones_sin_dato():
    """El MAE salta las posiciones con NaN y devuelve `None` si no queda ninguna con dato."""
    assert forecasting.mae([1, 2, 3], [1, np.nan, 5]) == pytest.approx(1.0)
    assert forecasting.mae([1, 2], [np.nan, np.nan]) is None


def test_los_cortes_exigen_horizonte_y_pasado_con_datos():
    """Un corte de validación exige una semana de pasado con datos y un horizonte que no esté vacío; si el horizonte queda en NaN deja de ser elegible."""
    s = _serie(dias=20, huecos=False)
    cortes = vf.eligible_cutoffs(s, min_train_obs=168)
    assert cortes and cortes[0] >= s.index[0] + pd.Timedelta(days=7)      # hace falta una semana de pasado
    s2 = s.copy()
    s2[cortes[-1]:cortes[-1] + pd.Timedelta(hours=23)] = np.nan            # horizonte vacío -> deja de ser elegible
    assert cortes[-1] not in vf.eligible_cutoffs(s2, min_train_obs=168)


def test_las_referencias_no_usan_datos_del_futuro():
    """Cambiar los valores a partir del corte no debe alterar ninguna referencia."""
    s = _serie(dias=15, huecos=False)
    corte = s.index[10 * 24]
    antes = vf.baseline_forecasts(s, corte)
    s_alterada = s.copy()
    s_alterada[corte:] = 99.0
    despues = vf.baseline_forecasts(s_alterada, corte)
    for nombre in antes:
        np.testing.assert_allclose(antes[nombre], despues[nombre], err_msg=nombre)


def test_la_validacion_compara_con_las_referencias(capsys):
    """evaluate + summarize: con un ciclo diario limpio el perfil y el SARIMA ganan a media y persistencia."""
    s = _serie(dias=16, huecos=False, ruido=0.005)
    cortes = vf.eligible_cutoffs(s, min_train_obs=168)[-2:]
    res, conv = vf.evaluate(s, cortes)
    # Aquí NO se exige que converja: eso lo comprueba test_el_sarima_converge..., y con estos datos casi sin
    # ruido el resultado del optimizador depende de las versiones de scipy/statsmodels (en el CI uno de los
    # dos cortes no convergió aunque en local siempre sí). Solo se comprueba que se registra por corte.
    assert len(conv[vf.SARIMA]) == 2 and all(isinstance(c, bool) for c in conv[vf.SARIMA])
    tabla = vf.summarize(res).set_index("modelo")
    assert tabla.loc[vf.PERFIL, "MAE"] < tabla.loc[vf.MEDIA, "MAE"] < tabla.loc[vf.PERSISTENCIA, "MAE"]
    assert tabla.loc[vf.SARIMA, "MAE"] < tabla.loc[vf.MEDIA, "MAE"]
    assert tabla.loc[vf.MEDIA, "veredicto"] in {"PEOR que el perfil", "indistinguible del perfil"}


def test_la_validacion_lee_la_base_en_solo_lectura(tmp_path):
    """load_hourly_share abre la base con immutable=1: no crea -wal/-shm ni modifica el archivo."""
    db = tmp_path / "m.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE route_measurements (timestamp TEXT, mobility_level TEXT)")
    con.executemany("INSERT INTO route_measurements VALUES (?, ?)", [
        ("2026-09-01T00:10:00+00:00", "Alta demora"), ("2026-09-01T00:40:00+00:00", "Normal"),
        ("2026-09-01T02:10:00+00:00", "Normal"), ("2026-07-01T00:00:00+00:00", "Alta demora")])
    con.commit()
    con.close()
    antes = db.read_bytes()
    s = vf.load_hourly_share(db)                      # el registro de julio queda fuera (>= 2026-08-01)
    assert s.iloc[0] == 0.5 and s.iloc[2] == 0.0 and s.iloc[1] != s.iloc[1]
    assert db.read_bytes() == antes
    assert sorted(p.name for p in tmp_path.iterdir()) == ["m.db"]
