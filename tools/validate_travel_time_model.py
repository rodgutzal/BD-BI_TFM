"""
Valida el modelo simple por ruta (TravelTimePredictor) con un CORTE CRONOLÓGICO: se entrena con el 80 % más antiguo de
cada ruta y se mide el error absoluto medio (MAE, en minutos) sobre el 20 % más reciente.

Compara el modelo con referencias triviales (media de entrenamiento, último valor de la MISMA fuente de datos y tiempo
sin tráfico) y, con `--incluir-version-anterior`, con la construcción antigua de la variable `travel_time_min_lag`, que
FILTRABA EL OBJETIVO: promediaba 5 filas que incluían la medición que se quiere predecir (y, al llegar las filas de la
más reciente a la más antigua, también mediciones posteriores). Con ella el error parecía menor de lo que es.

Es de SOLO LECTURA: abre la base con `immutable=1`. Con el stack apagado.

Uso (desde la raíz del proyecto):
    python tools/validate_travel_time_model.py
    python tools/validate_travel_time_model.py --incluir-version-anterior
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models.travel_time_model import TravelTimePredictor  # noqa: E402

DEFAULT_DB = ROOT / "data" / "mobility.db"
MIN_FILAS = 400
FRACCION_ENTRENAMIENTO = 0.8
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


def features_version_anterior(d: pd.DataFrame):
    """La construcción ANTERIOR (con fuga), solo para comparar: filas de la más reciente a la más antigua y media de 5
    filas que incluye la actual. NO se usa en el modelo."""
    d = d.sort_values("timestamp", ascending=False)
    X = pd.DataFrame(
        {
            "hour_of_day": d["timestamp"].dt.hour,
            "day_of_week": d["timestamp"].dt.dayofweek,
            "temperature": d["origin_temperature"],
            "humidity": d["origin_humidity"],
            "no_traffic_time_min": d["no_traffic_time_min"],
        },
        index=d.index,
    )
    X["travel_time_min_lag"] = d["travel_time_min"].rolling(5, min_periods=1).mean()
    return X.fillna(0), d["travel_time_min"]


def _ajustar_y_predecir(X_ent: pd.DataFrame, y_ent, X_test: pd.DataFrame) -> np.ndarray:
    modelo = TravelTimePredictor()
    modelo.fit_features(X_ent, y_ent)
    return modelo.model.predict(modelo.scaler.transform(X_test))


def evaluate_route(g: pd.DataFrame, incluir_anterior: bool = False) -> Optional[Dict[str, float]]:
    """MAE de cada método sobre el 20 % más reciente de una ruta. None si hay pocas filas."""
    g = g.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if len(g) < MIN_FILAS:
        return None
    corte = int(len(g) * FRACCION_ENTRENAMIENTO)
    ent, prueba = g.iloc[:corte], g.iloc[corte:]
    real = prueba["travel_time_min"]
    # Variables de TODA la serie (el lag necesita la historia), pero el ajuste solo ve la parte antigua.
    X, y = TravelTimePredictor().prepare_features(g)
    res = {
        "n_prueba": float(len(prueba)),
        "modelo": float(
            np.mean(np.abs(_ajustar_y_predecir(X.loc[ent.index], y.loc[ent.index], X.loc[prueba.index]) - real))
        ),
    }
    if incluir_anterior:
        Xa_ent, ya_ent = features_version_anterior(ent)
        Xa_test, ya_test = features_version_anterior(prueba)
        res["version_anterior"] = float(np.mean(np.abs(_ajustar_y_predecir(Xa_ent, ya_ent, Xa_test) - ya_test)))
    res["media_entrenamiento"] = float(np.mean(np.abs(ent["travel_time_min"].mean() - real)))
    ultimo = g.groupby("data_source")["travel_time_min"].shift(1).loc[prueba.index]
    res["ultimo_misma_fuente"] = (
        float(np.mean(np.abs(ultimo - real).dropna())) if ultimo.notna().any() else float("nan")
    )
    sin_trafico = prueba["no_traffic_time_min"]
    res["sin_trafico"] = (
        float(np.mean(np.abs(sin_trafico - real).dropna())) if sin_trafico.notna().any() else float("nan")
    )
    return res


def summarize(resultados: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    """Tabla ruta × método (más una fila 'MEDIA' entre rutas, sin ponderar)."""
    tabla = pd.DataFrame(resultados).T.drop(columns="n_prueba")
    tabla.loc["MEDIA"] = tabla.mean()
    return tabla


def verdict(tabla: pd.DataFrame) -> str:
    """¿El modelo mejora a la referencia JUSTA, repetir la última medición de la misma fuente? Compara la media entre
    rutas y cuenta en cuántas rutas gana."""
    rutas = tabla.drop(index="MEDIA")
    gana = int((rutas["modelo"] < rutas["ultimo_misma_fuente"]).sum())
    m = tabla.loc["MEDIA"]
    if m["modelo"] < m["ultimo_misma_fuente"]:
        return (
            f"VEREDICTO: el modelo ({m['modelo']:.3f}) mejora a repetir la última medición de la misma fuente "
            f"({m['ultimo_misma_fuente']:.3f}); gana en {gana} de {len(rutas)} rutas."
        )
    return (
        f"VEREDICTO: el modelo ({m['modelo']:.3f}) NO mejora a repetir la última medición de la misma fuente "
        f"({m['ultimo_misma_fuente']:.3f}); gana en {gana} de {len(rutas)} rutas. No aporta información sobre la persistencia."
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB), help=f"ruta de la base (default: {DEFAULT_DB})")
    ap.add_argument(
        "--incluir-version-anterior",
        action="store_true",
        help="añade la construcción antigua del lag (con fuga) para ver cuánto engañaba",
    )
    args = ap.parse_args(argv)

    df = load_measurements(args.db)
    resultados = {}
    for (origen, destino), g in df.groupby(["origin", "destination"]):
        r = evaluate_route(g, args.incluir_version_anterior)
        if r:
            resultados[f"{origen}>{destino}"] = r
    if not resultados:
        print(f"Ninguna ruta tiene al menos {MIN_FILAS} mediciones.", file=sys.stderr)
        return 1
    tabla = summarize(resultados)
    print(
        f"Corte cronológico: entrenar con el {FRACCION_ENTRENAMIENTO:.0%} más antiguo de cada ruta, medir en el resto. "
        f"MAE en minutos (menos es mejor). {len(resultados)} rutas.\n"
    )
    print(tabla.round(3).to_string())
    m = tabla.loc["MEDIA"]
    print(f"\nMODELO (lag sin fuga): {m['modelo']:.3f} min de error medio.")
    if "version_anterior" in m:
        print(
            f"Versión anterior (lag CON fuga): {m['version_anterior']:.3f} min. La fuga hacía parecer el error "
            f"{1 - m['version_anterior'] / m['modelo']:.0%} menor de lo que es."
        )
    print(verdict(tabla))
    print(
        "\nAVISO al leer las referencias: la base mezcla dos fuentes (ORS, sin tráfico; TomTom, con él) y el modelo no recibe "
        "la fuente como variable. Las referencias ingenuas que no la distinguen (media, tiempo sin tráfico) salen muy mal "
        "por eso, no porque el modelo sea una maravilla."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
