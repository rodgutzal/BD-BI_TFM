"""Reparte en categorías propias unos POIs que ya estaban recolectados dentro de otra, y recalcula el panorama.

Por qué DERIVA en vez de regenerar (la misma razón que `tools/strip_panorama_gap.py`): el `cell_counts.csv`
publicado lleva dentro el contexto de OSM (`edificio|*`, `alojamiento|*`, `transporte|*`, `industria|*`), que es
lo que alimenta la lente de mercado «residentes». Ese contexto NO está versionado: lo descarga
`tools/download_osm_context.py` de Overpass. Regenerar el panorama desde la base de datos lo perdería y cambiaría
las lentes de mercado de las SIETE categorías anteriores sin que nadie lo pidiera. Partiendo del CSV publicado y
verificado por hash, en cambio, los conteos por celda son exactamente los mismos: lo único que cambia es la
ETIQUETA con la que están agrupados.

Lo que hace, en una frase: renombra las columnas `business|<valor>` a `<categoría nueva>|<valor>` para los valores
que `poi_client.CATEGORY_TAGS` asigna ahora a una categoría propia, y vuelve a calcular las lentes de todos los
perfiles. Los totales por celda no cambian; el reparto, sí.

Qué cambia y qué no:
  - `cell_counts.csv`: cambian los NOMBRES de 5 columnas. Ningún número se mueve de celda.
  - `panorama.csv`: aparecen los perfiles nuevos, y el perfil `business` cambia, porque esos POIs dejan de ser su
    competencia directa y pasan a indirecta (ver `business_profiles.DEFAULT_PROFILES`). Los otros seis perfiles
    tienen que salir IDÉNTICOS, y la herramienta lo comprueba y aborta si no.

Uso:
    python tools/resplit_panorama_categories.py                  # comprueba y escribe en data/ml
    python tools/resplit_panorama_categories.py --solo-comprobar  # no escribe nada
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import panorama  # noqa: E402
from src.ml.business_profiles import DEFAULT_PROFILES  # noqa: E402
from src.ml.cell_counts import CellCounts  # noqa: E402
from src.poi_client import CATEGORY_TAGS  # noqa: E402

DEFAULT_DIR = ROOT / "data" / "ml"

# Categorías que antes caían en el cajón y ahora tienen la suya. Está escrito a mano, y no deducido, para que
# añadir una categoría obligue a declararlo aquí y a volver a ejecutar la comprobación de fidelidad.
CAJON = "business"
NUEVAS = ("belleza", "taller")

# Perfiles que NO deben cambiar ni un dígito al repartir. `business` sí cambia (pierde competencia directa) y los
# nuevos no existían.
MOTIVO = (
    "Las peluquerías/estética (shop=hairdresser|beauty) y los talleres (shop=car_repair|truck_repair|tyres) ya se "
    "recolectaban dentro de `business`, el cajón de shop/office, así que su competencia era «cualquier comercio» y "
    "no se podían analizar como lo que son. Ahora tienen categoría propia en CATEGORY_TAGS y perfil propio. Derivado "
    "del panorama publicado para no perder el contexto de OSM, que no está versionado."
)


def movimientos(columnas: List[str]) -> Dict[str, str]:
    """{columna vieja: columna nueva} para las columnas que cambian de categoría.

    Los valores de cada categoría nueva salen de CATEGORY_TAGS, que es la única fuente de verdad, así que el reparto
    no puede desalinearse con lo que clasificaría una extracción nueva."""
    mapa: Dict[str, str] = {}
    presentes = set(columnas)
    for categoria in NUEVAS:
        especificaciones = CATEGORY_TAGS.get(categoria)
        if not especificaciones:
            raise ValueError(f"{categoria!r} no está en CATEGORY_TAGS: no se puede repartir lo que no está definido")
        for especificacion in especificaciones:
            clave, _, valores = str(especificacion).partition("=")
            if not valores:
                raise ValueError(f"{categoria!r} usa la clave {clave!r} entera; esta herramienta reparte por valor")
            for valor in valores.split("|"):
                vieja, nueva = f"{CAJON}|{valor}", f"{categoria}|{valor}"
                if nueva in presentes:
                    raise ValueError(f"{nueva!r} ya existe: el reparto ya estaba hecho")
                if vieja in presentes:
                    mapa[vieja] = nueva
    return mapa


def repartir(counts: CellCounts, mapa: Dict[str, str]) -> CellCounts:
    """Mismos conteos, otra etiqueta. No se suma ni se resta nada."""
    arrays = {}
    for (categoria, subcategoria), matriz in counts.arrays.items():
        columna = f"{categoria}|{subcategoria}"
        destino = mapa.get(columna, columna)
        cat_nueva, _, sub_nueva = destino.partition("|")
        arrays[(cat_nueva, sub_nueva)] = matriz
    return CellCounts(arrays, 0, int(sum(m.sum() for m in arrays.values())))


def construir(counts: CellCounts) -> pd.DataFrame:
    partes = [panorama.build_panorama(counts, perfil) for perfil in DEFAULT_PROFILES.values()]
    return pd.concat(partes)


def comparar(nuevo: pd.DataFrame, publicado: pd.DataFrame, perfiles: Tuple[str, ...]) -> List[str]:
    """Diferencias en los perfiles que NO deberían cambiar. Lista vacía = el reparto fue fiel."""
    problemas = []
    for clave in perfiles:
        a = publicado[publicado["perfil"] == clave].set_index("cell_id").sort_index()
        b = nuevo[nuevo["perfil"] == clave].sort_index()
        if len(a) != len(b):
            problemas.append(f"{clave}: {len(a)} filas publicadas frente a {len(b)}")
            continue
        # Las columnas que falten o sobren son por sí mismas una diferencia: comparar solo las comunes dejaba pasar
        # una columna renombrada o perdida por el mismo guardia que dice «salen idénticos». Lo señaló un code-review.
        faltan = [c for c in a.columns if c not in b.columns and c != "perfil"]
        sobran = [c for c in b.columns if c not in a.columns and c != "perfil"]
        if faltan:
            problemas.append(f"{clave}: faltan columnas que el panorama publicado sí tiene: {faltan}")
        if sobran:
            problemas.append(f"{clave}: aparecen columnas nuevas en un perfil que no debía cambiar: {sobran}")
        comunes = [c for c in a.columns if c in b.columns and c != "perfil"]
        for columna in comunes:
            x, y = a[columna], b[columna]
            if x.dtype.kind in "if" and y.dtype.kind in "if":
                iguales = np.allclose(x.to_numpy(dtype=float), y.to_numpy(dtype=float), equal_nan=True, atol=1e-9)
            else:
                # Se comparan los textos COMO SE ESCRIBEN, no como pandas los infiere al leer: una columna vacía en
                # el CSV (p. ej. `modelo_brecha`, que el PR #77 dejó sin valor) vuelve de read_csv como NaN float,
                # mientras build_panorama la trae como "". En disco las dos son el mismo campo vacío, así que
                # compararlas en crudo daba una diferencia falsa.
                iguales = x.fillna("").astype(str).equals(y.fillna("").astype(str))
            if not iguales:
                problemas.append(f"{clave}.{columna}: cambió y no debía")
    return problemas


def _commit() -> str:
    especificacion = importlib.util.spec_from_file_location("export_ml_inputs", ROOT / "tools" / "export_ml_inputs.py")
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo.git_commit()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help=f"directorio de data/ml (default: {DEFAULT_DIR})")
    ap.add_argument("--solo-comprobar", action="store_true", help="comprueba la fidelidad y no escribe nada")
    args = ap.parse_args(argv)
    directorio = Path(args.dir)

    problemas = panorama.verify_outputs(directorio)
    if problemas:
        print("Los artefactos publicados no coinciden con su manifiesto:\n  " + "\n  ".join(problemas))
        return 1

    anterior = json.loads((directorio / panorama.ARCHIVOS["manifest"]).read_text(encoding="utf-8"))
    publicado = pd.read_csv(directorio / panorama.ARCHIVOS["panorama"])
    counts = panorama.read_counts(directorio, verificar=False)

    cuentas_viejas = counts.to_frame(counts.total_grid() > 0)
    mapa = movimientos(list(cuentas_viejas.columns))
    if not mapa:
        print("No hay nada que repartir: ninguna columna del cajón corresponde a las categorías nuevas.")
        return 1
    print("Columnas que cambian de categoría (los conteos no se tocan):")
    for vieja, nueva in sorted(mapa.items()):
        print(f"   {vieja:28} -> {nueva:24} {int(cuentas_viejas[vieja].sum()):5} POIs")

    nuevos_counts = repartir(counts, mapa)
    total_antes = sum(m.sum() for m in counts.arrays.values())
    total_despues = sum(m.sum() for m in nuevos_counts.arrays.values())
    if not np.isclose(total_antes, total_despues):
        print(f"ABORTA: el total de POIs cambió, {total_antes} -> {total_despues}. Repartir no puede crear ni perder.")
        return 1

    tabla = construir(nuevos_counts)
    intactos = tuple(c for c in anterior.get("perfiles", ()) if c != CAJON)
    fallos = comparar(tabla, publicado, intactos)
    if fallos:
        print("\nABORTA: perfiles que tenían que salir idénticos y no lo hicieron:\n  " + "\n  ".join(fallos))
        return 1
    print(f"\nFidelidad: los {len(intactos)} perfiles que no debían cambiar salen idénticos al panorama publicado.")
    print(f"Cambian a propósito: {CAJON} (pierde competencia directa) y los nuevos {', '.join(NUEVAS)}.")

    if args.solo_comprobar:
        print("\n--solo-comprobar: no se ha escrito nada.")
        return 0

    manifiesto = {
        "procedencia": dict(anterior.get("procedencia", {}), commit=_commit()),
        "parametros": anterior.get("parametros", {}),
        "perfiles": list(DEFAULT_PROFILES),
        "brecha": anterior.get("brecha", {}),
        "advertencia": anterior.get("advertencia", ""),
        "derivado": {
            "herramienta": "tools/resplit_panorama_categories.py",
            "motivo": MOTIVO,
            "columnas_movidas": {k: v for k, v in sorted(mapa.items())},
            "perfiles_intactos": list(intactos),
            "panorama_sha256_anterior": anterior.get("archivos", {}).get("panorama.csv", {}).get("sha256"),
            "cell_counts_sha256_anterior": anterior.get("archivos", {}).get("cell_counts.csv", {}).get("sha256"),
            "derivado_anterior": anterior.get("derivado"),
        },
    }
    completo = panorama.write_outputs(directorio, tabla, nuevos_counts, manifiesto)
    print(f"\nEscrito en {directorio}:")
    for nombre, info in completo["archivos"].items():
        print(f"   {nombre:20} {info['filas']:>7} filas  sha256 {info['sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
