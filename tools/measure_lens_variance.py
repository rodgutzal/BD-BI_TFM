"""
Mide cuánto VARÍA cada lente (competencia, mercado, proveedores) entre las celdas de la rejilla, para cada perfil
de negocio por defecto. Una lente que casi no varía entre celdas no ayuda a decidir dónde abrir (por ejemplo, si
en una isla pequeña todas las celdas están a minutos de los mismos proveedores).

Es de SOLO LECTURA: abre la base con `immutable=1` (no crea archivos ni escribe, ni siquiera tablas vacías) y lee
únicamente la tabla `pois`. Con el stack apagado.

Para cada perfil muestra, sobre las celdas activas: cuántas hay, % de celdas con valor 0, media, desviación,
coeficiente de variación (desv/media; cerca de 0 = casi constante) y rango intercuartílico; y la correlación de
Spearman entre lentes (si dos lentes son casi lo mismo, la segunda no aporta información).

Uso (desde la raíz del proyecto):
    python tools/measure_lens_variance.py
    python tools/measure_lens_variance.py --db otra.db
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import data_access, grid  # noqa: E402
from src.ml.business_profiles import DEFAULT_PROFILES  # noqa: E402
from src.ml.cell_counts import CellCounts  # noqa: E402
from src.ml.lenses import compute_lenses, lens_coverage  # noqa: E402

DEFAULT_DB = ROOT / "data" / "mobility.db"
INDICADORES = ["competencia_directa", "competencia_indirecta", "mercado_total", "mercado_residentes", "mercado_turistas",
               "proveedores_total", "proveedores_diversidad"]


def load_pois(db_path: Path) -> pd.DataFrame:
    """Lee la tabla pois en solo lectura (immutable=1)."""
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?immutable=1", uri=True)
    try:
        return pd.read_sql_query("SELECT category, subcategory, latitude, longitude FROM pois", conn)
    finally:
        conn.close()


def describe_lens(serie: pd.Series) -> dict:
    """Resumen de una lente sobre las celdas activas. Los NaN (sin datos) se excluyen y se cuentan aparte."""
    valida = serie.dropna()
    if valida.empty:
        return {"n": 0, "sin_datos": len(serie)}
    media, desv = float(valida.mean()), float(valida.std(ddof=0))
    return {
        "n": int(len(valida)), "sin_datos": int(len(serie) - len(valida)),
        "pct_cero": float((valida == 0).mean()), "media": media, "desv": desv,
        "cv": desv / media if media > 0 else float("nan"),
        "iqr": float(valida.quantile(0.75) - valida.quantile(0.25)), "max": float(valida.max()),
    }


def lens_correlations(lentes: pd.DataFrame) -> pd.DataFrame:
    """Spearman entre las lentes principales (competencia directa, mercado, proveedores)."""
    cols = [c for c in ("competencia_directa", "mercado_total", "proveedores_total") if c in lentes]
    return lentes[cols].dropna(axis=1, how="all").corr(method="spearman")


def opportunity_share(lentes: pd.DataFrame) -> float:
    """Fracción de celdas con mercado por encima de la mediana Y competencia directa por debajo de la mediana.

    Si las lentes fueran independientes saldría ~25 %; cuanto más correlacionadas (todas miden 'cuán urbana es
    la celda'), menos celdas caen en ese cuadrante. NaN si falta alguna de las dos lentes."""
    if "mercado_total" not in lentes or lentes["mercado_total"].isna().all():
        return float("nan")
    m, c = lentes["mercado_total"], lentes["competencia_directa"]
    return float(((m > m.median()) & (c < c.median())).mean())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB), help=f"ruta de la base (default: {DEFAULT_DB})")
    ap.add_argument("--contexto", default=None,
                    help="directorio con el contexto de OSM de tools/download_osm_context.py (fase 1b): da datos a residentes y turistas")
    args = ap.parse_args(argv)

    pois = load_pois(Path(args.db))
    contexto = data_access.load_context(args.db, args.contexto)
    if args.contexto or not contexto.empty:
        print(f"Contexto de OSM cargado: {contexto.groupby('category').size().to_dict() if not contexto.empty else 'sin datos'}")
    if not contexto.empty:
        counts = CellCounts.from_pois(pd.concat([pois, contexto], ignore_index=True))
    else:
        counts = CellCounts.from_pois(pois)
    activas = counts.active_mask()
    print(f"POIs leídos: {len(pois)} | elementos dentro de la rejilla (POIs{' + contexto' if args.contexto else ''}): "
          f"{counts.n_total - counts.n_fuera} (fuera: {counts.n_fuera}) | "
          f"celdas totales: {grid.N_ROWS * grid.N_COLS} | celdas activas (algún POI en la celda o su vecindad): {int(activas.sum())}")

    for clave, perfil in DEFAULT_PROFILES.items():
        lentes = compute_lenses(counts, perfil, activas)
        print(f"\n=== {perfil.nombre} ({clave}) ===")
        cobertura = lens_coverage(counts, perfil)
        sin = cobertura[cobertura["pois"] == 0]
        if len(sin):
            print("   sin datos con el catálogo actual:", ", ".join(f"{r.lente}:{r.nombre}" for r in sin.itertuples()))
        print(f"   {'indicador':24} {'n':>5} {'%cero':>6} {'media':>8} {'desv':>8} {'CV':>6} {'IQR':>7} {'máx':>7}")
        for col in INDICADORES:
            if col not in lentes:
                continue
            d = describe_lens(lentes[col])
            if d["n"] == 0:
                print(f"   {col:24} {'—':>5}   sin datos")
                continue
            print(f"   {col:24} {d['n']:>5} {d['pct_cero']:>6.0%} {d['media']:>8.2f} {d['desv']:>8.2f} {d['cv']:>6.2f} "
                  f"{d['iqr']:>7.2f} {d['max']:>7.1f}")
        corr = lens_correlations(lentes)
        if corr.shape[0] > 1:
            pares = [(a, b, corr.loc[a, b]) for i, a in enumerate(corr.index) for b in corr.columns[i + 1:]]
            print("   Spearman entre lentes:", "; ".join(f"{a.split('_')[0]}~{b.split('_')[0]} {v:+.2f}" for a, b, v in pares))
        oportunidad = opportunity_share(lentes)
        if not np.isnan(oportunidad):
            print(f"   celdas con mercado alto y competencia baja (independientes darían ~25 %): {oportunidad:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
