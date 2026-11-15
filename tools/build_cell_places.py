"""
Asigna a cada celda del panorama el nombre de su LOCALIDAD (consejo local de Malta) con límites de OpenStreetMap.

Qué hace y qué NO hace:
  - Hace UNA sola consulta a Overpass (relaciones administrativas de nivel 8 dentro de la rejilla), con el cliente y el
    User-Agent del proyecto, y asigna cada celda con un punto-en-polígono LOCAL (no se consulta una vez por celda).
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import grid, panorama, places  # noqa: E402
from src.poi_client import OverpassClient  # noqa: E402

TIMEOUT_SERVIDOR_S = 120
TIMEOUT_HTTP_S = 150


def construir_consulta() -> str:
    bbox = f"{grid.SOUTH:.6f},{grid.WEST:.6f},{grid.NORTH:.6f},{grid.EAST:.6f}"
    return (
        f"[out:json][timeout:{TIMEOUT_SERVIDOR_S}];\n"
        f'relation["boundary"="administrative"]["admin_level"="{places.NIVEL_LOCALIDAD}"]({bbox});\n'
        "out geom;"
    )


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
    args = ap.parse_args(argv)
    consulta = construir_consulta()
    if args.dry_run:
        print(consulta, "\n\n(dry-run: no se hizo ninguna llamada de red)")
        return 0

    data_dir = Path(args.data_dir)
    celdas = celdas_del_panorama(data_dir)
    if args.crudo:
        datos, espejo = (
            json.loads(Path(args.crudo).read_text(encoding="utf-8")),
            "respuesta guardada en un archivo local",
        )
    else:
        datos, espejo = pedir(OverpassClient(timeout=TIMEOUT_HTTP_S, max_retries=1), consulta)
    localidades = places.parse_boundaries(datos.get("elements", []))
    if not localidades:
        print("Overpass no devolvió ninguna localidad: no se escribe nada.")
        return 1
    incompletas = sorted(l.nombre for l in localidades if l.tramos_descartados)
    if incompletas:
        print(f"AVISO: límites incompletos (tramos sin cerrar) en: {', '.join(incompletas)}")
    asignacion = places.assign_places(celdas["lat"], celdas["lon"], localidades)
    tabla = pd.concat([celdas[["cell_id"]], asignacion], axis=1)
    manifiesto = places.write_places(
        data_dir,
        tabla,
        {
            "consulta": consulta,
            "espejo": espejo,
            "base_osm": datos.get("osm3s", {}).get("timestamp_osm_base", ""),
            "ejecutado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "localidades": len(localidades),
            "localidades_incompletas": incompletas,
            "nivel_admin": places.NIVEL_LOCALIDAD,
        },
    )
    print(
        f"{len(localidades)} localidades | {manifiesto['filas']} celdas | por cercanía: {manifiesto['por_cercania']} "
        f"| sin localidad: {manifiesto['sin_localidad']} | escrito en {data_dir}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
