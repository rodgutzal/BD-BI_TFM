"""
Compara la COBERTURA de Overpass (OpenStreetMap, tabla `pois`) contra la de
Foursquare (tabla `pois_foursquare`), para medir qué tan completo es OSM en
la zona antes de confiar en sus conteos de competencia.

Es de SOLO LECTURA: no modifica la base ni llama a ninguna API.

Cómo funciona
-------------
1. Empareja lugares de las dos fuentes por DISTANCIA (<=100 m) y NOMBRE
   (similitud), uno a uno. No es un emparejamiento perfecto — nombres
   distintos para el mismo negocio ("Tiffany's" vs "Tiffany's Pizzeria &
   Take Away") o negocios distintos muy juntos son inevitables en una zona
   tan densa — por eso se reportan dos niveles (fuerte y probable) y se
   imprimen ejemplos para revisarlos a ojo.

2. Foursquare devuelve como máximo 50 lugares por punto de búsqueda. Un
   punto que devolvió MENOS de 50 lo devolvió TODO lo que Foursquare tiene en
   su radio; ahí Foursquare está completo y se puede medir en ambos sentidos.
   Cuántos devolvió cada punto se lee del LOG del recolector de Foursquare
   (`logs/foursquare_collector.log`, líneas "[punto] Foursquare devolvió N
   resultados crudos"), tomando la corrida más reciente de cada punto.
   Deliberadamente NO se infiere a partir de lo guardado en la base: esa
   deducción solo es válida si la base contiene la corrida de todos los
   puntos, y da resultados engañosos (círculos "completos" con 0 lugares)
   cuando no es así. Sin log, las mediciones que necesitan círculos completos
   (A1 y B) se omiten con un aviso en vez de estimarse.

3. Dos mediciones:
   A) OSM respecto a Foursquare: de los lugares de Foursquare, ¿qué % tiene
      contraparte en OSM? Vale en todas partes, pero en zonas saturadas
      Foursquare solo aporta una muestra (posiblemente sesgada hacia lugares
      populares, que también tienden a estar mejor mapeados en OSM =>
      sobreestima la cobertura de OSM).
   B) Foursquare respecto a OSM: de los lugares de OSM, ¿qué % tiene
      contraparte en Foursquare? SOLO se calcula dentro de círculos
      completos, donde Foursquare no está recortado.

Uso (desde la raíz del proyecto):
    docker compose run --rm -v "${PWD}/src:/app/src" -v "${PWD}/tools:/app/tools" \\
        collector python tools/compare_overpass_foursquare.py
"""

import argparse
import re
import sqlite3
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.foursquare_client import build_search_points  # noqa: E402
from src.locations import LOCATIONS, ROUTES  # noqa: E402

DEFAULT_DB = ROOT / "data" / "mobility.db"
DEFAULT_LOG = ROOT / "logs" / "foursquare_collector.log"
RADIUS_M = 1500  # mismo radio que FoursquareClient
FS_LIMIT = 50  # tope de resultados por punto de Foursquare
MAX_DIST_STRONG = 100  # m
MAX_DIST_PROBABLE = 60  # m
SIM_STRONG = 0.75
SIM_PROBABLE = 0.50

# Palabras que no distinguen un negocio de otro ("Cafe Central" ~ "Central").
STOP = {
    "the",
    "and",
    "restaurant",
    "ristorante",
    "bar",
    "cafe",
    "caffe",
    "coffee",
    "pub",
    "pizzeria",
    "grill",
    "bistro",
    "kitchen",
    "shop",
    "store",
    "food",
    "take",
    "away",
    "takeaway",
    "malta",
    "ltd",
    "co",
    "of",
    "de",
    "la",
    "el",
    "il",
    "snack",
    "house",
}


def norm(s) -> str:
    if s is None or "sin nombre" in str(s).lower():
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s.replace("&", " ")).strip()


def tokens(s) -> set:
    return {t for t in norm(s).split() if len(t) >= 3 and t not in STOP}


def name_sim(a, b) -> float:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    ta, tb = tokens(a), tokens(b)
    if ta and tb and (ta <= tb or tb <= ta):  # un nombre contiene al otro
        ratio = max(ratio, 0.9)
    return ratio


def haversine_m(lat1, lon1, lat2, lon2):
    """Distancia en metros; admite arrays (broadcast)."""
    p = np.pi / 180
    a = np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371000 * np.arcsin(np.sqrt(a))


def _ascii_key(name: str) -> str:
    """Clave tolerante a la codificación del log: '↔' puede haberse guardado
    o leído mal según el sistema, así que cualquier tramo no-ASCII se
    reduce a '?' tanto en los nombres del log como en los de los puntos."""
    return re.sub(r"[^\x00-\x7f]+", "?", name).strip()


LOG_LINE = re.compile(r"\[(?P<point>[^\]]+)\] Foursquare devolvi\S* (?P<n>\d+) resultados crudos")


def parse_search_log(log_path: Path) -> dict:
    """{clave_de_punto: N resultados} usando la ÚLTIMA aparición de cada punto."""
    counts = {}
    try:
        text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return counts
    for line in text.splitlines():
        m = LOG_LINE.search(line)
        if m:
            counts[_ascii_key(m.group("point"))] = int(m.group("n"))
    return counts


def complete_circles(points: dict, log_counts: dict, limit=FS_LIMIT) -> tuple:
    """Puntos cuyo círculo NO saturó el tope según el log. Devuelve
    (círculos_completos, puntos_sin_dato_en_el_log)."""
    circles, missing = [], []
    for name, loc in points.items():
        n = log_counts.get(_ascii_key(name))
        if n is None:
            missing.append(name)
        elif n < limit:
            circles.append((name, loc, n))
    return circles, missing


def in_any_circle(df: pd.DataFrame, circles: list, radius=RADIUS_M) -> np.ndarray:
    mask = np.zeros(len(df), dtype=bool)
    for _, loc, _ in circles:
        mask |= haversine_m(loc.latitude, loc.longitude, df.latitude.values, df.longitude.values) <= radius
    return mask


def match_places(fs: pd.DataFrame, op: pd.DataFrame) -> pd.DataFrame:
    """Emparejamiento uno-a-uno FS<->OP, voraz por similitud de nombre.
    Devuelve una fila por par aceptado con columnas fs_idx, op_idx, sim, dist, nivel."""
    if fs.empty or op.empty:
        return pd.DataFrame(columns=["fs_idx", "op_idx", "sim", "dist", "nivel"])
    dist = haversine_m(
        fs.latitude.values[:, None],
        fs.longitude.values[:, None],
        op.latitude.values[None, :],
        op.longitude.values[None, :],
    )
    cands = []
    for i, j in zip(*np.where(dist <= MAX_DIST_STRONG)):
        sim = name_sim(fs.name.iloc[i], op.name.iloc[j])
        d = float(dist[i, j])
        if sim >= SIM_STRONG:
            cands.append((sim, i, j, d, "fuerte"))
        elif sim >= SIM_PROBABLE and d <= MAX_DIST_PROBABLE:
            cands.append((sim, i, j, d, "probable"))
    cands.sort(key=lambda c: (-c[0], c[3]))
    used_fs, used_op, rows = set(), set(), []
    for sim, i, j, d, nivel in cands:
        if i in used_fs or j in used_op:
            continue
        used_fs.add(i)
        used_op.add(j)
        rows.append({"fs_idx": i, "op_idx": j, "sim": sim, "dist": d, "nivel": nivel})
    return pd.DataFrame(rows)


def pct(n, d) -> str:
    return f"{100 * n / d:5.1f}%" if d else "  n/d "


def report(fs, op, matches, circles, out=print):
    matched_fs = dict(zip(matches.fs_idx, matches.nivel)) if len(matches) else {}
    matched_op = set(matches.op_idx) if len(matches) else set()
    fs = fs.assign(_nivel=[matched_fs.get(i) for i in range(len(fs))])
    op = op.assign(_match=[i in matched_op for i in range(len(op))])
    complete_fs = in_any_circle(fs, circles) if circles else np.zeros(len(fs), dtype=bool)
    complete_op = in_any_circle(op, circles) if circles else np.zeros(len(op), dtype=bool)

    if circles:
        out(f"Círculos completos (Foursquare devolvió menos de {FS_LIMIT}, según el log): {len(circles)}")
        for name, _, n in circles:
            out(f"    {name}: devolvió {n}")
    else:
        out("Círculos completos: NINGUNO identificable — las mediciones A1 y B se omiten (ver aviso arriba).")
    out(
        f"Lugares de Foursquare: {len(fs)} ({int(complete_fs.sum())} dentro de círculos completos) | "
        f"de Overpass: {len(op)} ({int(complete_op.sum())} dentro de círculos completos)"
    )
    unnamed = (op.name.map(norm) == "").mean()
    out(f"Overpass sin nombre utilizable (no se pueden emparejar por nombre): {unnamed:.0%}\n")

    def block(title, sub):
        out(title)
        out(
            f"    {'categoría Foursquare':<22}{'n':>5}   {'con contraparte en OSM (fuerte)':>32}   {'fuerte+probable':>16}"
        )
        for cat, g in sub.groupby("category"):
            strong = (g._nivel == "fuerte").sum()
            both = g._nivel.notna().sum()
            out(f"    {cat:<22}{len(g):>5}   {pct(strong, len(g)):>32}   {pct(both, len(g)):>16}")
        strong = (sub._nivel == "fuerte").sum()
        both = sub._nivel.notna().sum()
        out(f"    {'TOTAL':<22}{len(sub):>5}   {pct(strong, len(sub)):>32}   {pct(both, len(sub)):>16}\n")

    if circles:
        block("A1) OSM respecto a Foursquare — SOLO círculos completos (Foursquare sin recorte):", fs[complete_fs])
    block(
        "A2) OSM respecto a Foursquare — TODA la zona (Foursquare es una muestra topada => puede sobreestimar a OSM):",
        fs,
    )

    if circles:
        out("B) Foursquare respecto a OSM — SOLO círculos completos:")
        out(f"    {'categoría Overpass':<22}{'n':>5}   {'con contraparte en Foursquare':>30}")
        sub = op[complete_op]
        for cat, g in sub.groupby("category"):
            out(f"    {cat:<22}{len(g):>5}   {pct(g._match.sum(), len(g)):>30}")
        out(f"    {'TOTAL':<22}{len(sub):>5}   {pct(sub._match.sum(), len(sub)):>30}\n")

    out("Ejemplos para revisar a ojo (el emparejamiento automático no es perfecto):")
    if len(matches):
        out("  Pares 'probable' (Foursquare | Overpass | distancia):")
        for _, r in matches[matches.nivel == "probable"].head(6).iterrows():
            out(
                f"    {fs.name.iloc[int(r.fs_idx)][:32]:<32} | {str(op.name.iloc[int(r.op_idx)])[:32]:<32} | {r.dist:4.0f} m"
            )
    sin = fs[(complete_fs if circles else True) & fs._nivel.isna()]
    donde = "en círculos completos" if circles else "en toda la zona"
    out(f"  Lugares de Foursquare SIN contraparte {donde} ({len(sin)}), muestra:")
    for _, r in sin.head(8).iterrows():
        out(f"    {r['name'][:40]:<40} [{r['category']}/{r['subcategory']}]")
    out(
        "\nLímites: pocos círculos completos y en la zona menos densa (hacia Marsaskala) — no extrapolar tal cual al "
        "centro urbano. El emparejamiento por nombre subestima la coincidencia real cuando el mismo negocio tiene "
        "nombres distintos en cada fuente."
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument(
        "--log",
        default=str(DEFAULT_LOG),
        help="log del recolector de Foursquare, para saber qué puntos no llegaron al tope",
    )
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)  # solo lectura
    try:
        op = pd.read_sql("SELECT category, subcategory, name, latitude, longitude FROM pois", conn)
        fs = pd.read_sql("SELECT category, subcategory, name, latitude, longitude FROM pois_foursquare", conn)
    except Exception as e:
        sys.exit(f"No se pudieron leer las tablas pois / pois_foursquare: {e}")
    finally:
        conn.close()

    if op.empty or fs.empty:
        sys.exit(f"Faltan datos: pois={len(op)} filas, pois_foursquare={len(fs)} filas.")

    points = build_search_points(LOCATIONS, ROUTES)
    log_counts = parse_search_log(Path(args.log))
    circles, missing = complete_circles(points, log_counts)
    if not log_counts:
        print(
            f"AVISO: no encontré datos de puntos en el log ({args.log}); no puedo saber qué círculos están completos.\n"
        )
    elif missing:
        print(
            f"AVISO: {len(missing)} de {len(points)} puntos no aparecen en el log y se tratan como NO completos "
            f"(ej.: {missing[0]}). Corre poi_extraction_foursquare para regenerarlos.\n"
        )
    matches = match_places(fs, op)
    report(fs, op, matches, circles)


if __name__ == "__main__":
    main()
