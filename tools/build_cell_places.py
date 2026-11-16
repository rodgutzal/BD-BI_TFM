"""
Dice dónde está cada celda del panorama en palabras: su CALLE con nombre y su LOCALIDAD (consejo local de Malta), con
datos de OpenStreetMap.

Qué hace y qué NO hace:
  - Hace DOS consultas a Overpass (los límites administrativos de nivel 8 y las vías con nombre de la rejilla), con el
    cliente y el User-Agent del proyecto y una pausa entre ellas. Después asigna cada celda en LOCAL, con
    punto-en-polígono y distancia a segmentos (no se consulta una vez por celda).
  - Escribe data/ml/cell_places.csv y cell_places_manifest.json (sha256, fecha de la base de OSM, atribución ODbL).
  - NO toca panorama.csv, cell_counts.csv ni la base de datos.
  - `--dry-run` muestra la consulta sin hacer ninguna llamada de red.

Uso (desde la raíz del proyecto):
    python tools/build_cell_places.py --dry-run
    python tools/build_cell_places.py
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import grid, panorama, places  # noqa: E402
from src.poi_client import OverpassClient  # noqa: E402

TIMEOUT_SERVIDOR_S = 150
TIMEOUT_HTTP_S = 240
PAUSA_S = 12  # entre las dos consultas, para no cargar el servicio público


def _bbox() -> str:
    return f"{grid.SOUTH:.6f},{grid.WEST:.6f},{grid.NORTH:.6f},{grid.EAST:.6f}"


def construir_consulta() -> str:
    """Los límites de las localidades (consejos locales)."""
    return (
        f"[out:json][timeout:{TIMEOUT_SERVIDOR_S}];\n"
        f'relation["boundary"="administrative"]["admin_level"="{places.NIVEL_LOCALIDAD}"]({_bbox()});\n'
        "out geom;"
    )


def construir_consulta_calles() -> str:
    """Las vías con nombre. Sin nombre no sirven como rótulo, así que no se piden."""
    return f'[out:json][timeout:{TIMEOUT_SERVIDOR_S}];\nway["highway"]["name"]({_bbox()});\nout geom;'


def pedir(cliente, consulta: str):
    """Prueba cada espejo en orden; devuelve (JSON, espejo) o lanza RuntimeError si todos fallan."""
    ultimo = None
    for endpoint in cliente.endpoints:
        try:
            r = cliente.session.post(endpoint, data={"data": consulta}, timeout=TIMEOUT_HTTP_S)
            r.raise_for_status()
            return r.json(), endpoint
        except Exception as e:  # red, HTTP o JSON inválido: se prueba el siguiente espejo
            ultimo = e
    raise RuntimeError(f"Todos los espejos de Overpass fallaron. Último error: {ultimo}")


def celdas_del_panorama(data_dir: Path) -> pd.DataFrame:
    """cell_id, lat y lon de cada celda activa (únicas entre perfiles) de panorama.csv."""
    p = panorama.read_panorama(data_dir)
    return p[["cell_id", "lat", "lon"]].drop_duplicates("cell_id").reset_index(drop=True)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "ml"), help="directorio con panorama.csv (y destino)")
    ap.add_argument("--dry-run", action="store_true", help="muestra la consulta sin hacer ninguna llamada de red")
    ap.add_argument(
        "--crudo", help="JSON de una respuesta de Overpass ya descargada con esta misma consulta (no se llama a la red)"
    )
    ap.add_argument("--crudo-calles", help="JSON de la consulta de calles ya descargado (no se llama a la red)")
    args = ap.parse_args(argv)
    consulta, consulta_calles = construir_consulta(), construir_consulta_calles()
    if args.dry_run:
        print(f"{consulta}\n\n{consulta_calles}\n\n(dry-run: no se hizo ninguna llamada de red)")
        return 0

    data_dir = Path(args.data_dir)
    celdas = celdas_del_panorama(data_dir)
    cliente = None if (args.crudo and args.crudo_calles) else OverpassClient(timeout=TIMEOUT_HTTP_S, max_retries=1)

    def traer(archivo, q):
        if archivo:
            return json.loads(Path(archivo).read_text(encoding="utf-8")), "respuesta guardada en un archivo local"
        return pedir(cliente, q)

    datos, espejo = traer(args.crudo, consulta)
    localidades = places.parse_boundaries(datos.get("elements", []))
    if not localidades:
        print("Overpass no devolvió ninguna localidad: no se escribe nada.")
        return 1
    incompletas = sorted(l.nombre for l in localidades if l.tramos_descartados)
    if incompletas:
        print(f"AVISO: límites incompletos (tramos sin cerrar) en: {', '.join(incompletas)}")

    if not args.crudo_calles and not args.crudo:
        time.sleep(PAUSA_S)  # dos consultas seguidas al servicio público: se espera entre ellas
    datos_calles, _ = traer(args.crudo_calles, consulta_calles)
    calles = places.parse_streets(datos_calles.get("elements", []))
    if not len(calles):
        print("Overpass no devolvió ninguna calle con nombre: no se escribe nada.")
        return 1

    tabla = pd.concat(
        [
            celdas[["cell_id"]],
            places.assign_places(celdas["lat"], celdas["lon"], localidades),
            places.nearest_street(celdas["lat"], celdas["lon"], calles),
        ],
        axis=1,
    )
    manifiesto = places.write_places(
        data_dir,
        tabla,
        {
            "consulta": consulta,
            "consulta_calles": consulta_calles,
            "espejo": espejo,
            "base_osm": datos.get("osm3s", {}).get("timestamp_osm_base", ""),
            "ejecutado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "localidades": len(localidades),
            "localidades_incompletas": incompletas,
            "calles": len(calles),
            "nivel_admin": places.NIVEL_LOCALIDAD,
        },
    )
    print(
        f"{len(localidades)} localidades | {len(calles)} calles con nombre | {manifiesto['filas']} celdas "
        f"| por cercanía: {manifiesto['por_cercania']} | sin localidad: {manifiesto['sin_localidad']} "
        f"| sin calle: {manifiesto['sin_calle']} | escrito en {data_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
