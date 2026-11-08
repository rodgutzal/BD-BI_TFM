"""
Valida los modelos de oferta esperada del asistente de recomendación (fase 1 de docs/DISENO_ML_RECOMENDACION.md).

Para cada categoría objetivo (food_drink y business, las únicas con datos suficientes) entrena, con VALIDACIÓN CRUZADA
ESPACIAL por bloques de ~1 km repetida, el boosting de Poisson y la red MLP, y los compara con cuatro líneas base
(media, solo distancia, solo población, solo densidad urbana). Aplica la regla fijada de antemano: un modelo solo se
publica si mejora a la mejor línea base con el intervalo de confianza (bootstrap de bloques) por debajo de 0.

Además calcula la BRECHA DE OFERTA fuera de muestra (esperado − observado: cada celda se predice con un modelo que no
vio su bloque) y la contrasta con Foursquare, una fuente independiente:
  - AUC: ¿la oferta esperada distingue las celdas donde Foursquare tiene locales?
  - Artefacto de cartografía: de las celdas con mayor brecha, ¿cuántas tienen más locales en Foursquare que en OSM?
    (si muchas, el supuesto déficit puede ser solo falta de mapeo en OSM).

Es de SOLO LECTURA: abre la base con `immutable=1`. Con el stack apagado.

Uso (desde la raíz del proyecto):
    python tools/validate_location_model.py                       # food_drink y business, 10 repeticiones (~1-2 min)
    python tools/validate_location_model.py --target food_drink --repeats 5
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.locations import LOCATIONS  # noqa: E402
from src.ml import business_profiles, data_access, features, grid, models, validation  # noqa: E402
from src.ml.cell_counts import CellCounts  # noqa: E402

DEFAULT_DB = ROOT / "data" / "mobility.db"
TARGETS = ("food_drink", "business")
# Qué categorías de Foursquare se corresponden con cada objetivo de Overpass (contraste aproximado).
FSQ_MAP = {"food_drink": ("restaurant",), "business": ("retail", "services")}


def prepare(counts: CellCounts, target, zonas: pd.DataFrame):
    """(X, y) sobre las celdas activas: variables SIN el objetivo y conteo real del objetivo en cada celda."""
    X = features.build_features(counts, target, zonas)
    y = features.target_counts(counts, target).reindex(X.index).to_numpy()
    return X, y


def fsq_cell_counts(fsq: pd.DataFrame, categorias, index) -> np.ndarray:
    """Locales de Foursquare de esas categorías en cada celda de `index`."""
    sub = fsq[fsq["category"].isin(categorias)]
    filas, cols = grid.cell_index(sub["latitude"].to_numpy(), sub["longitude"].to_numpy())
    matriz = grid.count_grid(filas, cols)
    f, c = validation.positions(index)
    return matriz[f, c]


def run_target(clave: str, counts: CellCounts, zonas: pd.DataFrame, fsq: pd.DataFrame, repeats: int, n_folds: int,
               n_boot: int, seed: int, k_top: int, progress=None) -> dict:
    """Valida un objetivo y devuelve todo lo que luego se imprime (y se puede probar)."""
    perfil = business_profiles.get_default_profile(clave)
    objetivo = list(perfil.competencia_directa)
    X, y = prepare(counts, objetivo, zonas)
    ev = validation.evaluate(X, y, repeats=repeats, n_folds=n_folds, seed=seed, k_top=k_top, progress=progress)
    decision = validation.decide(ev, n_boot=n_boot, seed=seed)
    # La brecha usa el candidato ganador; si ninguno gana, el mejor de los candidatos solo como referencia informativa.
    resumen = validation.summarize(ev)
    referencia = decision["ganador"] or min(models.CANDIDATOS, key=lambda m: resumen.loc[m, "desviacion"])
    esperado = ev.oof[referencia].mean(axis=0)
    brecha = esperado - ev.y
    fsq_n = fsq_cell_counts(fsq, FSQ_MAP[clave], X.index)
    return {
        "clave": clave, "perfil": perfil, "X": X, "y": ev.y, "evaluacion": ev, "resumen": resumen, "decision": decision,
        "modelo_brecha": referencia, "esperado": esperado, "brecha": brecha, "fsq": fsq_n,
        "auc": {m: validation.auc_presence(ev.oof[m].mean(axis=0), fsq_n > 0) for m in ev.nombres} if len(fsq) else {},
        "artefacto": validation.gap_artifact_share(brecha, ev.y, fsq_n, k_top) if len(fsq) else None,
    }


def zona_mas_cercana(fila, col) -> str:
    lat, lon = grid.cell_center(fila, col)
    return min(LOCATIONS, key=lambda z: grid.haversine_m(LOCATIONS[z].latitude, LOCATIONS[z].longitude, lat, lon))


def imprimir(r: dict, repeats: int, k_top: int) -> None:
    y, X = r["y"], r["X"]
    print(f"\n{'=' * 78}\n{r['perfil'].nombre} ({r['clave']}): {int(y.sum())} locales en {len(y)} celdas activas "
          f"({int((y > 0).sum())} con al menos uno; máx. {int(y.max())} en una celda)\n{'=' * 78}")
    print(f"Validación espacial: {repeats} repeticiones, bloques de {validation.BLOCK_CELLS}x{validation.BLOCK_CELLS} celdas (~1 km).")
    print(f"   {'modelo':16} {'desviación':>11} {'± sd':>7} {'Spearman':>9} {'precisión@' + str(k_top):>13}")
    for modelo, f in r["resumen"].iterrows():
        marca = "  <- candidato" if modelo in models.CANDIDATOS else ""
        print(f"   {modelo:16} {f['desviacion']:>11.3f} {f['desviacion_sd']:>7.3f} {f['spearman']:>9.3f} {f['precision_k']:>13.2f}{marca}")
    d = r["decision"]
    print(f"\nMejor línea base: {d['mejor_baseline']}. Diferencia de desviación por celda (candidato − línea base; "
          "negativa = mejor), IC 95 % por bootstrap de bloques:")
    for c, f in d["comparaciones"].items():
        print(f"   {c:10} {f['diferencia']:+.3f}  [{f['ic_inf']:+.3f}, {f['ic_sup']:+.3f}]  -> {f['veredicto']}")
    if d["ganador"]:
        print(f"\nDECISIÓN: se puede publicar «{d['ganador']}» (mejora a la mejor línea base con el intervalo por debajo de 0).")
    else:
        print("\nDECISIÓN: NINGÚN candidato mejora a la mejor línea base con claridad -> NO se publica puntaje de ML; se queda el MCDA.")
    if r["auc"]:
        print("\nContraste con Foursquare (fuente independiente). AUC de la oferta esperada fuera de muestra para las celdas "
              "con locales en Foursquare:")
        print("   " + "  ".join(f"{m}={a:.3f}" for m, a in sorted(r["auc"].items(), key=lambda kv: -kv[1])))
        a = r["artefacto"]
        print(f"   Entre las {k_top} celdas con mayor brecha ({r['modelo_brecha']}), {a['top_k']:.0%} tienen más locales en Foursquare que en OSM "
              f"(referencia entre todas las celdas con locales: {a['referencia']:.0%}) -> "
              + ("posible falta de mapeo en OSM" if a['top_k'] > a['referencia'] + 0.1 else "no parece falta de mapeo"))
    else:
        print("\n(sin datos de Foursquare: no se hace el contraste independiente)")
    f, c = validation.positions(X.index)
    relativa = validation.brecha_relativa(r["esperado"], y)
    for titulo, serie in (("absoluta (esperado − observado)", r["brecha"]), ("RELATIVA (en desviaciones típicas)", relativa)):
        print(f"\nCordura: 5 celdas con mayor brecha {titulo} ({r['modelo_brecha']}, fuera de muestra):")
        print(f"   {'celda':8} {'zona cercana':13} {'a (m)':>6} {'observado':>10} {'esperado':>9} {'abs.':>7} {'rel.':>6}")
        for i in np.argsort(-serie, kind="stable")[:5]:
            print(f"   {X.index[i]:8} {zona_mas_cercana(f[i], c[i]):13} {X['dist_centro_m'].iloc[i]:>6.0f} {y[i]:>10.0f} "
                  f"{r['esperado'][i]:>9.1f} {r['brecha'][i]:>+7.1f} {relativa[i]:>+6.1f}")
    top_dist = float(np.median(X["dist_centro_m"].to_numpy()[np.argsort(-r["brecha"], kind="stable")[:k_top]]))
    print(f"   distancia mediana al centro de zona: celdas de mayor brecha {top_dist:.0f} m | todas las celdas "
          f"{float(np.median(X['dist_centro_m'])):.0f} m")
    print("   (sin edificios ni población por celda —fase 1b— no se puede comprobar que esas celdas tengan gente)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB), help=f"ruta de la base (default: {DEFAULT_DB})")
    ap.add_argument("--target", choices=TARGETS + ("all",), default="all")
    ap.add_argument("--repeats", type=int, default=10, help="repeticiones de la validación espacial")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--boot", type=int, default=2000, help="remuestreos del bootstrap de bloques")
    ap.add_argument("--k", type=int, default=50, help="k de la precisión@k y del análisis de la brecha")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    pois = data_access.load_pois(args.db)
    zonas = data_access.load_zone_table(args.db)
    fsq = data_access.load_pois_foursquare(args.db)
    counts = CellCounts.from_pois(pois)
    print(f"POIs de Overpass: {len(pois)} | Foursquare: {len(fsq)} | zonas con población: {int(zonas['demanda'].notna().sum())}/{len(zonas)}")
    for clave in (TARGETS if args.target == "all" else (args.target,)):
        t0 = time.perf_counter()
        r = run_target(clave, counts, zonas, fsq, args.repeats, args.folds, args.boot, args.seed, args.k,
                       progress=lambda i, n: print(f"\r   {clave}: repetición {i}/{n}", end="", flush=True))
        print(f"\r   {clave}: {time.perf_counter() - t0:.0f} s{' ' * 20}")
        imprimir(r, args.repeats, args.k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
