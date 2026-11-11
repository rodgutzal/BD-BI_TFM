"""
Descarga de Overpass (OpenStreetMap) el CONTEXTO que falta para medir mercado y proveedores por celda (fase 1b de
docs/DISENO_ML_RECOMENDACION.md): edificios, alojamiento turístico, transporte público y suelo industrial/mayoristas.

Qué hace y qué NO hace:
  - Descarga a ARCHIVOS JSON en un directorio que se indica (--out). NO toca la base de datos.
  - Usa el cliente y el User-Agent del proyecto (OverpassClient), con una pausa entre peticiones, un tiempo máximo de
    servidor y el edificado partido en franjas para no cargar el servicio público.
  - Si un espejo falla prueba el siguiente; si todos fallan para ese trozo, lo anota y sigue con el resto.
  - `--dry-run` muestra las consultas sin hacer NINGUNA llamada de red.

Uso (desde la raíz del proyecto):
    python tools/download_osm_context.py --out C:\\temp\\osm_context --dry-run
    python tools/download_osm_context.py --out C:\\temp\\osm_context
    python tools/download_osm_context.py --out C:\\temp\\osm_context --themes alojamiento transporte
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import grid  # noqa: E402
from src.poi_client import OverpassClient  # noqa: E402

PAUSA_S = 12
TIMEOUT_SERVIDOR_S = 150
TIMEOUT_HTTP_S = 190
FRANJAS_EDIFICIOS = 3

ALOJAMIENTO = "hotel|hostel|guest_house|apartment|motel|resort|chalet|camp_site"

# Cada tema: lista de cláusulas Overpass con {bbox}. `franjas`: en cuántas franjas de latitud se parte el área.
TEMAS: Dict[str, dict] = {
    "edificios": {"franjas": FRANJAS_EDIFICIOS, "clausulas": ['way["building"]({bbox});']},
    "alojamiento": {
        "franjas": 1,
        "clausulas": [
            f'node["tourism"~"^({ALOJAMIENTO})$"]({{bbox}});',
            f'way["tourism"~"^({ALOJAMIENTO})$"]({{bbox}});',
        ],
    },
    "transporte": {
        "franjas": 1,
        "clausulas": [
            'node["highway"="bus_stop"]({bbox});',
            'node["public_transport"~"^(platform|stop_position|station)$"]({bbox});',
            'nwr["amenity"="ferry_terminal"]({bbox});',
            'node["railway"~"^(station|halt|tram_stop)$"]({bbox});',
        ],
    },
    "industria": {
        "franjas": 1,
        "clausulas": [
            'way["landuse"="industrial"]({bbox});',
            'nwr["shop"="wholesale"]({bbox});',
            'nwr["industrial"]({bbox});',
        ],
    },
    "suelo_residencial": {"franjas": 1, "clausulas": ['way["landuse"="residential"]({bbox});']},
}


def bbox_franjas(n: int) -> List[Tuple[float, float, float, float]]:
    """Parte la rejilla en `n` franjas de latitud contiguas (sur, oeste, norte, este) que cubren TODA el área sin
    huecos ni solapes."""
    if n < 1:
        raise ValueError("n debe ser >= 1")
    alto = (grid.NORTH - grid.SOUTH) / n
    return [
        (grid.SOUTH + i * alto, grid.WEST, grid.SOUTH + (i + 1) * alto if i < n - 1 else grid.NORTH, grid.EAST)
        for i in range(n)
    ]


def construir_consulta(clausulas: List[str], bbox: Tuple[float, float, float, float]) -> str:
    """Consulta Overpass QL para un trozo: salida JSON con centro y etiquetas."""
    texto_bbox = ",".join(f"{v:.6f}" for v in bbox)
    cuerpo = "\n  ".join(c.format(bbox=texto_bbox) for c in clausulas)
    return f"[out:json][timeout:{TIMEOUT_SERVIDOR_S}];\n(\n  {cuerpo}\n);\nout center tags;"


def consultas(temas: List[str]) -> List[Tuple[str, int, str]]:
    """(tema, número de trozo, consulta) de todo lo que habría que pedir."""
    plan = []
    for tema in temas:
        for i, bbox in enumerate(bbox_franjas(TEMAS[tema]["franjas"])):
            plan.append((tema, i, construir_consulta(TEMAS[tema]["clausulas"], bbox)))
    return plan


def pedir(cliente, consulta: str) -> dict:
    """Envía la consulta probando cada espejo en orden; devuelve el JSON o lanza RuntimeError si todos fallan."""
    ultimo = None
    for endpoint in cliente.endpoints:
        try:
            r = cliente.session.post(endpoint, data={"data": consulta}, timeout=TIMEOUT_HTTP_S)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # red, HTTP o JSON inválido: se prueba el siguiente espejo
            ultimo = e
    raise RuntimeError(f"Todos los espejos de Overpass fallaron. Último error: {ultimo}")


def descargar(cliente, out_dir: Path, temas: List[str], pausa_s: float = PAUSA_S, log=print) -> Dict[str, dict]:
    """Descarga cada trozo a `out_dir/<tema>_<n>.json` y devuelve un resumen por tema:
    {tema: {"elementos": n, "trozos_ok": k, "trozos_fallidos": f}}. NO escribe nada fuera de `out_dir`."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    resumen: Dict[str, dict] = {t: {"elementos": 0, "trozos_ok": 0, "trozos_fallidos": 0} for t in temas}
    plan = consultas(temas)
    for k, (tema, i, consulta) in enumerate(plan):
        t0 = time.perf_counter()
        try:
            datos = pedir(cliente, consulta)
            elementos = datos.get("elements", [])
            (out_dir / f"{tema}_{i}.json").write_text(
                json.dumps({"tema": tema, "trozo": i, "elements": elementos}), encoding="utf-8"
            )
            resumen[tema]["elementos"] += len(elementos)
            resumen[tema]["trozos_ok"] += 1
            log(f"   {tema} [{i}]: {len(elementos):6} elementos ({time.perf_counter() - t0:.0f} s)")
        except RuntimeError as e:
            resumen[tema]["trozos_fallidos"] += 1
            log(f"   {tema} [{i}]: FALLÓ ({e})")
        if k < len(plan) - 1:
            time.sleep(pausa_s)
    return resumen


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="directorio donde guardar los JSON (NO la base de datos)")
    ap.add_argument("--themes", nargs="+", choices=list(TEMAS), default=list(TEMAS))
    ap.add_argument("--dry-run", action="store_true", help="muestra las consultas sin hacer ninguna llamada de red")
    ap.add_argument("--pausa", type=float, default=PAUSA_S, help="segundos de pausa entre peticiones")
    args = ap.parse_args(argv)

    plan = consultas(args.themes)
    print(
        f"Área: lat {grid.SOUTH}-{grid.NORTH}, lon {grid.WEST}-{grid.EAST} | trozos a pedir: {len(plan)} | salida: {args.out}"
    )
    if args.dry_run:
        for tema, i, consulta in plan:
            print(f"\n--- {tema} [{i}] ---\n{consulta}")
        print("\n(dry-run: no se hizo ninguna llamada de red)")
        return 0

    resumen = descargar(OverpassClient(timeout=TIMEOUT_HTTP_S, max_retries=1), Path(args.out), args.themes, args.pausa)
    print("\nResumen:")
    for tema, r in resumen.items():
        print(
            f"   {tema:18} {r['elementos']:7} elementos | trozos ok {r['trozos_ok']} | fallidos {r['trozos_fallidos']}"
        )
    return 0 if all(r["trozos_fallidos"] == 0 for r in resumen.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
