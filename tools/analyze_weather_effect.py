"""
¿Se asocia el tiempo (temperatura) con el tiempo de viaje, una vez comparadas situaciones comparables?

Con los datos reales (solo lectura: `immutable=1`) compara, para el tratamiento «más calor de lo habitual para esa hora
y esa semana»:
  1. la diferencia SIN ajustar (mezcla el tiempo con la ruta y la hora);
  2. la ESTRATIFICACIÓN EXACTA, con varias especificaciones de estratos (el estimador principal);
  3. el propensity-score matching, con su diagnóstico de equilibrio (un contraste, no el estimador principal);
  4. como demostración, el mismo emparejamiento con el tratamiento ingenuo «por encima de la mediana global», que no se
     puede equilibrar.
Todos son ASOCIACIONES ajustadas por lo medido, no prueba de causalidad (no controlan lluvia, eventos, obras...).

Uso (desde la raíz del proyecto):
    python tools/analyze_weather_effect.py
    python tools/analyze_weather_effect.py --boot 100      # más rápido
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analytics.causal_analysis import CausalAnalysis  # noqa: E402

DEFAULT_DB = ROOT / "data" / "mobility.db"
COLUMNAS = "timestamp, origin, destination, data_source, travel_time_min, origin_temperature"
ROUTE = ["origin", "destination", "data_source"]
ESPECIFICACIONES = [
    ("ruta + fuente", ROUTE),
    ("ruta + fuente + hora", ROUTE + ["hour"]),
    ("ruta + fuente + semana", ROUTE + ["week"]),
    ("ruta + fuente + hora + semana (defecto)", None),
    ("SIN ruta: fuente + hora + semana", ["data_source", "hour", "week"]),
]


def load_measurements(db_path) -> pd.DataFrame:
    """Mediciones con tiempo de viaje y temperatura (sin la columna polyline), en solo lectura."""
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?immutable=1", uri=True)
    try:
        return pd.read_sql_query(
            f"SELECT {COLUMNAS} FROM route_measurements WHERE travel_time_min IS NOT NULL AND origin_temperature IS NOT NULL",
            conn,
        )
    finally:
        conn.close()


def _fila(etiqueta: str, r: dict) -> str:
    if "error" in r:
        return f"   {etiqueta:42} (no calculable: {r['error']})"
    extra = (
        f" | equilibrio {r['balance']['quality']} (SMD máx. {r['balance']['max_abs_smd_after']:.2f})"
        if "balance" in r
        else ""
    )
    usado = r.get("share_used", r.get("share_matched", 1.0))
    return (
        f"   {etiqueta:42} {r['att']:+.3f} min  IC95 [{r['ci_95'][0]:+.3f}, {r['ci_95'][1]:+.3f}]  "
        f"{'excluye 0' if r['ci_excludes_zero'] else 'incluye 0 '}  usa {usado:.0%}{extra}"
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB), help=f"ruta de la base (default: {DEFAULT_DB})")
    ap.add_argument("--boot", type=int, default=300, help="remuestreos del bootstrap por días")
    args = ap.parse_args(argv)

    df = load_measurements(args.db)
    if len(df) < 100:
        print("Hay muy pocas mediciones con temperatura.", file=sys.stderr)
        return 1
    ca = CausalAnalysis(df)
    print(
        f"Mediciones: {len(df):,} | rutas: {df.groupby(['origin', 'destination']).ngroups} | fuentes: {sorted(df['data_source'].unique())}"
    )
    print(
        "Tratamiento: temperatura por encima de la mediana de SU hora y semana ('más calor de lo habitual'). Resultado: minutos de viaje.\n"
    )

    print(
        "1. ESTRATIFICACIÓN EXACTA (estimador principal): cada medición cálida frente a las no cálidas de su mismo estrato"
    )
    primero = None
    for etiqueta, estratos in ESPECIFICACIONES:
        r = ca.stratified_adjusted(strata=estratos, n_boot=args.boot)
        primero = primero or r
        print(_fila(etiqueta, r))
    if primero and "naive_difference" in primero:
        print(f"   {'SIN AJUSTAR (cálida − no cálida)':42} {primero['naive_difference']:+.3f} min")

    print("\n2. PROPENSITY-SCORE MATCHING (contraste, con diagnóstico de equilibrio)")
    print(_fila("emparejamiento exacto en ruta y fuente", ca.propensity_score_matching(n_boot=args.boot)))
    print(
        _fila(
            "mismo, con tratamiento 'mediana global' (demo)",
            ca.propensity_score_matching(treatment="above_median", n_boot=args.boot),
        )
    )
    print(
        "\nLECTURA: si la estratificación con la ruta da ~0 y la que NO la incluye da un valor grande, la diferencia sin ajustar es "
        "confusión por la ruta (la temperatura se mide en el origen de cada ruta), no un efecto del calor. El PSM es menos estable: con un "
        "propensity score casi constante empareja de forma casi aleatoria y su equilibrio puede ser pobre; por eso no es el estimador principal."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
