"""Tests de tools/validate_travel_time_model.py: validación cronológica del modelo simple por ruta, y la demostración
de que el `lag` antiguo filtraba el objetivo."""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "validate_travel_time_model", ROOT / "tools" / "validate_travel_time_model.py"
)
vt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vt)


def _ruta(n=600, seed=0, ruido=3.0):
    """Una ruta con ruido puro alrededor de 12 min (el pasado no ayuda a predecir el presente)."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-09-01", periods=n, freq="30min", tz="UTC"),
            "origin": "Msida",
            "destination": "Gzira",
            "data_source": "tomtom",
            "travel_time_min": 12 + rng.normal(0, ruido, n),
            "no_traffic_time_min": 11.0,
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


def test_la_construccion_antigua_filtraba_el_objetivo_y_la_nueva_no():
    """Con una serie de ruido puro nada del pasado predice el presente: un modelo honesto no puede ganar mucho a la
    media, pero el lag antiguo (que incluía la medición a predecir) daba un error artificialmente bajo."""
    r = vt.evaluate_route(_ruta(), incluir_anterior=True)
    assert r["version_anterior"] < 0.9 * r["modelo"]  # el objetivo pesa 1/5 en la media: ~15 % menos error
    assert r["modelo"] > 0.9 * r["media_entrenamiento"]  # sin fuga, no se «adivina» el ruido


def test_la_version_anterior_solo_se_calcula_si_se_pide():
    r = vt.evaluate_route(_ruta())
    assert "version_anterior" not in r and {
        "modelo",
        "media_entrenamiento",
        "ultimo_misma_fuente",
        "sin_trafico",
        "n_prueba",
    } <= set(r)


def test_las_rutas_con_pocas_filas_se_omiten():
    assert vt.evaluate_route(_ruta(n=vt.MIN_FILAS - 1)) is None


def test_el_corte_es_cronologico_se_mide_en_el_20_por_ciento_mas_reciente():
    r = vt.evaluate_route(_ruta(n=500))
    assert r["n_prueba"] == 100


def test_el_orden_de_las_filas_de_entrada_no_cambia_el_resultado():
    """Con tolerancia: el bosque aleatorio multihilo suma en un orden que varía y deja diferencias de ~1e-15 min entre
    ejecuciones idénticas (medido: en la mitad de ellas), así que una igualdad exacta fallaba al azar."""
    df = _ruta(n=500)
    a, b = vt.evaluate_route(df), vt.evaluate_route(df.iloc[::-1])
    assert a.keys() == b.keys()
    for clave in a:
        assert a[clave] == pytest.approx(b[clave], abs=1e-9)


def test_el_ultimo_valor_se_toma_de_la_misma_fuente():
    """Alternando fuentes con valores muy distintos, 'último de la misma fuente' acierta y 'último a secas' no."""
    n = 500
    df = _ruta(n=n, ruido=0.01)
    df["data_source"] = ["ors", "tomtom"] * (n // 2)
    df["travel_time_min"] = [10.0, 20.0] * (n // 2)
    assert vt.evaluate_route(df)["ultimo_misma_fuente"] < 0.1


def test_el_veredicto_depende_de_si_el_modelo_gana_a_la_persistencia():
    gana = pd.DataFrame({"modelo": [1.0, 1.0, 1.0], "ultimo_misma_fuente": [2.0, 2.0, 2.0]}, index=["a", "b", "MEDIA"])
    pierde = pd.DataFrame(
        {"modelo": [3.0, 3.0, 3.0], "ultimo_misma_fuente": [2.0, 2.0, 2.0]}, index=["a", "b", "MEDIA"]
    )
    assert "mejora a repetir" in vt.verdict(gana) and "gana en 2 de 2" in vt.verdict(gana)
    assert "NO mejora" in vt.verdict(pierde) and "gana en 0 de 2" in vt.verdict(pierde)


def test_la_herramienta_lee_en_solo_lectura_e_imprime_el_informe(tmp_path, capsys):
    db = tmp_path / "t.db"
    _db(db, _ruta())
    antes = db.read_bytes()
    assert vt.main(["--db", str(db), "--incluir-version-anterior"]) == 0
    salida = capsys.readouterr().out
    assert "Corte cronológico" in salida and "Msida>Gzira" in salida and "MEDIA" in salida
    assert "lag CON fuga" in salida and "VEREDICTO" in salida and "AVISO" in salida
    assert db.read_bytes() == antes and [p.name for p in tmp_path.iterdir()] == ["t.db"]


def test_sin_rutas_suficientes_devuelve_error(tmp_path, capsys):
    db = tmp_path / "t.db"
    _db(db, _ruta(n=50))
    assert vt.main(["--db", str(db)]) == 1
    assert "Ninguna ruta" in capsys.readouterr().err


def test_load_measurements_ignora_filas_sin_tiempo_de_viaje_y_parsea_fechas(tmp_path):
    df = _ruta(n=10)
    df.loc[3, "travel_time_min"] = np.nan
    db = tmp_path / "t.db"
    _db(db, df)
    cargado = vt.load_measurements(db)
    assert len(cargado) == 9 and str(cargado["timestamp"].dt.tz) == "UTC"
    assert "polyline" not in cargado.columns


def test_features_version_anterior_documenta_el_orden_y_la_inclusion_de_la_fila_actual():
    """La versión antigua (solo para comparar) ordena de la más reciente a la más antigua e incluye la fila actual."""
    df = _ruta(n=10)
    df["travel_time_min"] = np.arange(10.0)
    X, y = vt.features_version_anterior(df)
    assert X.index[0] == 9 and X["travel_time_min_lag"].iloc[0] == pytest.approx(9.0)  # solo la propia fila
    assert X["travel_time_min_lag"].iloc[1] == pytest.approx(8.5)  # (9 + 8) / 2: incluye la fila actual
