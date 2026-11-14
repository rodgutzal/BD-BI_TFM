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


def leer_elementos(ruta: Path) -> List[dict]:
    """Los elementos de un archivo de la descarga."""
    elementos = json.loads(Path(ruta).read_text(encoding="utf-8"))["elements"]
    if not isinstance(elementos, list):
        raise ValueError(f"{ruta}: «elements» no es una lista")
    return elementos


def cargar_fotos(rutas: Dict[str, Path]) -> Dict[str, List[dict]]:
    """Agrupa los trozos verificados por instante: 2022, hoy y ciclo de vida (cada uno en dos franjas, salvo el último).
    Se niega si algún grupo queda vacío o algún archivo no encaja en ninguno: con un nombre cambiado en la descarga, «hoy»
    saldría vacío y todos los locales serían «probables» sin que nada avisara."""
    grupos = {"2022": "2022-01-01_", "hoy": "hoy_", "ciclo": "ciclo_de_vida_"}
    asignados = {g: [a for a in sorted(rutas) if a.startswith(pref)] for g, pref in grupos.items()}
    vacios = [g for g, archivos in asignados.items() if not archivos]
    if vacios:
        raise ValueError(f"No hay archivos verificados para: {', '.join(vacios)} (archivos: {sorted(rutas)})")
    usados = {a for archivos in asignados.values() for a in archivos}
    # 2024 se verifica con el resto pero NO se usa en esta etapa (control descriptivo posterior)
    desconocidos = sorted(a for a in rutas if a not in usados and not a.startswith("2024-01-01_"))
    if desconocidos:
        raise ValueError(f"Archivos verificados que no encajan en ningún instante conocido: {desconocidos}")
    return {g: [e for a in archivos for e in leer_elementos(rutas[a])] for g, archivos in asignados.items()}


def etiquetas_verificadas(out_dir: Path, huella: Optional[dict]):
    """LA vía para leer la descarga (la validación posterior debe partir de aquí): exige la huella versionada, verifica con
    `exigir_datos_verificados` ANTES de leer ningún archivo y devuelve (tabla de etiquetas, descartados de la población, rutas).
    """
    if huella is None:
        raise ValueError("falta docs/HUELLA_OSM_HISTORY.json: sin el ancla externa no se leen los datos.")
    rutas = dh.exigir_datos_verificados(out_dir, huella)  # se niega (ValueError) si algo no es utilizable
    fotos = cargar_fotos(rutas)
    etiquetas, descartados = closure_labels.etiquetar(fotos["2022"], fotos["hoy"], fotos["ciclo"])
    return etiquetas, descartados, rutas


def calcular_puerta(out_dir: Path, huella: Optional[dict]) -> dict:
    """Verifica, lee y devuelve el resultado de la puerta junto con lo descartado de la población y lo que se leyó."""
    etiquetas, descartados, rutas = etiquetas_verificadas(out_dir, huella)
    resultado = closure_labels.puerta(etiquetas)
    resultado["descartados_de_la_poblacion"] = descartados
    resultado["protocolo"] = PROTOCOLO
    manifiesto = json.loads((Path(out_dir) / "manifest.json").read_text(encoding="utf-8"))["archivos"]
    resultado["entradas_sha256"] = {a: manifiesto[a]["sha256"] for a in sorted(rutas)}
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
