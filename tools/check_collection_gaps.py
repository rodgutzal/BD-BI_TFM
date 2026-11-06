"""
Detecta y mide HUECOS en la recolección de tráfico (tabla route_measurements).

Por qué existe: si el stack de Docker está apagado, el collector no recolecta
y nada avisa — no hay error, simplemente dejan de llegar datos. Un
`docker compose run ...` puntual (para correr un script suelto) arranca solo
la base de datos como dependencia, lo que da la falsa impresión de que el
sistema está en marcha. Esta herramienta lo revela desde los propios datos.

Los ciclos de recolección escriben todas sus filas casi al mismo instante, y
en modo híbrido llega un ciclo cada 15 min (ORS) o 27 min (TomTom); por eso un
umbral de 2 horas separa sin ambigüedad una caída real de la cadencia normal.

Es de SOLO LECTURA: no modifica la base.

Uso (desde la raíz del proyecto):
    docker compose run --rm -v "${PWD}/tools:/app/tools" collector python tools/check_collection_gaps.py
    ... python tools/check_collection_gaps.py --days 60 --min-gap-hours 1
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mobility.db"


def load_cycle_times(db_path, since: pd.Timestamp) -> pd.DataFrame:
    """Instantes DISTINTOS de recolección (UTC), con su fuente, desde `since`."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)   # solo lectura
    try:
        df = pd.read_sql("SELECT timestamp, data_source FROM route_measurements", conn)
    finally:
        conn.close()
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601", errors="coerce")
    df = df.dropna(subset=["ts"])
    return df[df["ts"] >= since]


def find_gaps(times: pd.Series, min_gap: pd.Timedelta) -> pd.DataFrame:
    """Huecos entre instantes consecutivos: columnas start, end, duration."""
    t = times.drop_duplicates().sort_values().reset_index(drop=True)
    if len(t) < 2:
        return pd.DataFrame(columns=["start", "end", "duration"])
    gap = t.diff()
    idx = gap[gap > min_gap].index
    return pd.DataFrame({"start": t.shift(1)[idx].values, "end": t[idx].values, "duration": gap[idx].values})


def fmt_h(td: pd.Timedelta) -> str:
    h = td.total_seconds() / 3600
    return f"{h / 24:.1f} días" if h >= 48 else f"{h:.1f} h"


def report(df: pd.DataFrame, now: pd.Timestamp, days: int, min_gap: pd.Timedelta, out=print) -> dict:
    if df.empty:
        out(f"Sin datos de tráfico en los últimos {days} días.")
        return {"gaps": 0}

    last = df["ts"].max()
    age = now - last
    out(f"Último dato de tráfico: {last:%Y-%m-%d %H:%M} UTC  (hace {fmt_h(age)})")
    for src, g in df.groupby("data_source"):
        out(f"    {src:<8} último: {g['ts'].max():%Y-%m-%d %H:%M} UTC")

    if age > min_gap:
        out(f"  >> AHORA MISMO no está llegando tráfico (sin datos hace {fmt_h(age)}). "
            f"Revisa: docker compose ps  /  docker compose up -d")

    first = df["ts"].min()
    window = max(last - first, pd.Timedelta(seconds=1))
    gaps = find_gaps(df["ts"], min_gap)
    missing = gaps["duration"].sum() if len(gaps) else pd.Timedelta(0)
    out(f"\nVentana con datos: {first:%Y-%m-%d %H:%M} -> {last:%Y-%m-%d %H:%M} UTC "
        f"({df['ts'].nunique()} instantes de recolección distintos)")
    out(f"Huecos de más de {fmt_h(min_gap)}: {len(gaps)}"
        + (f"   |   tiempo total sin datos dentro de la ventana: {fmt_h(missing)} "
           f"({100 * missing / window:.1f}%)" if len(gaps) else ""))
    for _, r in gaps.sort_values("start").tail(15).iterrows():
        out(f"    {pd.Timestamp(r['start']):%Y-%m-%d %H:%M}  ->  {pd.Timestamp(r['end']):%Y-%m-%d %H:%M} UTC   ({fmt_h(r['duration'])})")
    if len(gaps) > 15:
        out(f"    ... (se muestran los 15 más recientes de {len(gaps)})")
    return {"gaps": len(gaps), "missing": missing, "age": age}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--days", type=int, default=30, help="ventana hacia atrás desde ahora (default 30)")
    ap.add_argument("--min-gap-hours", type=float, default=2.0, help="umbral para llamar hueco a una pausa (default 2)")
    ap.add_argument("--now", default=None, help="(pruebas) instante 'actual' en ISO 8601")
    args = ap.parse_args()

    now = pd.Timestamp(args.now, tz="UTC") if args.now else pd.Timestamp.now(tz="UTC")
    try:
        df = load_cycle_times(args.db, now - pd.Timedelta(days=args.days))
    except Exception as e:
        sys.exit(f"No se pudo leer route_measurements de {args.db}: {e}")
    report(df, now, args.days, pd.Timedelta(hours=args.min_gap_hours))


if __name__ == "__main__":
    main()
