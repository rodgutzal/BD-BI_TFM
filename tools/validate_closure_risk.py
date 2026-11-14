"""
Estudio de riesgo de cierre (fase 4): valida con el protocolo fijado de antemano (sección 3.M de
`docs/DISENO_ML_RECOMENDACION.md`) si el entorno de un local en 2022 (competencia y densidad) predice que ya no figura hoy.

Es una señal de ENTORNO, no una probabilidad de cierre ni de rentabilidad. Lee los datos solo por la vía verificada
(`tools/build_closure_labels.fotos_verificadas`: huella versionada, verificación y lectura única con sha256), aplica primero la
puerta de tamaño muestral y, si se cumple, entrena y evalúa (`src/ml/closure_validation.py`): regresión logística y boosting
frente a las líneas base triviales, AUC por repetición con intervalos por remuestreo de bloques y la regla de decisión.

Las sensibilidades A (solo cierres fuertes), B (con Foursquare) y el control de 2024 son DESCRIPTIVOS y no influyen en la
decisión; la C (contexto estático de 2022) no se ejecuta porque ese contexto no se ha descargado con fecha.

**No se cambia nada después de ver los resultados.** Si se encuentra un error, se documenta y se repite entera declarando que
hubo una repetición. Se imprime y se guarda (con `--guardar`, en `docs/RESULTADO_RIESGO_CIERRE.json`) solo lo agregado: nada por
local (ni nombres, ni posiciones, ni identificadores).

Uso (desde la raíz del proyecto; los datos están en `data/osm_history/`, ignorado por git):
    python tools/validate_closure_risk.py
    python tools/validate_closure_risk.py --guardar
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.foursquare_client import build_search_points  # noqa: E402
from src.locations import LOCATIONS, ROUTES  # noqa: E402
from src.ml import closure_features, closure_labels, closure_validation, data_access, grid  # noqa: E402
from tools import build_closure_labels as etiquetas_tool  # noqa: E402
from tools import download_osm_history as dh  # noqa: E402

DEFAULT_DIR = dh.SALIDA_POR_DEFECTO
DEFAULT_DB = ROOT / "data" / "mobility.db"
RESULTADO_POR_DEFECTO = ROOT / "docs" / "RESULTADO_RIESGO_CIERRE.json"
PROTOCOLO = "docs/DISENO_ML_RECOMENDACION.md, sección 3.M (v2.3)"


def preparar(etiquetas: pd.DataFrame, elementos_del_instante: Iterable[dict], columna: str):
    """Locales con etiqueta definida en `columna` (los dudosos quedan fuera), sus variables, la etiqueta y su celda."""
    t = etiquetas[etiquetas[columna].notna()].reset_index(drop=True)
    X = closure_features.variables(t, elementos_del_instante)
    filas, cols = grid.cell_index(t["lat"].to_numpy(), t["lon"].to_numpy())
    return t, X, t[columna].astype(int).to_numpy(), filas, cols


def _validar_etiqueta(etiquetas, elementos, columna, n_remuestreos, repeticiones) -> dict:
    t, X, y, filas, cols = preparar(etiquetas, elementos, columna)
    resultado = closure_validation.evaluar(X, y, filas, cols, repeticiones=repeticiones, n_remuestreos=n_remuestreos)
    resultado["tasa_por_categoria"] = closure_validation.tasa_por_categoria(t, y)
    return resultado


def _descriptivo(etiquetas, elementos, columna, n_remuestreos, repeticiones) -> dict:
    """Ejecuta una sensibilidad o control SOLO si tiene al menos 30 positivos; si no, informa del recuento."""
    positivos = int((etiquetas[columna] == 1).sum())
    if positivos < closure_validation.MIN_POSITIVOS_DESCRIPTIVOS:
        return {
            "ejecutado": False,
            "motivo": f"solo {positivos} positivos (mínimo {closure_validation.MIN_POSITIVOS_DESCRIPTIVOS})",
            "positivos": positivos,
        }
    resultado = _validar_etiqueta(etiquetas, elementos, columna, n_remuestreos, repeticiones)
    resultado["ejecutado"] = True
    return resultado


def huella_de_foursquare(foursquare: Optional[pd.DataFrame]) -> dict:
    """Recuento y sha256 (independiente del orden) de las filas de Foursquare usadas por la sensibilidad B: la base está viva
    y la entrada de B debe quedar identificada, igual que las de OpenStreetMap. Solo agregados: ni nombres ni posiciones.
    """
    if foursquare is None or len(foursquare) == 0:
        return {"filas": 0, "sha256": None}
    filas = sorted(
        f"{n}|{la!r}|{lo!r}" for n, la, lo in zip(foursquare["name"], foursquare["latitude"], foursquare["longitude"])
    )
    return {"filas": int(len(foursquare)), "sha256": hashlib.sha256("\n".join(filas).encode("utf-8")).hexdigest()}


def estudio(
    fotos: Dict[str, list],
    foursquare: Optional[pd.DataFrame],
    puntos_busqueda: Iterable[Tuple[float, float]],
    n_remuestreos: int = closure_validation.N_REMUESTREOS,
    repeticiones: int = closure_validation.N_REPETICIONES,
) -> dict:
    """El estudio completo sobre las fotos ya leídas y verificadas. Devuelve solo agregados."""
    etiquetas, descartados = closure_labels.etiquetar(fotos["2022"], fotos["hoy"], fotos["ciclo"])
    puerta = closure_labels.puerta(etiquetas)
    puerta["descartados_de_la_poblacion"] = descartados
    resultado: dict = {"protocolo": PROTOCOLO, "puerta": puerta, "foursquare": huella_de_foursquare(foursquare)}
    if not puerta["pasa"]:
        resultado["principal"] = None
        resultado["conclusion"] = "no concluyente: no se entrena (no se cumple la puerta de tamaño muestral)"
        return resultado
    principal = _validar_etiqueta(etiquetas, fotos["2022"], "cierre_principal", n_remuestreos, repeticiones)
    resultado["principal"] = principal
    resultado["conclusion"] = (
        "señal de entorno UTILIZABLE según la regla fijada (pasaría a un PR aparte con su revisión)"
        if principal["utilizable"]
        else "NO utilizable: ningún candidato cumple la regla fijada; queda como hallazgo del TFM y no se expone nada al usuario"
    )
    descriptivos: Dict[str, dict] = {
        "A_solo_fuertes": _descriptivo(etiquetas, fotos["2022"], "cierre_fuerte", n_remuestreos, repeticiones)
    }
    etiquetas_2024, _ = closure_labels.etiquetar(fotos["2024"], fotos["hoy"], fotos["ciclo"])
    descriptivos["control_2024_a_hoy"] = _descriptivo(
        etiquetas_2024, fotos["2024"], "cierre_principal", n_remuestreos, repeticiones
    )
    if foursquare is None or len(foursquare) == 0:
        descriptivos["B_con_foursquare"] = {"ejecutado": False, "motivo": "no hay datos de Foursquare"}
    else:
        etiquetas_b = closure_labels.sensibilidad_b(etiquetas, foursquare, puntos_busqueda)
        descriptivos["B_con_foursquare"] = _descriptivo(
            etiquetas_b, fotos["2022"], "cierre_principal", n_remuestreos, repeticiones
        )
    descriptivos["C_contexto_estatico_2022"] = {
        "ejecutado": False,
        "motivo": "el contexto estático de 2022 no se ha descargado con fecha (exigiría ampliar la herramienta de descarga)",
    }
    resultado["descriptivos"] = descriptivos
    return resultado


def _fmt(modelo: dict) -> str:
    return f"{modelo['media']:.3f} [{modelo['ic'][0]:.3f}, {modelo['ic'][1]:.3f}]"


def imprimir(resultado: dict) -> None:
    p = resultado["puerta"]
    print(
        f"Puerta: {p['cierres_principales']} cierres principales en {p['bloques_con_cierre']} bloques -> {p['veredicto']}"
    )
    if resultado.get("principal") is None:
        print(f"CONCLUSIÓN: {resultado['conclusion']}")
        return
    r = resultado["principal"]
    print(
        f"\nANÁLISIS PRINCIPAL ({r['n']} locales, {r['positivos']} cierres, {r['bloques']} bloques de 1 km); AUC medio [IC 97,5 %]"
    )
    for n in closure_validation.MODELOS:
        print(f"   {n:15} {_fmt(r['auc'][n])}")
    print(f"   mejor línea base trivial: {r['mejor_linea_base']}")
    for c in closure_validation.CANDIDATOS:
        d, ok = r["diferencia_con_la_mejor_linea_base"][c], r["decision"][c]
        print(
            f"   {c:10} diferencia con la mejor base {_fmt(d)} | (a) AUC>0,5: {ok['a']} | (b) mejora la base: {ok['b']} | cumple: {ok['cumple']}"
        )
    print(f"\nCONCLUSIÓN: {resultado['conclusion']}")
    print("\nDESCRIPTIVOS (no influyen en la decisión):")
    for nombre, d in resultado["descriptivos"].items():
        if not d.get("ejecutado"):
            print(f"   {nombre}: no ejecutado ({d['motivo']})")
            continue
        aucs = " | ".join(f"{n} {d['auc'][n]['media']:.3f}" for n in closure_validation.MODELOS)
        print(f"   {nombre}: {d['n']} locales, {d['positivos']} positivos | AUC {aucs}")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEFAULT_DIR), help="carpeta con la descarga verificada")
    ap.add_argument(
        "--db", default=str(DEFAULT_DB), help="base con la tabla pois_foursquare (solo lectura; sensibilidad B)"
    )
    ap.add_argument(
        "--guardar", action="store_true", help=f"escribe el resultado agregado en {RESULTADO_POR_DEFECTO.name}"
    )
    ap.add_argument("--destino", default=None, help="dónde escribir el resultado con --guardar (por defecto docs/)")
    args = ap.parse_args(argv)

    try:
        huella = dh.cargar_huella(dh.HUELLA_POR_DEFECTO)
        fotos, hashes = etiquetas_tool.fotos_verificadas(Path(args.out), huella)
        foursquare = data_access.load_pois_foursquare(args.db) if Path(args.db).exists() else None
        puntos = [(p.latitude, p.longitude) for p in build_search_points(LOCATIONS, ROUTES).values()]
        resultado = estudio(fotos, foursquare, puntos)
    except (ValueError, OSError, KeyError) as e:
        print(f"ERROR: {e}")
        return 1
    resultado["entradas_sha256"] = {a: hashes[a] for a in sorted(hashes)}
    imprimir(resultado)
    if args.guardar:
        destino = Path(args.destino) if args.destino else RESULTADO_POR_DEFECTO
        destino.write_text(json.dumps(resultado, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nResultado agregado guardado en {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
