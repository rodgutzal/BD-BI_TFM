"""Paquete de entrada del ML (fase 1c): todo lo que necesitan las herramientas de entrenamiento, en UN archivo pequeño
y autocontenido, para entrenar en otra máquina sin copiar la base completa (`mobility.db` pesa ~400 MB, casi todo
mediciones de rutas que el ML no usa).

Formato: un archivo SQLite (sin dependencias nuevas) con las MISMAS tablas y columnas que lee `data_access`, así que
cualquier herramienta lo acepta en `--db` sin cambios:

  pois                category, subcategory, name, latitude, longitude
  pois_foursquare     category, subcategory, name, latitude, longitude   (vacía si no hay datos de Foursquare)
  zone_demographics   zone_name, population
  route_measurements  origin, destination, travel_time_min, n_mediciones  (YA agregada por par origen-destino)
  osm_context         category, subcategory, latitude, longitude          (contexto de la fase 1b, ya normalizado)
  manifest            clave, valor: formato, fecha, commit, versiones de las librerías, y por tabla filas y sha256

El manifiesto permite comprobar en la máquina de entrenamiento que el archivo llegó íntegro (`verify_bundle`) y dejar
constancia de con qué datos y versiones se produjo cada resultado (`provenance`).
"""

import hashlib
import platform
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

FORMATO = 1
TABLAS = ("pois", "pois_foursquare", "zone_demographics", "route_measurements", "osm_context")
COLUMNAS_CONTEXTO = ["category", "subcategory", "latitude", "longitude"]
_POIS = ["category", "subcategory", "name", "latitude", "longitude"]

_LECTURAS = {
    "pois": "SELECT category, subcategory, name, latitude, longitude FROM pois",
    "pois_foursquare": "SELECT category, subcategory, name, latitude, longitude FROM pois_foursquare",
    "zone_demographics": "SELECT zone_name, population FROM zone_demographics",
    "route_measurements": "SELECT origin, destination, AVG(travel_time_min) AS travel_time_min, COUNT(*) AS n_mediciones "
    "FROM route_measurements GROUP BY origin, destination",
}
_VACIAS = {
    "pois_foursquare": _POIS,
    "zone_demographics": ["zone_name", "population"],
    "route_measurements": ["origin", "destination", "travel_time_min", "n_mediciones"],
}


def _abrir(path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(path).as_posix()}?immutable=1", uri=True)


def _leer(path, sql: str) -> pd.DataFrame:
    conn = _abrir(path)
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()


def table_hash(df: pd.DataFrame) -> str:
    """sha256 del contenido de una tabla, independiente del orden de las filas y de la columna de índice."""
    if len(df.columns):
        df = df.sort_values(list(df.columns), kind="stable", na_position="last")
    csv = df.reset_index(drop=True).to_csv(index=False, float_format="%.10g", lineterminator="\n")
    return hashlib.sha256(csv.encode("utf-8")).hexdigest()


def file_hash(path) -> str:
    """sha256 del archivo completo (para comprobar que llegó íntegro tras copiarlo a otra máquina)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def library_versions() -> Dict[str, str]:
    """Versiones que influyen en los resultados numéricos del ML."""
    import numpy
    import scipy
    import sklearn

    return {
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": numpy.__version__,
        "scikit-learn": sklearn.__version__,
        "scipy": scipy.__version__,
    }


def export_bundle(
    db_path, out_path, contexto: Optional[pd.DataFrame] = None, commit: str = "", sobrescribir: bool = False
) -> Dict[str, str]:
    """Escribe el paquete en `out_path` leyendo `db_path` en solo lectura. `contexto` es el DataFrame del contexto de
    OSM (ver `osm_context.load_context`); si es None o está vacío, la tabla `osm_context` queda vacía.

    Se niega a pisar un archivo existente salvo `sobrescribir=True`, y nunca escribe sobre la base de origen.
    Devuelve el manifiesto."""
    out = Path(out_path)
    if out.exists() and not sobrescribir:
        raise FileExistsError(f"{out} ya existe (use sobrescribir=True para reemplazarlo)")
    if out.resolve() == Path(db_path).resolve():
        raise ValueError("el paquete no puede ser la propia base de origen")

    tablas: Dict[str, pd.DataFrame] = {}
    for nombre, sql in _LECTURAS.items():
        try:
            tablas[nombre] = _leer(db_path, sql)
        except Exception:
            if nombre not in _VACIAS:  # `pois` es obligatoria; las demás son opcionales
                raise
            tablas[nombre] = pd.DataFrame(columns=_VACIAS[nombre])  # tabla opcional ausente en la base de origen
    if tablas["pois"].empty:
        raise ValueError(f"{db_path} no tiene POIs: no hay nada que exportar")
    tablas["osm_context"] = (
        contexto[COLUMNAS_CONTEXTO].reset_index(drop=True)
        if contexto is not None and not contexto.empty
        else pd.DataFrame(columns=COLUMNAS_CONTEXTO)
    )

    if out.exists():
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(out)
    try:
        for nombre in TABLAS:
            tablas[nombre].to_sql(nombre, conn, index=False)
        conn.commit()
    finally:
        conn.close()

    manifiesto = {
        "formato": str(FORMATO),
        "creado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": commit or "desconocido",
        "origen": Path(db_path).name,
        "sistema": platform.system(),
    }
    manifiesto.update({f"version.{k}": v for k, v in library_versions().items()})
    for nombre in TABLAS:  # los hashes se calculan LEYENDO el paquete, igual que al verificar
        df = _leer(out, f"SELECT * FROM {nombre}")
        manifiesto[f"tabla.{nombre}.filas"] = str(len(df))
        manifiesto[f"tabla.{nombre}.sha256"] = table_hash(df)
    conn = sqlite3.connect(out)
    try:
        pd.DataFrame({"clave": list(manifiesto), "valor": list(manifiesto.values())}).to_sql(
            "manifest", conn, index=False
        )
        conn.commit()
    finally:
        conn.close()
    return manifiesto


def is_bundle(path) -> bool:
    """¿Es un paquete de entrada (tiene la tabla `manifest`) y no la base completa?"""
    try:
        return not _leer(path, "SELECT 1 FROM manifest LIMIT 1").empty
    except Exception:
        return False


def read_manifest(path) -> Dict[str, str]:
    df = _leer(path, "SELECT clave, valor FROM manifest")
    return dict(zip(df["clave"], df["valor"]))


def verify_bundle(path) -> List[str]:
    """Compara el contenido del paquete con su manifiesto. Devuelve la lista de problemas (vacía = íntegro)."""
    try:
        m = read_manifest(path)
    except Exception as e:
        return [f"no se pudo leer el manifiesto: {e}"]
    problemas = []
    if m.get("formato") != str(FORMATO):
        problemas.append(f"formato {m.get('formato')!r}, se esperaba {FORMATO}")
    for nombre in TABLAS:
        try:
            df = _leer(path, f"SELECT * FROM {nombre}")
        except Exception:
            problemas.append(f"falta la tabla {nombre}")
            continue
        if str(len(df)) != m.get(f"tabla.{nombre}.filas"):
            problemas.append(f"{nombre}: {len(df)} filas, el manifiesto dice {m.get(f'tabla.{nombre}.filas')}")
        elif table_hash(df) != m.get(f"tabla.{nombre}.sha256"):
            problemas.append(f"{nombre}: el contenido no coincide con el hash del manifiesto")
    return problemas


def load_context_table(path) -> pd.DataFrame:
    """Contexto de OSM guardado en el paquete; vacío si el archivo no tiene esa tabla (p. ej. la base completa)."""
    try:
        return _leer(path, "SELECT category, subcategory, latitude, longitude FROM osm_context")
    except Exception:
        return pd.DataFrame(columns=COLUMNAS_CONTEXTO)


def provenance(path, commit: str = "") -> Dict[str, str]:
    """Procedencia de un resultado: qué paquete (hash del archivo y de su manifiesto) y qué versiones lo produjeron.
    Es lo que cada tabla de salida de la máquina de entrenamiento guarda junto a sus números."""
    prov = {
        "entrada_sha256": file_hash(path),
        "commit": commit or "desconocido",
        "ejecutado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python_exe": Path(sys.executable).name,
    }
    prov.update({f"version.{k}": v for k, v in library_versions().items()})
    if is_bundle(path):
        m = read_manifest(path)
        prov["entrada_creada"] = m.get("creado", "")
        prov["entrada_commit"] = m.get("commit", "")
    return prov
