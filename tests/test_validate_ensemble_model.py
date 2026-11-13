"""Tests de tools/validate_ensemble_model.py: validación fuera de muestra del ensemble por ruta, y la demostración de que la
R² en muestra (la que se informaba antes) engaña."""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("validate_ensemble_model", ROOT / "tools" / "validate_ensemble_model.py")
ve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ve)


def _ruta(n=500, seed=0, origen="Msida", destino="Gzira"):
    """Una ruta con ruido puro alrededor de 12 min: ni las variables ni el pasado ayudan a predecir."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-09-01", periods=n, freq="30min", tz="UTC"),
            "origin": origen,
            "destination": destino,
            "data_source": "tomtom",
            "travel_time_min": 12 + rng.normal(0, 3, n),
            "no_traffic_time_min": rng.uniform(10, 15, n),
            "origin_temperature": 20 + rng.normal(0, 1, n),
            "origin_humidity": 50 + rng.normal(0, 3, n),
        }
    )


def _db(ruta_db, df):
    con = sqlite3.connect(ruta_db)
    con.execute(
        "CREATE TABLE route_measurements (timestamp TEXT, origin TEXT, destination TEXT, data_source TEXT, "
        "travel_time_min REAL, no_traffic_time_min REAL, origin_temperature REAL, origin_humidity REAL, polyline TEXT)"
    )
    d = df.assign(timestamp=df["timestamp"].map(lambda t: t.isoformat()), polyline="x" * 50)
    d.to_sql("route_measurements", con, if_exists="append", index=False)
    con.close()


def test_evaluate_route_devuelve_las_metricas_y_mide_el_20_por_ciento_mas_reciente():
    """Devuelve R² en y fuera de muestra, el MAE del ensemble y el de las dos referencias, sobre el 20 % más reciente."""
    r = ve.evaluate_route(_ruta(n=500))
    assert {"n_prueba", "r2_en_muestra", "r2_fuera", "mae_ensemble", "mae_ultimo_valor", "mae_media"} <= set(r)
    assert r["n_prueba"] == 100


def test_las_rutas_con_pocas_filas_se_omiten():
    """Una ruta con menos filas que el mínimo no se evalúa."""
    assert ve.evaluate_route(_ruta(n=ve.MIN_FILAS - 1)) is None


def test_con_ruido_puro_la_r2_en_muestra_es_mayor_que_la_de_fuera_de_muestra():
    """La demostración: la R² en muestra (la que se informaba antes) supera a la honesta, que con ruido no pasa de ~0."""
    r = ve.evaluate_route(_ruta())
    assert r["r2_en_muestra"] > r["r2_fuera"] + 0.2
    assert r["r2_fuera"] < 0.1


def test_el_orden_de_las_filas_de_entrada_no_cambia_el_resultado():
    """La base entrega las filas de la más reciente a la más antigua; el corte las ordena, así que el resultado no
    depende del orden de entrada (con tolerancia: los bosques multihilo suman en un orden que varía)."""
    datos = _ruta()
    a = ve.evaluate_route(datos)
    b = ve.evaluate_route(datos.iloc[::-1])
    for clave in a:
        assert a[clave] == pytest.approx(b[clave], abs=1e-9)


def test_summarize_anade_la_fila_media_sin_ponderar():
    """La tabla trae una fila por ruta y una fila MEDIA con el promedio simple entre rutas."""
    tabla = ve.summarize({"A>B": ve.evaluate_route(_ruta(seed=1)), "C>D": ve.evaluate_route(_ruta(seed=2))})
    assert list(tabla.index) == ["A>B", "C>D", "MEDIA"] and "n_prueba" not in tabla.columns
    assert tabla.loc["MEDIA", "mae_ensemble"] == pytest.approx(tabla.loc[["A>B", "C>D"], "mae_ensemble"].mean())


def _tabla(mae_ensemble, mae_ultimo):
    filas = {
        f"R{i}": {"r2_en_muestra": 0.3, "r2_fuera": 0.1, "mae_ensemble": e, "mae_ultimo_valor": u, "mae_media": 2.0}
        for i, (e, u) in enumerate(zip(mae_ensemble, mae_ultimo))
    }
    return ve.summarize({k: {**v, "n_prueba": 1.0} for k, v in filas.items()})


def test_el_veredicto_dice_que_no_mejora_si_pierde_frente_a_repetir_la_ultima_medicion():
    """Si el ensemble tiene más error que repetir la última medición de la misma fuente, el veredicto lo dice y cuenta
    en cuántas rutas gana."""
    texto = ve.verdict(_tabla([1.5, 0.5, 2.0], [0.2, 0.9, 0.3]))
    assert "NO mejora" in texto and "gana en 1 de 3 rutas" in texto


def test_el_veredicto_dice_que_mejora_si_gana_en_la_media():
    """Si el ensemble tiene menos error medio que la referencia, el veredicto dice que mejora."""
    texto = ve.verdict(_tabla([0.1, 0.1], [0.5, 0.4]))
    assert "mejora a repetir" in texto and "NO mejora" not in texto and "gana en 2 de 2 rutas" in texto


def test_main_es_de_solo_lectura_y_muestra_las_dos_r2(tmp_path, capsys):
    """La herramienta no modifica la base ni crea archivos junto a ella, e imprime la R² en muestra, la de fuera y el
    veredicto."""
    base = tmp_path / "t.db"
    _db(base, _ruta(n=450))
    antes = base.read_bytes()
    assert ve.main(["--db", str(base)]) == 0
    salida = capsys.readouterr().out
    assert "EN MUESTRA" in salida and "FUERA DE MUESTRA" in salida and "VEREDICTO" in salida
    assert base.read_bytes() == antes and [p.name for p in tmp_path.iterdir()] == ["t.db"]


def test_main_sin_rutas_suficientes_devuelve_error(tmp_path, capsys):
    """Si ninguna ruta llega al mínimo de filas, devuelve 1 y lo dice."""
    base = tmp_path / "t.db"
    _db(base, _ruta(n=50))
    assert ve.main(["--db", str(base)]) == 1
    assert "Ninguna ruta" in capsys.readouterr().err
