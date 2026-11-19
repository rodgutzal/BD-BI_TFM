"""Reconstruye el panorama publicado a partir de su propio `cell_counts.csv`, sin red y sin la base de datos.

Dos usos, los dos de añadir categorías al sistema:
  1. Un perfil NUEVO sobre categorías que ya están en los conteos (fase 2: `alojamiento`).
  2. Repartir en categoría propia unos POIs que estaban recolectados dentro de otra (fase 3: `belleza`, `taller`),
     renombrando las columnas `business|<valor>` a `<categoría>|<valor>` según `poi_client.CATEGORY_TAGS`.
Los dos se pueden dar a la vez, y el caso 2 puede no tener nada que mover: entonces solo se recalculan las lentes.

Por qué DERIVA en vez de regenerar (la misma razón que `tools/strip_panorama_gap.py`): el `cell_counts.csv`
publicado lleva dentro el contexto de OSM (`edificio|*`, `alojamiento|*`, `transporte|*`, `industria|*`), que es
lo que alimenta la lente de mercado «residentes». Ese contexto NO está versionado: lo descarga
`tools/download_osm_context.py` de Overpass. Regenerar el panorama desde la base de datos lo perdería y cambiaría
las lentes de mercado de las categorías anteriores sin que nadie lo pidiera. Partiendo del CSV publicado y
verificado por hash, en cambio, los conteos por celda son exactamente los mismos.

Qué cambia y qué no:
  - `cell_counts.csv`: solo si hay reparto, y entonces cambian NOMBRES de columnas. Ningún número se mueve de celda.
  - `panorama.csv`: aparecen las filas de los perfiles nuevos. Un perfil anterior solo puede cambiar si el reparto le
    quitó competencia (le pasó a `business` en la fase 3). El resto tiene que salir IDÉNTICO, y la herramienta lo
    comprueba y ABORTA si no, incluidas las columnas que falten o sobren.

Uso:
    python tools/rebuild_panorama_from_counts.py                  # comprueba y escribe en data/ml
    python tools/rebuild_panorama_from_counts.py --solo-comprobar  # no escribe nada
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

# Categorías que SALIERON del cajón y por eso hay que repartir sus columnas. Escrito a mano, no deducido, para que
# añadir una obligue a declararlo aquí y a volver a pasar la comprobación de fidelidad.
#
# `alojamiento` (fase 2) NO está aquí, y es importante: nunca estuvo en el cajón. Ya venía en los conteos como
# categoría de contexto, con las mismas columnas `alojamiento|*`, así que no hay nada que renombrar; lo único que
# hace falta es calcular su perfil. Meterla aquí buscaría columnas `business|hotel` que no existen.
SALIERON_DEL_CAJON = ("belleza", "taller")

MOTIVO = (
    "Reconstruido del panorama publicado, no regenerado desde la base, para no perder el contexto de OSM, que no "
    "está versionado. Cubre las categorías que salieron del cajón `business` (fase 3: belleza, taller) y los perfiles "
    "nuevos sobre categorías que ya estaban en los conteos (fase 2: alojamiento)."
)


def movimientos(columnas: List[str]) -> Dict[str, str]:
    """{columna vieja: columna nueva} para las columnas que cambian de categoría. Vacío si no hay nada que mover.

    Los valores de cada categoría salen de CATEGORY_TAGS, que es la única fuente de verdad, así que el reparto no
    puede desalinearse con lo que clasificaría una extracción nueva.

    Un reparto YA HECHO no es un error: devuelve el movimiento vacío y la herramienta sigue, porque su otro trabajo
    —recalcular las lentes con los perfiles de hoy— sigue teniendo sentido. Solo se queja si encuentra las dos
    columnas a la vez, que sería un reparto a medias y nadie debería tapar."""
    mapa: Dict[str, str] = {}
    presentes = set(columnas)
    for categoria in SALIERON_DEL_CAJON:
        especificaciones = CATEGORY_TAGS.get(categoria)
        if not especificaciones:
            raise ValueError(f"{categoria!r} no está en CATEGORY_TAGS: no se puede repartir lo que no está definido")
        for especificacion in especificaciones:
            clave, _, valores = str(especificacion).partition("=")
            if not valores:
                raise ValueError(f"{categoria!r} usa la clave {clave!r} entera; esta herramienta reparte por valor")
            for valor in valores.split("|"):
                vieja, nueva = f"{CAJON}|{valor}", f"{categoria}|{valor}"
                if vieja in presentes and nueva in presentes:
                    raise ValueError(f"{vieja!r} y {nueva!r} existen las dos: el reparto quedó a medias")
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
    vacias = set()  # columnas que el esquema gana pero que este perfil deja vacías: se informan, no son un fallo
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
        # Una columna NUEVA solo se tolera si para este perfil está entera vacía. Las columnas de `panorama.csv` son
        # la UNIÓN de las lentes de todos los perfiles, así que declarar un tipo de proveedor nuevo (la fase 2 añadió
        # `lavanderia` para el alojamiento) ensancha el esquema de todas las filas; a quien no lo usa le queda en NaN,
        # y entonces no ha cambiado nada suyo. Si trae algún valor, sí es un cambio y aborta.
        con_valor = [c for c in sobran if b[c].notna().any()]
        if con_valor:
            problemas.append(f"{clave}: columnas nuevas CON VALOR en un perfil que no debía cambiar: {con_valor}")
        vacias.update(c for c in sobran if c not in con_valor)
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
    if vacias and not problemas:
        print(f"   el esquema gana {sorted(vacias)}, vacías en los perfiles que no las usan: no cambia ningún valor")
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
    try:
        mapa = movimientos(list(cuentas_viejas.columns))
    except ValueError as e:
        print(f"No se puede repartir: {e}")
        return 1
    if mapa:
        print("Columnas que cambian de categoría (los conteos no se tocan):")
        for vieja, nueva in sorted(mapa.items()):
            print(f"   {vieja:28} -> {nueva:24} {int(cuentas_viejas[vieja].sum()):5} POIs")
    else:
        print("Nada que repartir: los conteos ya están agrupados como dice CATEGORY_TAGS.")

    nuevos = [c for c in DEFAULT_PROFILES if c not in anterior.get("perfiles", ())]
    print(f"Perfiles nuevos a calcular: {nuevos if nuevos else 'ninguno'}")
    if not mapa and not nuevos:
        print("No hay nada que hacer: ni columnas que repartir ni perfiles nuevos.")
        return 1

    nuevos_counts = repartir(counts, mapa)
    total_antes = sum(m.sum() for m in counts.arrays.values())
    total_despues = sum(m.sum() for m in nuevos_counts.arrays.values())
    if not np.isclose(total_antes, total_despues):
        print(f"ABORTA: el total de POIs cambió, {total_antes} -> {total_despues}. Repartir no puede crear ni perder.")
        return 1

    tabla = construir(nuevos_counts)
    # Solo se le permite cambiar al cajón, y solo si de verdad se le quitaron columnas. Sin reparto, ni él cambia.
    puede_cambiar = {CAJON} if mapa else set()
    intactos = tuple(c for c in anterior.get("perfiles", ()) if c not in puede_cambiar)
    fallos = comparar(tabla, publicado, intactos)
    if fallos:
        print("\nABORTA: perfiles que tenían que salir idénticos y no lo hicieron:\n  " + "\n  ".join(fallos))
        return 1
    print(f"\nFidelidad: los {len(intactos)} perfiles que no debían cambiar salen idénticos al panorama publicado.")
    cambian = sorted(puede_cambiar) + nuevos
    print(f"Cambian a propósito: {', '.join(cambian) if cambian else 'ninguno'}.")

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
            "herramienta": "tools/rebuild_panorama_from_counts.py",
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
