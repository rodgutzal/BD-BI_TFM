"""Tests de tools/analyze_weather_effect.py: análisis del efecto asociado al tiempo sobre los datos de la base."""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("analyze_weather_effect", ROOT / "tools" / "analyze_weather_effect.py")
awe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(awe)


def _db(ruta_db, dias=25):
    """Dos rutas; la A sale de un origen más cálido y es más rápida (la ruta confunde), el calor no tiene efecto."""
    rng = np.random.default_rng(0)
    filas = []
    inicio = pd.Timestamp("2026-09-01", tz="UTC")
    for d in range(dias):
        anomalia_dia = rng.normal(0, 2)
        for h in range(24):
            ciclo = 8 * np.sin((h - 9) / 24 * 2 * np.pi)
            for ruta, signo in (("A", 1), ("B", -1)):
                filas.append(
                    (
                        (inicio + pd.Timedelta(days=d, hours=h)).isoformat(),
                        ruta,
                        "Z",
                        "tomtom",
                        12 - 4 * signo + rng.normal(0, 0.5),
                        20 + ciclo + anomalia_dia + rng.normal(0, 0.7) + 1.5 * signo,
                        "x" * 40,
                    )
                )
    con = sqlite3.connect(ruta_db)
    con.execute(
        "CREATE TABLE route_measurements (timestamp TEXT, origin TEXT, destination TEXT, data_source TEXT, "
        "travel_time_min REAL, origin_temperature REAL, polyline TEXT)"
    )
    con.executemany("INSERT INTO route_measurements VALUES (?,?,?,?,?,?,?)", filas)
    con.commit()
    con.close()


def test_la_herramienta_lee_en_solo_lectura_y_solo_las_columnas_necesarias(tmp_path):
    db = tmp_path / "t.db"
    _db(db, dias=3)
    antes = db.read_bytes()
    df = awe.load_measurements(db)
    assert "polyline" not in df.columns and len(df) == 3 * 24 * 2
    assert db.read_bytes() == antes and [p.name for p in tmp_path.iterdir()] == ["t.db"]


def test_ignora_las_filas_sin_temperatura_o_sin_tiempo_de_viaje(tmp_path):
    db = tmp_path / "t.db"
    _db(db, dias=2)
    con = sqlite3.connect(db)
    con.execute("UPDATE route_measurements SET origin_temperature = NULL WHERE rowid <= 5")
    con.execute("UPDATE route_measurements SET travel_time_min = NULL WHERE rowid BETWEEN 6 AND 8")
    con.commit()
    con.close()
    assert len(awe.load_measurements(db)) == 2 * 24 * 2 - 8


def test_el_informe_muestra_la_confusion_por_la_ruta_y_el_aviso_del_psm(tmp_path, capsys):
    db = tmp_path / "t.db"
    _db(db)
    assert awe.main(["--db", str(db), "--boot", "60"]) == 0
    salida = capsys.readouterr().out
    assert "ESTRATIFICACIÓN EXACTA" in salida and "PROPENSITY-SCORE MATCHING" in salida and "SIN AJUSTAR" in salida
    assert "SIN ruta" in salida and "LECTURA" in salida and "demo" in salida
    # con la ruta en los estratos el efecto es ~0; sin ella, la confusión por la ruta reaparece
    linea_con = next(
        linea for linea in salida.splitlines() if linea.strip().startswith("ruta + fuente + hora + semana")
    )
    linea_sin = next(linea for linea in salida.splitlines() if linea.strip().startswith("SIN ruta"))
    assert abs(float(linea_con.split("min")[0].split()[-1])) < 0.3
    assert float(linea_sin.split("min")[0].split()[-1]) < -3


def test_con_muy_pocas_mediciones_devuelve_error(tmp_path, capsys):
    db = tmp_path / "t.db"
    _db(db, dias=1)
    assert awe.main(["--db", str(db)]) == 1
    assert "muy pocas" in capsys.readouterr().err
