"""
Exporta el PAQUETE DE ENTRADA del ML (fase 1c): un archivo pequeño con lo único que necesitan las herramientas de
entrenamiento, para entrenar en otra máquina sin copiar `mobility.db` (~400 MB, casi todo mediciones de rutas).

Contiene los POIs de Overpass y de Foursquare, la población por zona, el tiempo de viaje medio por par de zonas y el
contexto de OSM de la fase 1b ya normalizado, más un manifiesto con fecha, commit, versiones de las librerías y el
hash de cada tabla. Ver src/ml/inputs_bundle.py.

Es de SOLO LECTURA sobre la base: la abre con `immutable=1` y escribe únicamente el paquete. Con el stack apagado.

Uso (desde la raíz del proyecto):
    python tools/export_ml_inputs.py --contexto C:\\temp\\osm_context          # -> data/ml_inputs.sqlite
    python tools/export_ml_inputs.py --out D:\\transferencia\\ml_inputs.sqlite
    python tools/export_ml_inputs.py --verify data/ml_inputs.sqlite          # en la máquina de entrenamiento

En la otra máquina, las herramientas aceptan el paquete en --db:
    python tools/validate_location_model.py --db ml_inputs.sqlite
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import inputs_bundle, osm_context  # noqa: E402

DEFAULT_DB = ROOT / "data" / "mobility.db"
DEFAULT_OUT = ROOT / "data" / "ml_inputs.sqlite"


def git_commit() -> str:
    """Commit actual del repositorio ('desconocido' si no hay git); con '+' si hay cambios sin confirmar."""
    try:
        h = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        sucio = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        return h + ("+" if sucio else "")
    except Exception:
        return "desconocido"


def verificar(ruta: Path) -> int:
    problemas = inputs_bundle.verify_bundle(ruta)
    if problemas:
        print(f"{ruta}: NO coincide con su manifiesto:\n  " + "\n  ".join(problemas))
        return 1
    m = inputs_bundle.read_manifest(ruta)
    print(f"{ruta}: íntegro (creado {m.get('creado')}, commit {m.get('commit')}, origen {m.get('origen')})")
    print(f"   sha256 del archivo: {inputs_bundle.file_hash(ruta)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB), help=f"base de origen (default: {DEFAULT_DB})")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help=f"paquete a escribir (default: {DEFAULT_OUT})")
    ap.add_argument(
        "--contexto",
        default=None,
        help="directorio con el contexto de OSM de tools/download_osm_context.py (fase 1b); sin él la tabla va vacía",
    )
    ap.add_argument("--force", action="store_true", help="reemplazar el paquete si ya existe")
    ap.add_argument(
        "--verify",
        metavar="PAQUETE",
        default=None,
        help="solo comprueba un paquete contra su manifiesto (no necesita la base) y sale",
    )
    args = ap.parse_args(argv)

    if args.verify:
        return verificar(Path(args.verify))

    contexto = osm_context.load_context(args.contexto) if args.contexto else None
    if args.contexto and (contexto is None or contexto.empty):
        print(f"AVISO: {args.contexto} no tiene contexto válido; la tabla osm_context irá vacía.")
    try:
        manifiesto = inputs_bundle.export_bundle(
            args.db, args.out, contexto, commit=git_commit(), sobrescribir=args.force
        )
    except (FileExistsError, ValueError) as e:
        print(f"Error: {e}")
        return 1
    out = Path(args.out)
    print(f"Paquete escrito en {out} ({out.stat().st_size / 1e6:.1f} MB)")
    for nombre in inputs_bundle.TABLAS:
        print(f"   {nombre:20} {manifiesto[f'tabla.{nombre}.filas']:>8} filas")
    print(f"   sha256 del archivo: {inputs_bundle.file_hash(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
