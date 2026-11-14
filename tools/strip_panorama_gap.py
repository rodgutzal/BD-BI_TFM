"""
Quita la BRECHA DE OFERTA de un panorama ya publicado (`data/ml/`), dejando las lentes exactamente como están.

Por qué: las columnas de brecha (`esperado`, `brecha_relativa`, `brecha_p10`, `brecha_p90`) salen de un modelo que usa como
variables la población por zona (Google Data Commons) y el tiempo de viaje medio de las rutas, calculado sobre mediciones que
incluyen las de TomTom (cuyas condiciones prohíben las bases de datos derivadas). Esa brecha, además, no está validada (ningún
candidato superó a la densidad) y no entra en ningún puntaje. Ver docs/DATOS_Y_LICENCIAS.md.

Por qué NO se regenera con `tools/build_panorama.py --sin-brecha`: eso recalcularía las lentes desde los datos de hoy y, sin el
contexto de OpenStreetMap (edificios, alojamiento, paradas) que no está disponible, cambiaría las lentes de mercado, que no
tienen nada que ver con la brecha. Aquí se DERIVA del propio `panorama.csv` verificado:
  - `esperado`, `brecha_relativa`, `brecha_p10` y `brecha_p90` quedan vacías, `modelo_brecha` vacío y `brecha_validada` en
    False (la misma representación que da `build_panorama --sin-brecha`);
  - el resto de columnas, el orden y el número de filas no cambian;
  - `cell_counts.csv` NO se toca (conteos de OpenStreetMap);
  - el manifiesto se actualiza (hash del panorama, `con_brecha: false`, sin sección de brecha) y conserva la procedencia
    original, con una sección `derivado` que dice qué se hizo y el hash anterior.

Se niega si el directorio no verifica contra su manifiesto. Es idempotente: sobre un panorama que ya no tiene brecha no hace nada.
Cada archivo se escribe de forma atómica (temporal + reemplazo) y el hash original se conserva en `derivado` aunque se repita.
Límite: son dos archivos; si el proceso se corta justo entre ambos, el directorio deja de verificar y la herramienta se niega a
tocarlo: se recupera con `git checkout -- data/ml` y se repite.

Uso (desde la raíz del proyecto):
    python tools/strip_panorama_gap.py
    python tools/strip_panorama_gap.py --dir data/ml
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import panorama  # noqa: E402

DEFAULT_DIR = ROOT / "data" / "ml"
ADVERTENCIA_SIN_BRECHA = "Sin brecha: solo lentes explícitas."
MOTIVO = (
    "La brecha de oferta dependía de la población de Data Commons y del tiempo de viaje medio, calculado con mediciones de "
    "TomTom (cuyas condiciones prohíben las bases de datos derivadas), y no estaba validada: se retiró del panorama publicado. "
    "Las lentes y cell_counts.csv no cambian."
)


def tiene_brecha(tabla) -> bool:
    return bool(tabla[list(panorama.COLUMNAS_BRECHA)].notna().any().any() or tabla["modelo_brecha"].ne("").any())


def _reemplazar_atomico(ruta: Path, escribir) -> None:
    """Escribe en un temporal y lo reemplaza sobre `ruta`; si algo falla, el temporal no se queda."""
    temporal = ruta.with_name(ruta.name + ".tmp")
    try:
        escribir(temporal)
        os.replace(temporal, ruta)
    finally:
        temporal.unlink(missing_ok=True)


def quitar_brecha(directorio) -> dict:
    """Quita la brecha de `directorio`. Devuelve `{"cambiado": bool, "filas": n, "sha256_anterior": ..., "sha256": ...}`."""
    d = Path(directorio)
    problemas = panorama.verify_outputs(d)
    if problemas:
        raise ValueError("El panorama no coincide con su manifiesto, no se toca: " + "; ".join(problemas))
    ruta_p = d / panorama.ARCHIVOS["panorama"]
    ruta_m = d / panorama.ARCHIVOS["manifest"]
    manifiesto = json.loads(ruta_m.read_text(encoding="utf-8"))
    tabla = panorama.read_panorama(d)
    anterior = manifiesto["archivos"][panorama.ARCHIVOS["panorama"]]["sha256"]
    if (
        not tiene_brecha(tabla)
        and not manifiesto.get("brecha")
        and manifiesto.get("parametros", {}).get("con_brecha") is False
    ):
        return {"cambiado": False, "filas": int(len(tabla)), "sha256_anterior": anterior, "sha256": anterior}
    for col in panorama.COLUMNAS_BRECHA:
        tabla[col] = np.nan
    tabla["modelo_brecha"] = ""
    tabla["brecha_validada"] = False
    _reemplazar_atomico(ruta_p, lambda temporal: panorama._escribir_csv(tabla, temporal, False))
    nuevo = panorama.file_hash(ruta_p)
    manifiesto["archivos"][panorama.ARCHIVOS["panorama"]] = {"filas": int(len(tabla)), "sha256": nuevo}
    manifiesto["parametros"] = {**manifiesto.get("parametros", {}), "con_brecha": False}
    manifiesto["brecha"] = {}
    manifiesto["advertencia"] = ADVERTENCIA_SIN_BRECHA
    manifiesto["derivado"] = {
        "herramienta": "tools/strip_panorama_gap.py",
        # el hash del panorama ORIGINAL (con brecha), también si se repara un estado a medias
        "panorama_sha256_anterior": manifiesto.get("derivado", {}).get("panorama_sha256_anterior", anterior),
        "motivo": MOTIVO,
    }
    texto = json.dumps(manifiesto, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    _reemplazar_atomico(ruta_m, lambda temporal: temporal.write_text(texto, encoding="utf-8", newline="\n"))
    return {"cambiado": True, "filas": int(len(tabla)), "sha256_anterior": anterior, "sha256": nuevo}


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", default=str(DEFAULT_DIR), help=f"directorio del panorama (default: {DEFAULT_DIR})")
    args = ap.parse_args(argv)
    try:
        r = quitar_brecha(args.dir)
    except (ValueError, OSError, KeyError) as e:
        print(f"ERROR: {e}")
        return 1
    if not r["cambiado"]:
        print("El panorama ya no tiene brecha: no se hizo nada.")
        return 0
    print(
        f"Brecha retirada de {args.dir}: {r['filas']} filas; panorama.csv {r['sha256_anterior'][:12]}… -> {r['sha256'][:12]}…"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
