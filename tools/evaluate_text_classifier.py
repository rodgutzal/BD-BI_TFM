"""
Evalúa el clasificador de texto del tipo de negocio (fase 3 de docs/DISENO_ML_RECOMENDACION.md §3.C) frente al método de
palabras clave actual, con la regla de decisión fijada de antemano (ver src/ml/text_training.py).

Datos (a mano, en data/text/): frases de entrenamiento y un conjunto de evaluación RESERVADO de 200 frases (directas,
sinónimos, erratas, frases largas y frases fuera de alcance). Ninguna frase de evaluación se usa para entrenar ni para
elegir el umbral (que sale de una validación cruzada sobre el entrenamiento).

Compara: palabras clave, TF-IDF + regresión logística, red MLP y el híbrido (palabras clave y, solo si se abstienen, el
clasificador). Con --exportar escribe el modelo (JSON, solo numpy para usarlo) y su manifiesto.

No necesita la base de datos ni la red. Tarda ~1-2 minutos (casi todo es la red MLP; --sin-mlp la omite).

Uso (desde la raíz del proyecto):
    python tools/evaluate_text_classifier.py
    python tools/evaluate_text_classifier.py --exportar data/ml
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import text_training as tt  # noqa: E402
from src.ml.inputs_bundle import file_hash, library_versions  # noqa: E402
from src.ml.text_classifier import NINGUNA  # noqa: E402

DATA = ROOT / "data" / "text"
ENTRENAMIENTO = DATA / "frases_entrenamiento.psv"
EVALUACION = DATA / "frases_evaluacion.psv"
CATEGORIAS = ("food_drink", "hospital", "school", "sport", "leisure", "mall", "business")


def cargar(entrenamiento=ENTRENAMIENTO, evaluacion=EVALUACION):
    tr = pd.read_csv(entrenamiento, sep="|", dtype=str, keep_default_na=False)
    ev = pd.read_csv(evaluacion, sep="|", dtype=str, keep_default_na=False)
    return tr, ev


def validar_datos(tr: pd.DataFrame, ev: pd.DataFrame) -> list:
    """Problemas de los datos que invalidarían la evaluación (vacío = bien)."""
    validas = set(CATEGORIAS) | {NINGUNA}
    problemas = []
    for nombre, df in (("entrenamiento", tr), ("evaluación", ev)):
        malas = sorted(set(df["categoria"]) - validas)
        if malas:
            problemas.append(f"{nombre}: categorías desconocidas {malas}")
        if df["frase"].str.strip().eq("").any() or df["frase"].duplicated().any():
            problemas.append(f"{nombre}: frases vacías o repetidas")
    if "ciego" in ev.columns:
        malas = sorted(set(ev["ciego"]) - validas)
        if malas:
            problemas.append(f"evaluación: etiquetas del etiquetador ciego desconocidas {malas}")
    comunes = set(tr["frase"].str.lower().str.strip()) & set(ev["frase"].str.lower().str.strip())
    if comunes:
        problemas.append(
            f"{len(comunes)} frases están a la vez en entrenamiento y evaluación (p. ej. {sorted(comunes)[:3]})"
        )
    return problemas


def solo_coincidentes(ev: pd.DataFrame) -> pd.DataFrame:
    """Las frases cuya etiqueta del autor coincide con la del etiquetador ciego (docs/DISENO_ML_RECOMENDACION.md §3.L2).
    Las que no coinciden son las ambiguas (`ambiguas`): quedan fuera de la evaluación principal y `main` imprime cómo
    responden los sistemas a cada una."""
    return ev[ev["ciego"] == ev["categoria"]].reset_index(drop=True)


def ambiguas(ev: pd.DataFrame) -> pd.DataFrame:
    """Las frases cuya etiqueta del autor NO coincide con la del etiquetador ciego (el complemento de `solo_coincidentes`)."""
    return ev[ev["ciego"] != ev["categoria"]].reset_index(drop=True)


def evaluar(
    tr: pd.DataFrame, ev: pd.DataFrame, seed: int = 0, n_boot: int = 5000, n_folds: int = 5, con_mlp: bool = True
) -> dict:
    """Todo lo que luego se imprime y se exporta. No toca la evaluación para elegir nada."""
    X, y = list(tr["frase"]), list(tr["categoria"])
    frases, reales, tipos = list(ev["frase"]), list(ev["categoria"]), list(ev["tipo"])

    # umbrales: solo con el entrenamiento (validación cruzada)
    c_lr, p_lr = tt.probabilidades_oof(
        X, y, lambda a, b, c: tt.probabilidades_sklearn(a, b, c, seed=seed), n_folds, seed
    )
    palabras_tr = tt.palabras_clave(X)  # las palabras clave no se entrenan: sirven de referencia para el umbral
    umbral_lr, umbral_mlp = tt.elegir_umbral(c_lr, p_lr, y, palabras_tr), None
    if con_mlp:
        c_mlp, p_mlp = tt.probabilidades_oof(
            X, y, lambda a, b, c: tt.probabilidades_mlp(a, b, c, seed=seed), n_folds, seed
        )
        umbral_mlp = tt.elegir_umbral(c_mlp, p_mlp, y, palabras_tr)

    modelo = tt.entrenar_logistica(X, y, seed=seed)
    modelo.umbral = umbral_lr
    clases_l, pl = tt.probabilidades_sklearn(X, y, frases, seed=seed)
    sistemas = {"palabras": tt.palabras_clave(frases), "logistica": tt.respuesta(clases_l, pl, umbral_lr)}
    if con_mlp:
        clases_m, pm = tt.probabilidades_mlp(X, y, frases, seed=seed)
        sistemas["mlp"] = tt.respuesta(clases_m, pm, umbral_mlp)
    sistemas["hibrido"] = tt.hibrido(sistemas["palabras"], sistemas["logistica"])
    if con_mlp:
        sistemas["hibrido_mlp"] = tt.hibrido(sistemas["palabras"], sistemas["mlp"])
    # Sensibilidad (descriptiva, NO se usa para elegir nada): el híbrido con cada umbral sobre la evaluación.
    sensibilidad = []
    for u in tt.UMBRALES:
        h = tt.hibrido(sistemas["palabras"], tt.respuesta(clases_l, pl, u))
        d = tt.decidir(sistemas["palabras"], h, reales, 1000, seed)
        sensibilidad.append(
            {
                "umbral": u,
                **tt.resumen(h, reales),
                "ic_inf": d["exactitud"]["ic_inf"],
                "cumple_errores": d["cumple_errores"],
            }
        )
    return {
        "sensibilidad": sensibilidad,
        "modelo": modelo,
        "umbral": {"logistica": umbral_lr, "mlp": umbral_mlp},
        "frases": frases,
        "reales": reales,
        "tipos": tipos,
        "sistemas": sistemas,
        "resumen": {k: tt.resumen(v, reales) for k, v in sistemas.items()},
        "por_tipo": {k: tt.por_tipo(sistemas[k], reales, tipos) for k in ("palabras", "logistica", "hibrido")},
        "decision": tt.decidir(sistemas["palabras"], sistemas["hibrido"], reales, n_boot, seed),
        "logistica_vs_mlp": (
            tt.bootstrap_pareado(
                tt.aciertos(sistemas["logistica"], reales), tt.aciertos(sistemas["mlp"], reales), n_boot, seed
            )
            if con_mlp
            else None
        ),
        "n_entrenamiento": len(tr),
        "n_evaluacion": len(ev),
        "con_ciego": "ciego" in ev.columns,
    }


def imprimir(r: dict) -> None:
    print(
        f"Entrenamiento: {r['n_entrenamiento']} frases | evaluación reservada: {r['n_evaluacion']} frases "
        f"({sum(1 for c in r['reales'] if c == NINGUNA)} fuera de alcance)"
    )
    mlp = f", MLP {r['umbral']['mlp']:.2f}" if r["umbral"]["mlp"] is not None else ""
    print(
        f"Umbral de confianza elegido por validación cruzada del entrenamiento: logística {r['umbral']['logistica']:.2f}{mlp}\n"
    )
    print(f"{'sistema':14} {'exactitud':>10} {'equivocadas':>12} {'sin respuesta':>14}")
    for nombre, s in r["resumen"].items():
        print(f"{nombre:14} {s['exactitud']:>10.1%} {s['equivocadas']:>12.1%} {s['sin_respuesta']:>14.1%}")
    print(
        "\n«equivocadas» = respondió una categoría que no es (incluye responder a una frase fuera de alcance); "
        "«sin respuesta» = no respondió a una frase que sí describía un negocio."
    )
    print("\nPor tipo de frase (exactitud / equivocadas):")
    tipos = list(r["por_tipo"]["palabras"].index)
    print(f"   {'tipo':10} {'n':>3} " + " ".join(f"{k:>22}" for k in r["por_tipo"]))
    for t in tipos:
        celdas = [
            f"{r['por_tipo'][k].loc[t, 'exactitud']:>9.0%} / {r['por_tipo'][k].loc[t, 'equivocadas']:<8.0%}"
            for k in r["por_tipo"]
        ]
        print(f"   {t:10} {int(r['por_tipo']['palabras'].loc[t, 'n']):>3} " + " ".join(f"{c:>22}" for c in celdas))
    print(
        "\nLa composición del conjunto (cuotas por tipo y categoría) la fijó el autor antes de generarlo; el número global "
        "depende de ella. Lo que se compara es el desglose por tipo."
    )
    d = r["decision"]
    e = d["exactitud"]
    print(f"\nRegla de decisión (híbrido frente a palabras clave):")
    print(
        f"   exactitud: {e['diferencia']:+.1%} [{e['ic_inf']:+.1%}, {e['ic_sup']:+.1%}] -> "
        + ("IC por encima de 0" if d["cumple_exactitud"] else "el IC incluye 0")
    )
    print(
        f"   respuestas equivocadas: híbrido {d['equivocadas_candidato']:.1%} frente a {d['equivocadas_palabras']:.1%} "
        f"(tolerancia +{tt.TOLERANCIA_ERRORES:.0%}) -> " + ("cumple" if d["cumple_errores"] else "NO cumple")
    )
    print(
        "   DECISIÓN: "
        + (
            "se adopta el híbrido."
            if d["adoptar"]
            else "NO se adopta el híbrido; se queda el método de palabras clave."
        )
    )
    v = r["logistica_vs_mlp"]
    if v is not None:
        print(
            f"\nLogística − MLP (exactitud): {v['diferencia']:+.1%} [{v['ic_inf']:+.1%}, {v['ic_sup']:+.1%}] -> "
            + ("la red no se distingue de la logística" if v["ic_inf"] <= 0 <= v["ic_sup"] else "diferencia clara")
        )
    print("\nSensibilidad al umbral (descriptiva; NO se usa para elegir): híbrido sobre la evaluación")
    print(f"   {'umbral':>6} {'exactitud':>10} {'equivocadas':>12} {'sin resp.':>10}  cumpliría la regla")
    for s in r["sensibilidad"][::2]:
        print(
            f"   {s['umbral']:>6.2f} {s['exactitud']:>10.1%} {s['equivocadas']:>12.1%} {s['sin_respuesta']:>10.1%}  "
            + ("sí" if s["cumple_errores"] and s["ic_inf"] > 0 else "no")
        )
    print(
        "   Elegir ahora un umbral con esta tabla sería ajustar a la evaluación: cualquier cambio de protocolo exige una "
        "evaluación nueva."
    )
    print("\nRespuestas equivocadas del híbrido:")
    for f, real, resp in zip(r["frases"], r["reales"], r["sistemas"]["hibrido"]):
        if resp is not None and resp != real:
            print(f"   «{f}»: dijo {resp}, era {real}")


def imprimir_ambiguas(tr: pd.DataFrame, dudosas: pd.DataFrame, seed: int = 0) -> None:
    """Cómo responden las palabras clave y el híbrido a las frases ambiguas (excluidas de la evaluación principal). Es
    informativo: el modelo y el umbral son los mismos, sin tocar nada."""
    r = evaluar(tr, dudosas, seed, 100, con_mlp=False)
    print(
        f"\nLas {len(dudosas)} frases ambiguas (no coinciden con el etiquetador ciego), fuera de la evaluación principal:"
    )
    pal, hib = r["sistemas"]["palabras"], r["sistemas"]["hibrido"]
    for f, autor, ciego, p, h in zip(dudosas["frase"], dudosas["categoria"], dudosas["ciego"], pal, hib):
        print(f"   autor={autor}, ciego={ciego} | palabras={p}, híbrido={h} | «{f}»")
    print(
        f"   El híbrido coincide con el autor en {sum(h == a for h, a in zip(hib, dudosas['categoria']))} y con el etiquetador "
        f"en {sum(h == c for h, c in zip(hib, dudosas['ciego']))} de {len(dudosas)}."
    )


def exportar(r: dict, destino: Path, entrenamiento=ENTRENAMIENTO, evaluacion=EVALUACION, commit: str = "") -> dict:
    """Escribe text_classifier.json y text_classifier_manifest.json en `destino` y devuelve el manifiesto."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / "text_classifier.json"
    r["modelo"].save(ruta)
    d = r["decision"]
    manifiesto = {
        "formato": 1,
        "adoptado": d["adoptar"],
        "umbral": r["umbral"]["logistica"],
        "modelo": {
            "archivo": ruta.name,
            "sha256": file_hash(ruta),
            "clases": r["modelo"].clases,
            "ngramas": list(r["modelo"].ngramas),
            "n_ngramas": len(r["modelo"].vocabulario),
        },
        "decision": {
            "exactitud": d["exactitud"],
            "equivocadas_hibrido": d["equivocadas_candidato"],
            "equivocadas_palabras": d["equivocadas_palabras"],
            "tolerancia_errores": tt.TOLERANCIA_ERRORES,
        },
        "resumen": r["resumen"],
        "datos": {
            "entrenamiento": {
                "archivo": Path(entrenamiento).name,
                "frases": r["n_entrenamiento"],
                "sha256": file_hash(entrenamiento),
            },
            "evaluacion": {
                "archivo": Path(evaluacion).name,
                "frases": r["n_evaluacion"],
                # el archivo puede tener más frases que las evaluadas (p. ej. las ambiguas con --solo-coincidentes): se
                # registra para que el número de frases evaluadas se pueda reproducir solo con el manifiesto
                "frases_en_archivo": r.get("n_archivo_evaluacion", r["n_evaluacion"]),
                "filtro": r.get("filtro"),
                "sha256": file_hash(evaluacion),
            },
        },
        "advertencia": (
            (
                "Frases de evaluación escritas por un modelo de lenguaje (Codex) y etiquetadas por otra sesión a ciegas; "
                "no son consultas reales de usuarios: la exactitud puede ser optimista y depende de la composición del "
                "conjunto."
            )
            if r.get("con_ciego")
            else (
                "Frases de entrenamiento y de evaluación escritas por el mismo autor (no son consultas reales de "
                "usuarios): la exactitud sobre ellas es optimista y depende de la composición del conjunto."
            )
        ),
        "procedencia": {
            "commit": commit or "desconocido",
            **{f"version.{k}": v for k, v in library_versions().items()},
        },
    }
    (destino / "text_classifier_manifest.json").write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return manifiesto


def _commit() -> str:
    spec = importlib.util.spec_from_file_location("export_ml_inputs", ROOT / "tools" / "export_ml_inputs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.git_commit()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--entrenamiento", default=str(ENTRENAMIENTO))
    ap.add_argument("--evaluacion", default=str(EVALUACION))
    ap.add_argument(
        "--exportar", default=None, help="directorio donde escribir el modelo y su manifiesto (p. ej. data/ml)"
    )
    ap.add_argument(
        "--solo-coincidentes",
        action="store_true",
        help="evalúa solo las frases cuya etiqueta coincide con la del etiquetador ciego (columna `ciego`)",
    )
    ap.add_argument("--sin-mlp", action="store_true", help="omite la red MLP (es lo que más tarda: ~1 minuto)")
    ap.add_argument("--boot", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    tr, ev = cargar(args.entrenamiento, args.evaluacion)
    problemas = validar_datos(tr, ev)
    if args.solo_coincidentes and "ciego" not in ev.columns:
        problemas.append("--solo-coincidentes necesita la columna `ciego` en el archivo de evaluación")
    if problemas:
        print("Los datos no son válidos para evaluar:\n  " + "\n  ".join(problemas))
        return 1
    n_archivo = len(ev)
    if args.solo_coincidentes:
        n_antes = len(ev)
        dudosas = ambiguas(ev)
        ev = solo_coincidentes(ev)
        print(
            f"Se evalúan {len(ev)} de {n_antes} frases: las otras {n_antes - len(ev)} son ambiguas (no coinciden con el etiquetador ciego).\n"
        )
    r = evaluar(tr, ev, args.seed, args.boot, con_mlp=not args.sin_mlp)
    r["n_archivo_evaluacion"] = n_archivo
    r["filtro"] = "solo_coincidentes" if args.solo_coincidentes else None
    imprimir(r)
    if args.solo_coincidentes and len(dudosas):
        imprimir_ambiguas(tr, dudosas, args.seed)
    if args.exportar:
        m = exportar(r, Path(args.exportar), args.entrenamiento, args.evaluacion, _commit())
        print(
            f"\nEscrito en {args.exportar}: text_classifier.json ({m['modelo']['n_ngramas']} n-gramas) y text_classifier_manifest.json"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
