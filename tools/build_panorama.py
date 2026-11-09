"""
Construye el PANORAMA POR CELDA del asistente de recomendación (fase 2a de docs/DISENO_ML_RECOMENDACION.md): para cada
perfil de negocio, las tres lentes (competencia, mercado, proveedores) de cada celda activa, con percentiles, una
confianza de datos y, solo para `food_drink` y `business`, la brecha de oferta como indicador EXPLORATORIO.

Está pensado para correr en la MÁQUINA DE ENTRENAMIENTO con el paquete de entrada (tools/export_ml_inputs.py), pero
acepta también la base completa. Es de SOLO LECTURA sobre la entrada. La brecha requiere entrenar (validación espacial
repetida, 1-2 minutos por objetivo); con `--sin-brecha` solo se calculan las lentes, en segundos.

Escribe en --out-dir (por defecto data/ml/), para versionar y llevar al dashboard:
    panorama.csv            una fila por (perfil, celda activa)
    cell_counts.csv         celda × (categoría|subcategoría): base para recalcular las lentes con otro perfil
    panorama_manifest.json  procedencia (hash de la entrada, commit, versiones), parámetros, decisión de la validación

Uso (desde la raíz del proyecto):
    python tools/build_panorama.py --db data/ml_inputs.sqlite
    python tools/build_panorama.py --db data/ml_inputs.sqlite --sin-brecha
    python tools/build_panorama.py --db data/mobility.db --contexto C:\\temp\\osm_context --repeats 5
"""

import argparse
import importlib.util
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import data_access, inputs_bundle, panorama  # noqa: E402
from src.ml.business_profiles import DEFAULT_PROFILES  # noqa: E402
from src.ml.cell_counts import CellCounts  # noqa: E402

DEFAULT_DB = ROOT / "data" / "mobility.db"
DEFAULT_OUT = ROOT / "data" / "ml"
TARGETS = ("food_drink", "business")        # los únicos con datos suficientes para aprender una oferta esperada
ADVERTENCIA = ("La brecha de oferta es EXPLORATORIA: en la validación espacial ningún candidato superó con claridad a la "
               "densidad de POIs (ver docs/DISENO_ML_RECOMENDACION.md §3.G y §3.H). No entra en ningún puntaje.")


def _herramienta(nombre: str):
    spec = importlib.util.spec_from_file_location(nombre, ROOT / "tools" / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def calcular_brechas(counts, zonas, fsq, args, con_contexto: bool) -> dict:
    """Valida y calcula la brecha de cada objetivo. Devuelve {clave: (tabla indexada por cell_id, modelo, ganador, resumen)}."""
    from src.ml import validation
    vlm = _herramienta("validate_location_model")
    resultado = {}
    for clave in TARGETS:
        t0 = time.perf_counter()
        r = vlm.run_target(clave, counts, zonas, fsq, args.repeats, args.folds, args.boot, args.seed, args.k,
                           progress=lambda i, n, c=clave: print(f"\r   {c}: repetición {i}/{n}", end="", flush=True),
                           con_contexto=con_contexto)
        print(f"\r   {clave}: {time.perf_counter() - t0:.0f} s{' ' * 20}")
        tabla = validation.gap_from_evaluation(r["evaluacion"], r["modelo_brecha"])
        tabla.index = r["X"].index
        d = r["decision"]
        resultado[clave] = (tabla, r["modelo_brecha"], d["ganador"],
                            {"modelo_brecha": r["modelo_brecha"], "ganador": d["ganador"], "mejor_baseline": d["mejor_baseline"],
                             "comparaciones": {c: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()}
                                               for c, f in d["comparaciones"].items()}})
    return resultado


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB), help=f"paquete de entrada o base (default: {DEFAULT_DB})")
    ap.add_argument("--contexto", default=None, help="directorio con el contexto de OSM (si no, el del paquete)")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT), help=f"directorio de salida (default: {DEFAULT_OUT})")
    ap.add_argument("--sin-brecha", action="store_true", help="solo las lentes: no entrena ni calcula la brecha")
    ap.add_argument("--repeats", type=int, default=10)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--k", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    if inputs_bundle.is_bundle(args.db):
        problemas = inputs_bundle.verify_bundle(args.db)
        if problemas:
            print("El paquete de entrada no coincide con su manifiesto:\n  " + "\n  ".join(problemas))
            return 1
    pois = data_access.load_pois(args.db)
    contexto = data_access.load_context(args.db, args.contexto)
    con_contexto = not contexto.empty
    counts = CellCounts.from_pois(pd.concat([pois, contexto], ignore_index=True) if con_contexto else pois)
    print(f"POIs: {len(pois)} | contexto de OSM: {len(contexto)} | celdas activas: {int(counts.active_mask().sum())}")

    brechas = {}
    if not args.sin_brecha:
        brechas = calcular_brechas(counts, data_access.load_zone_table(args.db), data_access.load_pois_foursquare(args.db),
                                   args, con_contexto)
    partes = []
    for clave, perfil in DEFAULT_PROFILES.items():
        tabla, modelo, ganador, _ = brechas.get(clave, (None, "", None, None))
        partes.append(panorama.build_panorama(counts, perfil, tabla, modelo, brecha_validada=ganador is not None))
    tabla_final = pd.concat(partes)

    export = _herramienta("export_ml_inputs")
    manifiesto = {
        "procedencia": inputs_bundle.provenance(args.db, export.git_commit()),
        "parametros": {"repeats": args.repeats, "folds": args.folds, "boot": args.boot, "k": args.k, "seed": args.seed,
                       "con_brecha": not args.sin_brecha, "con_contexto": con_contexto},
        "perfiles": list(DEFAULT_PROFILES),
        "brecha": {c: v[3] for c, v in brechas.items()},
        "advertencia": ADVERTENCIA if brechas else "Sin brecha: solo lentes explícitas.",
    }
    completo = panorama.write_outputs(args.out_dir, tabla_final, counts, manifiesto)
    print(f"\nEscrito en {args.out_dir}:")
    for nombre, info in completo["archivos"].items():
        print(f"   {nombre:20} {info['filas']:>7} filas  sha256 {info['sha256'][:16]}…")
    for clave, (_, modelo, ganador, _) in brechas.items():
        print(f"   brecha {clave}: modelo {modelo}; "
              + ("VALIDADA" if ganador else "exploratoria (ningún candidato supera con claridad a la línea base)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
