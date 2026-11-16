"""Dónde está cada celda en palabras: su calle con nombre y su localidad (de OpenStreetMap).

El panorama solo decía «zona más cercana»: una de las 7 zonas monitorizadas, a veces a casi 6 km, que no es un lugar
sino el punto de referencia más próximo. Y la localidad sola tampoco basta: dentro de una zona de 1.500 m casi todas
las celdas caen en el mismo pueblo, así que la columna repetía «Birkirkara» una fila tras otra. Por eso cada celda
recibe DOS rótulos:

  - `calle`: la vía con nombre más cercana al centro de la celda (≤ `CALLE_MAX_M`). Es lo que distingue una celda de
    su vecina y lo que una persona reconoce: «Triq il-Kbira».
  - `localidad`: el consejo local (relación `admin_level=8`) que contiene la celda, para situar la calle.

Es un dato PRECALCULADO (tools/build_cell_places.py hace DOS consultas a Overpass y escribe data/ml/cell_places.csv);
la pantalla no consulta la red.

Este módulo solo usa numpy y pandas. Si el archivo falta o no coincide con su manifiesto, `read_places` devuelve None y
la pantalla vuelve a rotular con la zona de referencia.

Archivos (`write_places`), en un directorio:
  cell_places.csv            cell_id, localidad, osm_relacion, criterio: «dentro» (el centro de la celda cae en la
                             localidad), «cercana» (centro en el mar pero el borde a ≤ 250 m) o vacío (ninguna);
                             calle y calle_m (distancia a ella; vacías si no hay ninguna con nombre cerca)
  cell_places_manifest.json  procedencia, atribución y sha256 del CSV
"""

import json
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.ml import grid
from src.ml.inputs_bundle import file_hash

NIVEL_LOCALIDAD = 8  # consejos locales de Malta en OpenStreetMap
CALLE_MAX_M = 150.0  # más lejos que esto, la calle ya no describe la celda (que mide 250 m de lado)
K_LAT_M = 111_320.0  # metros por grado de latitud; la longitud se corrige por el coseno de la latitud de referencia
FORMATO = 2
ARCHIVOS = {"places": "cell_places.csv", "manifest": "cell_places_manifest.json"}
COLUMNAS = ("cell_id", "localidad", "osm_relacion", "criterio", "calle", "calle_m")
ATRIBUCION = "© colaboradores de OpenStreetMap, ODbL (https://www.openstreetmap.org/copyright)"

Punto = Tuple[float, float]  # (lat, lon)


class Localidad:
    """Límite de una localidad: anillos exteriores y huecos como listas de (lat, lon) cerradas."""

    def __init__(
        self,
        osm_id: int,
        nombre: str,
        exteriores: List[List[Punto]],
        interiores: List[List[Punto]],
        tramos_descartados: int = 0,
    ):
        self.osm_id = int(osm_id)
        self.nombre = nombre
        self.exteriores = exteriores
        self.interiores = interiores
        self.tramos_descartados = tramos_descartados  # >0: el límite está incompleto (tramos que no cerraron)

    def __repr__(self) -> str:
        return f"Localidad({self.osm_id}, {self.nombre!r}, {len(self.exteriores)} ext, {len(self.interiores)} int)"


# ---------------------------------------------------------------------------
# Geometría
# ---------------------------------------------------------------------------
def _cerrar_anillos(segmentos: Sequence[Sequence[Punto]]) -> Tuple[List[List[Punto]], int]:
    """Une tramos (las `way` de una relación) en anillos cerrados. Devuelve (anillos, cuántos conjuntos de tramos no se
    pudieron cerrar y se descartaron)."""
    pendientes = [list(s) for s in segmentos if len(s) >= 2]
    anillos: List[List[Punto]] = []
    descartados = 0
    while pendientes:
        actual = pendientes.pop()
        while actual[0] != actual[-1]:
            for i, s in enumerate(pendientes):
                if s[0] == actual[-1]:
                    actual = actual + s[1:]
                elif s[-1] == actual[-1]:
                    actual = actual + s[::-1][1:]
                elif s[-1] == actual[0]:
                    actual = s[:-1] + actual
                elif s[0] == actual[0]:
                    actual = s[::-1][:-1] + actual
                else:
                    continue
                pendientes.pop(i)
                break
            else:
                break  # ningún tramo continúa este: no se cierra
        if len(actual) >= 4 and actual[0] == actual[-1]:
            anillos.append(actual)
        else:
            descartados += 1
    return anillos, descartados


def nombre_de(etiquetas: Dict[str, str]) -> str:
    """Nombre en inglés si existe (Marsaskala, no «Wied il-Għajn»), si no el nombre local."""
    return (etiquetas.get("name:en") or etiquetas.get("name") or "").strip()


def parse_boundaries(elementos: Sequence[dict], nivel: int = NIVEL_LOCALIDAD) -> List[Localidad]:
    """Localidades de una respuesta de Overpass (`out geom` de relaciones administrativas). Ignora las de otro nivel,
    las sin nombre y los miembros sin geometría."""
    salida: List[Localidad] = []
    for el in elementos:
        etiquetas = el.get("tags", {})
        if el.get("type") != "relation" or str(etiquetas.get("admin_level")) != str(nivel):
            continue
        nombre = nombre_de(etiquetas)
        if not nombre:
            continue
        tramos = {"outer": [], "inner": []}
        ignoradas = 0
        for m in el.get("members", []):
            geom = m.get("geometry")
            if m.get("type") != "way" or not geom:
                continue
            # En un límite de OSM, una `way` sin rol delimita por fuera: es el caso corriente, no un error. Cualquier
            # otro rol (p. ej. `label`) no delimita, y se cuenta para poder avisar de que el límite va incompleto.
            rol = m.get("role") or "outer"
            if rol in tramos:
                tramos[rol].append([(float(p["lat"]), float(p["lon"])) for p in geom])
            else:
                ignoradas += 1
        (exteriores, sobran_ext), (interiores, sobran_int) = _cerrar_anillos(tramos["outer"]), _cerrar_anillos(
            tramos["inner"]
        )
        descartados = sobran_ext + sobran_int + ignoradas
        if exteriores or descartados:  # sin ningún anillo cerrado se conserva, vacía y marcada, para que se avise
            salida.append(Localidad(el["id"], nombre, exteriores, interiores, descartados))
    return salida


def _dentro_de_anillo(lat: np.ndarray, lon: np.ndarray, anillo: Sequence[Punto]) -> np.ndarray:
    """Punto en polígono por conteo de cruces de un rayo hacia el este (lon crece)."""
    a = np.asarray(anillo, dtype=float)
    y1, x1, y2, x2 = a[:-1, 0], a[:-1, 1], a[1:, 0], a[1:, 1]
    dentro = np.zeros(len(lat), dtype=bool)
    for j in range(len(y1)):
        if y1[j] == y2[j]:
            continue
        cruza = (y1[j] > lat) != (y2[j] > lat)
        x_corte = x1[j] + (lat - y1[j]) * (x2[j] - x1[j]) / (y2[j] - y1[j])
        dentro ^= cruza & (lon < x_corte)
    return dentro


def contained_mask(lat: np.ndarray, lon: np.ndarray, loc: Localidad) -> np.ndarray:
    """¿Cada punto está dentro de la localidad (algún anillo exterior y ningún hueco)?"""
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    dentro = np.zeros(len(lat), dtype=bool)
    for anillo in loc.exteriores:
        en_anillo = _dentro_de_anillo(lat, lon, anillo)
        # Cada hueco solo resta del anillo exterior que lo contiene (el de su primer vértice): restarlo de la unión de todos
        # borraría una isla o un exclave de la misma relación que quede dentro del hueco.
        for hueco in loc.interiores:
            if _dentro_de_anillo(np.array([hueco[0][0]]), np.array([hueco[0][1]]), anillo)[0]:
                en_anillo &= ~_dentro_de_anillo(lat, lon, hueco)
        dentro |= en_anillo
    return dentro


class Calles:
    """Las vías con nombre, ya proyectadas a metros y partidas en segmentos rectos.

    `segmentos` es (M, 4) con [y1, x1, y2, x2] en metros, `de_nombre` (M,) dice a qué nombre pertenece cada segmento y
    `nombres` es la lista de nombres. Proyección plana local: a estas distancias (cientos de metros) sobra."""

    def __init__(self, nombres: List[str], segmentos: np.ndarray, de_nombre: np.ndarray, ref_lat: float):
        self.nombres = nombres
        self.segmentos = segmentos
        self.de_nombre = de_nombre
        self.ref_lat = ref_lat

    def __len__(self) -> int:
        return len(self.nombres)

    def __repr__(self) -> str:
        return f"Calles({len(self.nombres)} nombres, {len(self.segmentos)} segmentos)"

    def proyectar(self, lat, lon) -> Tuple[np.ndarray, np.ndarray]:
        k_lon = K_LAT_M * math.cos(math.radians(self.ref_lat))
        return np.asarray(lat, dtype=float) * K_LAT_M, np.asarray(lon, dtype=float) * k_lon


def nombre_util(nombre: str) -> bool:
    """¿Sirve como rótulo? Descarta los nombres que no dicen un lugar: marcas de obra o de eje como «4», «A-A», «B-B»."""
    return len(nombre) >= 3 and len(re.findall(r"[^\W\d_]", nombre, flags=re.UNICODE)) >= 3


def parse_streets(elementos: Sequence[dict], ref_lat: Optional[float] = None) -> Calles:
    """Vías con nombre de una respuesta de Overpass (`out geom` de ways con `highway` y `name`).

    Ignora lo que no sea una `way` con geometría y nombre útil (ver `nombre_util`). Varias vías con el mismo nombre
    (una calle suele venir partida en tramos) comparten un único nombre."""
    if ref_lat is None:
        ref_lat = (grid.SOUTH + grid.NORTH) / 2
    k_lon = K_LAT_M * math.cos(math.radians(ref_lat))
    indices: Dict[str, int] = {}
    nombres: List[str] = []
    trozos, de_nombre = [], []
    for el in elementos:
        if el.get("type") != "way":
            continue
        nombre = nombre_de(el.get("tags", {}))
        geom = el.get("geometry")
        if not nombre or not nombre_util(nombre) or not geom or len(geom) < 2:
            continue
        if nombre not in indices:
            indices[nombre] = len(nombres)
            nombres.append(nombre)
        p = np.array([(float(g["lat"]) * K_LAT_M, float(g["lon"]) * k_lon) for g in geom], dtype=float)
        trozos.append(np.concatenate([p[:-1], p[1:]], axis=1))
        de_nombre.append(np.full(len(p) - 1, indices[nombre], dtype=int))
    segmentos = np.concatenate(trozos) if trozos else np.zeros((0, 4))
    return Calles(nombres, segmentos, np.concatenate(de_nombre) if de_nombre else np.zeros(0, dtype=int), ref_lat)


def nearest_street(lat, lon, calles: Calles, max_m: float = CALLE_MAX_M, trozo: int = 64) -> pd.DataFrame:
    """Calle con nombre más cercana a cada punto: columnas `calle` y `calle_m` (vacía y NaN si ninguna a `max_m` o menos).

    Fuerza bruta por trozos de `trozo` puntos: son ~1.100 celdas contra ~40.000 segmentos, una vez, al precalcular."""
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    nombre = np.full(len(lat), "", dtype=object)
    distancia = np.full(len(lat), np.nan)
    if not len(calles.segmentos) or not len(lat):
        return pd.DataFrame({"calle": nombre, "calle_m": distancia})
    ay, ax, by, bx = calles.segmentos.T
    dy, dx = by - ay, bx - ax
    largo2 = np.where(dx * dx + dy * dy == 0, 1.0, dx * dx + dy * dy)
    py, px = calles.proyectar(lat, lon)
    for i in range(0, len(lat), trozo):
        qy, qx = py[i : i + trozo, None], px[i : i + trozo, None]
        t = np.clip(((qx - ax) * dx + (qy - ay) * dy) / largo2, 0.0, 1.0)
        d = np.hypot(qx - (ax + t * dx), qy - (ay + t * dy))
        mejor = np.argmin(d, axis=1)
        d_mejor = d[np.arange(len(mejor)), mejor]
        cerca = d_mejor <= max_m
        tramo = slice(i, i + len(mejor))
        nombre[tramo] = np.where(cerca, [calles.nombres[j] for j in calles.de_nombre[mejor]], "")
        distancia[tramo] = np.where(cerca, d_mejor, np.nan)
    return pd.DataFrame({"calle": nombre, "calle_m": distancia})


def distance_to_boundary_m(lat: np.ndarray, lon: np.ndarray, loc: Localidad) -> np.ndarray:
    """Distancia (m) de cada punto al borde de la localidad (al segmento más cercano de cualquiera de sus anillos),
    con una proyección plana local: sobra para distancias de unos cientos de metros."""
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    k_lat = 111_320.0
    k_lon = k_lat * np.cos(np.radians(lat.mean() if len(lat) else 0.0))
    mejor = np.full(len(lat), np.inf)
    for anillo in list(loc.exteriores) + list(loc.interiores):
        a = np.asarray(anillo, dtype=float)
        ay, ax, by, bx = a[:-1, 0] * k_lat, a[:-1, 1] * k_lon, a[1:, 0] * k_lat, a[1:, 1] * k_lon
        dy, dx = by - ay, bx - ax
        largo2 = np.where(dx * dx + dy * dy == 0, 1.0, dx * dx + dy * dy)
        py, px = (lat * k_lat)[:, None], (lon * k_lon)[:, None]
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / largo2, 0.0, 1.0)
        d = np.hypot(px - (ax + t * dx), py - (ay + t * dy))
        mejor = np.minimum(mejor, d.min(axis=1))
    return mejor


def assign_places(lat, lon, localidades: Sequence[Localidad], tolerancia_m: float = 250.0) -> pd.DataFrame:
    """Localidad de cada punto: columnas `localidad`, `osm_relacion` y `criterio`.

    `criterio` es «dentro» si el punto cae en el polígono de la localidad. Los límites de los consejos locales siguen la
    costa, así que el CENTRO de una celda costera puede caer en el mar aunque la celda tenga tierra: si no está dentro de
    ninguna, se asigna la localidad cuyo borde esté a `tolerancia_m` o menos (por defecto, el lado de la celda) y el
    criterio es «cercana». Más lejos queda vacío (mar o fuera de los límites). Si un punto cae en más de una localidad
    (solapes en el borde), gana la de menor id, para que sea determinista."""
    lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float)
    ordenadas = sorted(localidades, key=lambda l: l.osm_id)
    nombre = np.full(len(lat), "", dtype=object)
    rel = np.full(len(lat), "", dtype=object)
    criterio = np.full(len(lat), "", dtype=object)
    libre = np.ones(len(lat), dtype=bool)
    for loc in ordenadas:
        dentro = contained_mask(lat, lon, loc) & libre
        nombre[dentro], rel[dentro], criterio[dentro] = loc.nombre, str(loc.osm_id), "dentro"
        libre &= ~dentro
    if libre.any():
        idx = np.nonzero(libre)[0]
        mejor_d = np.full(len(idx), np.inf)
        for loc in ordenadas:
            d = distance_to_boundary_m(lat[idx], lon[idx], loc)
            mejor = d < mejor_d
            mejor_d = np.where(mejor, d, mejor_d)
            nombre[idx[mejor]], rel[idx[mejor]] = loc.nombre, str(loc.osm_id)
        cerca = mejor_d <= tolerancia_m
        criterio[idx[cerca]] = "cercana"
        nombre[idx[~cerca]], rel[idx[~cerca]] = "", ""
    return pd.DataFrame({"localidad": nombre, "osm_relacion": rel, "criterio": criterio})


# ---------------------------------------------------------------------------
# Archivos
# ---------------------------------------------------------------------------
def write_places(out_dir, tabla: pd.DataFrame, procedencia: Dict) -> Dict:
    """Escribe cell_places.csv (cell_id, localidad, osm_relacion, criterio, calle, calle_m) y su manifiesto; devuelve el
    manifiesto."""
    directorio = Path(out_dir)
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / ARCHIVOS["places"]
    tabla = tabla[list(COLUMNAS)].sort_values("cell_id")
    tabla.to_csv(ruta, index=False, lineterminator="\n", encoding="utf-8", float_format="%.1f")
    completo = dict(procedencia)
    completo.update(
        {
            "formato": FORMATO,
            "atribucion": ATRIBUCION,
            "filas": int(len(tabla)),
            "sin_localidad": int((tabla["localidad"] == "").sum()),
            "por_cercania": int((tabla["criterio"] == "cercana").sum()),
            "sin_calle": int((tabla["calle"] == "").sum()),
            "calle_max_m": CALLE_MAX_M,
            "sha256": file_hash(ruta),
        }
    )
    (directorio / ARCHIVOS["manifest"]).write_text(
        json.dumps(completo, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return completo


def verify_places(out_dir) -> List[str]:
    """Problemas de cell_places.csv respecto a su manifiesto (lista vacía = íntegro)."""
    directorio = Path(out_dir)
    try:
        manifiesto = json.loads((directorio / ARCHIVOS["manifest"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"no se pudo leer el manifiesto de localidades: {e}"]
    ruta = directorio / ARCHIVOS["places"]
    if manifiesto.get("formato") != FORMATO:
        return [f"formato {manifiesto.get('formato')!r}, se esperaba {FORMATO}"]
    if not ruta.exists():
        return [f"falta {ARCHIVOS['places']}"]
    if file_hash(ruta) != manifiesto.get("sha256"):
        return [f"{ARCHIVOS['places']}: el contenido no coincide con el hash del manifiesto"]
    return []


def read_places(out_dir) -> Optional[pd.DataFrame]:
    """Tabla indexada por cell_id con `localidad` y `calle` (cadena vacía si no se conocen), o None si el archivo falta
    o no coincide con su manifiesto. Sin ella la pantalla sigue funcionando con la zona de referencia."""
    if verify_places(out_dir):
        return None
    tabla = pd.read_csv(Path(out_dir) / ARCHIVOS["places"], dtype=str, keep_default_na=False, na_values=[]).set_index(
        "cell_id"
    )
    return tabla[["localidad", "calle"]]
