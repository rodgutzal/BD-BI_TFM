"""
Valida el ensemble por ruta (EnsemblePredictor) FUERA DE MUESTRA, con un corte cronológico: se entrena con el 80 % más
antiguo de cada ruta y se mide (R² y error absoluto medio, MAE, en minutos) sobre el 20 % más reciente.

Antes, `train()` devolvía como `r2` la R² calculada sobre los MISMOS datos con los que se ajustaba el modelo (en muestra):
mide lo bien que el modelo se aprende lo que ya vio, no si predice. Esta herramienta enseña las dos cifras, la antigua
(en muestra) y la honesta (fuera de muestra), junto a las referencias triviales: la media del tramo de entrenamiento y
repetir la última medición de la MISMA fuente de datos (ORS, sin tráfico, y TomTom, con él).

Es de SOLO LECTURA: abre la base con `immutable=1` y guarda los modelos de prueba en una carpeta temporal. Con el stack
apagado.

Uso (desde la raíz del proyecto):
    python tools/validate_ensemble_model.py
    python tools/validate_ensemble_model.py --db otra_base.sqlite
"""

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.ensemble_predictor import EnsemblePredictor  # noqa: E402

DEFAULT_DB = ROOT / "data" / "mobility.db"
MIN_FILAS = 400
COLUMNAS = "timestamp, origin, destination, data_source, travel_time_min, no_traffic_time_min, origin_temperature, origin_humidity"


def load_measurements(db_path) -> pd.DataFrame:
    """Mediciones (sin la columna polyline) en solo lectura."""
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?immutable=1", uri=True)
    try:
        df = pd.read_sql_query(f"SELECT {COLUMNAS} FROM route_measurements WHERE travel_time_min IS NOT NULL", conn)
    finally:
        conn.close()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    return df


def evaluate_route(g: pd.DataFrame) -> Optional[Dict[str, float]]:
    """Métricas de una ruta (entrenando con `EnsemblePredictor.train`, que hace el corte). None si hay pocas filas o no
    se pudo medir fuera de muestra."""
    if len(g) < MIN_FILAS:
        return None
    with tempfile.TemporaryDirectory() as carpeta:
        resultado = EnsemblePredictor("validacion", Path(carpeta)).train(g)
    fuera = resultado.get("holdout", {})
    if "ensemble" not in fuera:
        return None
    en_muestra = [m["r2_entrenamiento"] for m in resultado["models_trained"] if "r2_entrenamiento" in m]
    return {
        "n_prueba": float(fuera["n_prueba"]),
        "r2_en_muestra": float(np.mean(en_muestra)),
        "r2_fuera": fuera["ensemble"]["r2"],
        "mae_ensemble": fuera["ensemble"]["mae"],
        "mae_ultimo_valor": fuera["referencias"]["ultimo_valor"]["mae"],
        "mae_media": fuera["referencias"]["media_entrenamiento"]["mae"],
    }


def summarize(resultados: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    """Tabla ruta × métrica (más una fila 'MEDIA' entre rutas, sin ponderar)."""
    tabla = pd.DataFrame(resultados).T.drop(columns="n_prueba")
    tabla.loc["MEDIA"] = tabla.mean()
    return tabla


def verdict(tabla: pd.DataFrame) -> str:
    """¿El ensemble mejora a la referencia JUSTA, repetir la última medición de la misma fuente? Compara la media entre
    rutas y cuenta en cuántas rutas gana."""
    rutas = tabla.drop(index="MEDIA")
    gana = int((rutas["mae_ensemble"] < rutas["mae_ultimo_valor"]).sum())
    m = tabla.loc["MEDIA"]
    if m["mae_ensemble"] < m["mae_ultimo_valor"]:
        return (
            f"VEREDICTO: el ensemble ({m['mae_ensemble']:.3f} min) mejora a repetir la última medición de la misma "
            f"fuente ({m['mae_ultimo_valor']:.3f}); gana en {gana} de {len(rutas)} rutas."
        )
    return (
        f"VEREDICTO: el ensemble ({m['mae_ensemble']:.3f} min) NO mejora a repetir la última medición de la misma fuente "
        f"({m['mae_ultimo_valor']:.3f}); gana en {gana} de {len(rutas)} rutas. No aporta información sobre la persistencia."
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB), help=f"ruta de la base (default: {DEFAULT_DB})")
    args = ap.parse_args(argv)

    df = load_measurements(args.db)
    resultados = {}
    for (origen, destino), g in df.groupby(["origin", "destination"]):
        r = evaluate_route(g)
        if r:
            resultados[f"{origen}>{destino}"] = r
    if not resultados:
        print(f"Ninguna ruta tiene al menos {MIN_FILAS} mediciones.", file=sys.stderr)
        return 1
    tabla = summarize(resultados)
    print(
        "Corte cronológico: entrenar con el 80 % más antiguo de cada ruta, medir en el 20 % más reciente "
        f"({len(resultados)} rutas). R² (más es mejor) y MAE en minutos (menos es mejor).\n"
    )
    print(tabla.round(3).to_string())
    m = tabla.loc["MEDIA"]
    print(
        f"\nR² EN MUESTRA (la que se informaba antes como `r2`): {m['r2_en_muestra']:.3f}. "
        f"R² FUERA DE MUESTRA (la que mide si predice): {m['r2_fuera']:.3f}."
    )
    print(verdict(tabla))
    print(
        "\nAVISO al leer las referencias: la base mezcla dos fuentes (ORS, sin tráfico; TomTom, con él) y el ensemble no "
        "recibe la fuente como variable ni el valor anterior. La media sale mal por esa mezcla; repetir la última "
        "medición de la misma fuente es la referencia justa."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
