"""
Construye las etiquetas de cierre de la fase 4 y comprueba SOLO la puerta de tamaño muestral del protocolo (sección 3.M de
`docs/DISENO_ML_RECOMENDACION.md`): ≥ 60 cierres principales y ≥ 30 bloques de 1 km con algún cierre. Si no se cumple, el
resultado es «no concluyente: no se entrena».

No entrena ni valida nada. Antes de leer un solo dato llama a `download_osm_history.exigir_datos_verificados` con la huella
versionada: si los archivos no están completos, no son los verificados o no coinciden con la huella, se niega.

Lo que imprime y guarda son AGREGADOS (recuentos por nivel, cierres y bloques); **no se escribe ninguna etiqueta por local**
(protocolo: «No se versionan etiquetas por local»). Con `--guardar` escribe `docs/PUERTA_RIESGO_CIERRE.json`.

Uso (desde la raíz del proyecto; los datos están en `data/osm_history/`, ignorado por git):
    python tools/build_closure_labels.py
    python tools/build_closure_labels.py --guardar
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import closure_labels  # noqa: E402
from tools import download_osm_history as dh  # noqa: E402

DEFAULT_DIR = dh.SALIDA_POR_DEFECTO
RESULTADO_POR_DEFECTO = ROOT / "docs" / "PUERTA_RIESGO_CIERRE.json"
PROTOCOLO = "docs/DISENO_ML_RECOMENDACION.md, sección 3.M (v2.2)"


def leer_elementos(ruta: Path, sha256_esperado: str) -> List[dict]:
    """Los elementos de un archivo de la descarga. Lee los bytes UNA sola vez, comprueba que su sha256 es el verificado y
    parsea esos mismos bytes: así no hay ventana entre «verificar» y «leer» en la que el archivo pueda haber cambiado.
    """
    datos = Path(ruta).read_bytes()
    leido = hashlib.sha256(datos).hexdigest()
    if leido != sha256_esperado:
        raise ValueError(
            f"{ruta}: el archivo que se lee no es el que se verificó (sha256 {leido[:12]}… en vez de {str(sha256_esperado)[:12]}…)."
        )
    elementos = json.loads(datos.decode("utf-8"))["elements"]
    if not isinstance(elementos, list):
        raise ValueError(f"{ruta}: «elements» no es una lista")
    return elementos


def cargar_fotos(rutas: Dict[str, Path], hashes: Dict[str, str]) -> Dict[str, List[dict]]:
    """Agrupa los trozos verificados por instante: 2022, 2024, hoy y ciclo de vida (cada uno en dos franjas, salvo el último).
    Se niega si algún grupo queda vacío o algún archivo no encaja en ninguno: con un nombre cambiado en la descarga, «hoy»
    saldría vacío y todos los locales serían «probables» sin que nada avisara."""
    grupos = {"2022": "2022-01-01_", "2024": "2024-01-01_", "hoy": "hoy_", "ciclo": "ciclo_de_vida_"}
    asignados = {g: [a for a in sorted(rutas) if a.startswith(pref)] for g, pref in grupos.items()}
    vacios = [g for g, archivos in asignados.items() if not archivos]
    if vacios:
        raise ValueError(f"No hay archivos verificados para: {', '.join(vacios)} (archivos: {sorted(rutas)})")
    usados = {a for archivos in asignados.values() for a in archivos}
    desconocidos = sorted(a for a in rutas if a not in usados)
    if desconocidos:
        raise ValueError(f"Archivos verificados que no encajan en ningún instante conocido: {desconocidos}")
    return {g: [e for a in archivos for e in leer_elementos(rutas[a], hashes[a])] for g, archivos in asignados.items()}


def fotos_verificadas(out_dir: Path, huella: Optional[dict]):
    """LA vía para leer la descarga (la validación debe partir de aquí): exige la huella versionada, verifica con
    `exigir_datos_verificados` ANTES de leer ningún archivo y lee cada archivo UNA vez comprobando que sus bytes son los
    verificados (sha256 de la huella). Devuelve ({instante: [elementos]}, {archivo: sha256 de lo verificado})."""
    if huella is None:
        raise ValueError("falta docs/HUELLA_OSM_HISTORY.json: sin el ancla externa no se leen los datos.")
    rutas = dh.exigir_datos_verificados(out_dir, huella)  # se niega (ValueError) si algo no es utilizable
    # Correspondencia EXACTA entre lo que devuelve la verificación, el plan de descarga y la huella: no se confía en que la
    # función de verificación haya devuelto todo (si falta un fragmento, no se calculan etiquetas con una entrada incompleta).
    esperados = {f"{nombre}_{franja}.json" for nombre, franja, _, _ in dh.plan()}
    if set(rutas) != esperados or set(huella["archivos"]) != esperados:
        raise ValueError(
            "Los archivos verificados no son exactamente los del plan de descarga y los de la huella: "
            f"faltan {sorted(esperados - set(rutas))}, sobran {sorted(set(rutas) - esperados)}, "
            f"la huella tiene de más {sorted(set(huella['archivos']) - esperados)} y de menos {sorted(esperados - set(huella['archivos']))}."
        )
    # Los hashes son los del ancla externa (la huella), no los de un segundo vistazo al manifiesto.
    hashes = {a: huella["archivos"][a]["sha256"] for a in rutas}
    return cargar_fotos(rutas, hashes), hashes


def etiquetas_verificadas(out_dir: Path, huella: Optional[dict]):
    """Etiquetas de cierre (2022 → hoy) sobre `fotos_verificadas`. Devuelve (tabla de etiquetas, descartados de la población,
    {archivo: sha256 de lo verificado})."""
    fotos, hashes = fotos_verificadas(out_dir, huella)
    etiquetas, descartados = closure_labels.etiquetar(fotos["2022"], fotos["hoy"], fotos["ciclo"])
    return etiquetas, descartados, hashes


def calcular_puerta(out_dir: Path, huella: Optional[dict]) -> dict:
    """Verifica, lee y devuelve el resultado de la puerta junto con lo descartado de la población y lo que se leyó."""
    etiquetas, descartados, hashes = etiquetas_verificadas(out_dir, huella)
    resultado = closure_labels.puerta(etiquetas)
    resultado["descartados_de_la_poblacion"] = descartados
    resultado["protocolo"] = PROTOCOLO
    resultado["entradas_sha256"] = {
        a: hashes[a] for a in sorted(hashes)
    }  # lo verificado y leído, sin releer el manifiesto
    return resultado


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEFAULT_DIR), help="carpeta con la descarga verificada")
    ap.add_argument(
        "--guardar", action="store_true", help=f"escribe el resultado agregado en {RESULTADO_POR_DEFECTO.name}"
    )
    ap.add_argument("--destino", default=None, help="dónde escribir el resultado con --guardar (por defecto docs/)")
    args = ap.parse_args(argv)

    try:
        huella = dh.cargar_huella(dh.HUELLA_POR_DEFECTO)
        resultado = calcular_puerta(Path(args.out), huella)
    except (ValueError, OSError, KeyError) as e:
        print(f"ERROR: {e}")
        return 1

    n = resultado["por_nivel"]
    print(f"Población de estudio (2022, con nombre, a más de 500 m del borde): {resultado['poblacion']}")
    print(
        f"Niveles: fuerte {n['fuerte']} | superviviente {n['superviviente']} | dudoso {n['dudoso']} | probable {n['probable']}"
    )
    print(
        f"Cierres principales: {resultado['cierres_principales']} (mínimo {resultado['minimos']['cierres_principales']}) | "
        f"bloques de 1 km con algún cierre: {resultado['bloques_con_cierre']} (mínimo {resultado['minimos']['bloques_con_cierre']})"
    )
    print(f"PUERTA: {resultado['veredicto']}")
    if args.guardar:
        destino = Path(args.destino) if args.destino else RESULTADO_POR_DEFECTO
        destino.write_text(json.dumps(resultado, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Resultado agregado guardado en {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
