"""Pruebas de tools/check_collection_gaps.py (detección de huecos de recolección)."""

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# tools/ no es un paquete (no tiene __init__.py): se carga el script por ruta.
_spec = importlib.util.spec_from_file_location("check_collection_gaps", ROOT / "tools" / "check_collection_gaps.py")
gaps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gaps)

H = pd.Timedelta(hours=1)
T0 = pd.Timestamp("2026-10-01 00:00", tz="UTC")


def _serie(*offsets_h):
    return pd.Series([T0 + h * H for h in offsets_h])


def test_find_gaps_detecta_solo_pausas_mayores_al_umbral():
    # ciclos cada 15 min durante 1 h, luego 5 h de silencio, luego otro ciclo
    """`find_gaps` detecta solo las pausas mayores que el umbral: ciclos cada 15 minutos y 5 horas de silencio dan un único hueco."""
    t = pd.Series([T0, T0 + 0.25 * H, T0 + 0.5 * H, T0 + 0.75 * H, T0 + 1 * H, T0 + 6 * H])
    g = gaps.find_gaps(t, pd.Timedelta(hours=2))
    assert len(g) == 1
    assert g.iloc[0]["duration"] == pd.Timedelta(hours=5)
    assert pd.Timestamp(g.iloc[0]["start"], tz="UTC") == T0 + 1 * H


def test_find_gaps_sin_huecos():
    """Sin pausas mayores que el umbral, `find_gaps` devuelve una tabla vacía."""
    g = gaps.find_gaps(_serie(0, 0.5, 1.0, 1.5), pd.Timedelta(hours=2))
    assert g.empty


def test_find_gaps_ignora_duplicados_y_orden():
    # las filas de un mismo ciclo comparten instante; el orden de entrada no importa
    """Las filas de un mismo ciclo comparten instante y el orden de entrada no importa para detectar huecos."""
    g = gaps.find_gaps(_serie(6, 0, 0, 0, 1), pd.Timedelta(hours=2))
    assert len(g) == 1 and g.iloc[0]["duration"] == pd.Timedelta(hours=5)


def test_find_gaps_con_menos_de_dos_instantes():
    """Con menos de dos instantes distintos no puede haber huecos."""
    assert gaps.find_gaps(_serie(0), pd.Timedelta(hours=2)).empty
    assert gaps.find_gaps(_serie(), pd.Timedelta(hours=2)).empty


def test_fmt_h():
    """`fmt_h` da horas para una duración corta (3 h se muestra «3.0 h») y días para una larga (72 h se muestra «3.0 días»)."""
    assert gaps.fmt_h(pd.Timedelta(hours=3)) == "3.0 h"
    assert gaps.fmt_h(pd.Timedelta(hours=72)) == "3.0 días"


def _db_con_ciclos(tmp_path, ciclos):
    """Crea un mobility.db mínimo con las columnas que lee la herramienta."""
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE route_measurements (timestamp TEXT, data_source TEXT)")
    conn.executemany("INSERT INTO route_measurements VALUES (?, ?)", ciclos)
    conn.commit()
    conn.close()
    return path


def test_load_cycle_times_filtra_por_fecha_y_descarta_timestamps_invalidos(tmp_path):
    """`load_cycle_times` descarta lo anterior a la fecha de inicio y los timestamps que no son fechas."""
    path = _db_con_ciclos(
        tmp_path,
        [
            ((T0 - 100 * H).isoformat(), "ors"),  # antes de la ventana
            ((T0 + 1 * H).isoformat(), "ors"),
            ("no-es-una-fecha", "tomtom"),  # inválido
        ],
    )
    df = gaps.load_cycle_times(path, since=T0)
    assert len(df) == 1 and df.iloc[0]["data_source"] == "ors"


def test_load_cycle_times_es_de_solo_lectura(tmp_path):
    """`load_cycle_times` no modifica la base de datos."""
    path = _db_con_ciclos(tmp_path, [(T0.isoformat(), "ors")])
    gaps.load_cycle_times(path, since=T0 - H)
    # la base queda intacta y sin archivos auxiliares de escritura
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM route_measurements").fetchone()[0] == 1
    conn.close()


def test_report_avisa_si_ahora_mismo_no_llega_trafico():
    """El informe avisa «AHORA MISMO» si el último dato es antiguo y devuelve su edad."""
    df = pd.DataFrame({"ts": [T0, T0 + 1 * H], "data_source": ["ors", "ors"]})
    salida = []
    now = T0 + 30 * H  # 29 h después del último dato
    r = gaps.report(df, now, days=30, min_gap=pd.Timedelta(hours=2), out=salida.append)
    assert any("AHORA MISMO" in linea for linea in salida)
    assert r["age"] == pd.Timedelta(hours=29)


def test_report_mide_el_tiempo_total_sin_datos():
    """El informe cuenta los huecos y suma el tiempo total sin datos, sin avisar de sequía actual si los datos son recientes."""
    df = pd.DataFrame(
        {
            "ts": [T0, T0 + 1 * H, T0 + 11 * H, T0 + 12 * H],  # un hueco de 10 h
            "data_source": ["ors"] * 4,
        }
    )
    salida = []
    r = gaps.report(df, T0 + 12 * H, days=30, min_gap=pd.Timedelta(hours=2), out=salida.append)
    assert r["gaps"] == 1
    assert r["missing"] == pd.Timedelta(hours=10)
    assert not any("AHORA MISMO" in linea for linea in salida)


def test_report_sin_datos():
    """Sin datos, el informe devuelve cero huecos y escribe «Sin datos»."""
    salida = []
    r = gaps.report(
        pd.DataFrame(columns=["ts", "data_source"]), T0, days=30, min_gap=pd.Timedelta(hours=2), out=salida.append
    )
    assert r == {"gaps": 0}
    assert "Sin datos" in salida[0]
