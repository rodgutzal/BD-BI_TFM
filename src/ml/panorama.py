"""Panorama por celda (fase 2a): las tres lentes de cada celda activa para cada perfil, con percentiles legibles, una
confianza de datos y, solo para `food_drink` y `business`, la brecha de oferta como indicador EXPLORATORIO.

Este módulo solo usa numpy y pandas (no scikit-learn): el dashboard puede importarlo para recalcular las lentes cuando
el usuario ajusta su perfil. Lo que necesita un modelo aprendido (la brecha) se calcula aparte, en la máquina de
entrenamiento (tools/build_panorama.py), y llega aquí como una tabla ya hecha.

Tres reglas que el panorama respeta:
  - Las lentes son indicadores EXPLÍCITOS (conteos) y se muestran por separado; no hay un puntaje combinado.
  - La brecha NO está validada (fase 1: ningún candidato superó con claridad a la densidad de POIs). Viaja en columnas
    propias, con `brecha_validada` en False, y no entra en ninguna otra columna.
  - La confianza no es una probabilidad: resume cuántas lentes tienen datos y cuántos POIs sustentan cada una.

Archivos de salida (`write_outputs`), en un directorio:
  panorama.csv            una fila por (perfil, celda activa)
  cell_counts.csv         tabla celda × (categoría|subcategoría) de toda celda con algún conteo: base para recalcular
                          las lentes con otro perfil (con ella, las lentes salen idénticas a las del panorama)
  panorama_manifest.json  procedencia, parámetros, decisión de la validación y sha256 de los dos CSV
"""

import json
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from src.locations import LOCATIONS
from src.ml import grid
from src.ml.business_profiles import BusinessProfile
from src.ml.cell_counts import CellCounts
from src.ml.inputs_bundle import file_hash
from src.ml.lenses import compute_lenses
from src.ml.osm_context import CONTEXTO

APOYO_SUFICIENTE = 5  # POIs en la celda y sus 8 vecinas a partir de los cuales una lente se considera bien apoyada
NIVELES_CONFIANZA = ((2 / 3, "alta"), (1 / 3, "media"), (0.0, "baja"))
PERCENTILES = ("competencia_directa", "mercado_total", "proveedores_total", "proveedores_diversidad")
COLUMNAS_BRECHA = ("esperado", "brecha_relativa", "brecha_p10", "brecha_p90")
FORMATO = 1
ARCHIVOS = {"panorama": "panorama.csv", "cell_counts": "cell_counts.csv", "manifest": "panorama_manifest.json"}


def percentile_rank(serie: pd.Series) -> pd.Series:
    """Posición de cada celda entre las de su serie, de 0 (la más baja) a 1 (la más alta). Los NaN siguen siendo NaN
    (sin datos no es lo mismo que posición baja). Los empates reciben el rango medio."""
    return serie.rank(pct=True, method="average")


def confidence(lentes: pd.DataFrame, pois_vecindad) -> pd.DataFrame:
    """Confianza de datos de cada celda: media de las tres lentes de min(apoyo / APOYO_SUFICIENTE, 1), contando 0 para
    una lente sin datos. Devuelve `confianza` (0-1) y `confianza_nivel` (alta, media o baja).

    El apoyo de la COMPETENCIA no es el número de competidores sino `pois_vecindad` (POIs de cualquier categoría en la
    celda y sus 8 vecinas): «cero competidores» es una observación creíble donde hay mucho mapeado y poco creíble donde
    casi no hay nada. Si se usara el número de competidores, las celdas sin competencia —justo las que interesan— saldrían
    siempre con confianza baja. Mercado y proveedores sí usan su propio apoyo: sin generadores de consumidores ni
    proveedores cerca, no hay evidencia de que haya mercado o proveedores."""
    apoyos = {
        "competencia": np.asarray(pois_vecindad, dtype=float),
        "mercado": lentes["apoyo_mercado"].to_numpy(dtype=float),
        "proveedores": lentes["apoyo_proveedores"].to_numpy(dtype=float),
    }
    soportes = []
    for lente in ("competencia", "mercado", "proveedores"):
        apoyo = np.minimum(apoyos[lente] / APOYO_SUFICIENTE, 1.0)
        soportes.append(np.where(lentes[f"datos_{lente}"].to_numpy(dtype=bool), apoyo, 0.0))
    valor = np.mean(soportes, axis=0)
    nivel = np.full(len(valor), NIVELES_CONFIANZA[-1][1], dtype=object)
    for umbral, nombre in reversed(NIVELES_CONFIANZA[:-1]):
        nivel = np.where(valor >= umbral - 1e-12, nombre, nivel)
    return pd.DataFrame({"confianza": valor, "confianza_nivel": nivel}, index=lentes.index)


def locate(index: pd.Index) -> pd.DataFrame:
    """Fila, columna, coordenadas del centro, zona más cercana y distancia a ella (m) de cada celda."""
    posiciones = [grid.parse_cell_id(i) for i in index]
    filas = np.array([p[0] for p in posiciones], dtype=int)
    cols = np.array([p[1] for p in posiciones], dtype=int)
    lat, lon = grid.cell_center(filas, cols)
    nombres = list(LOCATIONS)
    distancias = np.stack([grid.haversine_m(LOCATIONS[z].latitude, LOCATIONS[z].longitude, lat, lon) for z in nombres])
    cercana = np.argmin(distancias, axis=0)
    return pd.DataFrame(
        {
            "fila": filas,
            "col": cols,
            "lat": lat,
            "lon": lon,
            "zona_cercana": [nombres[i] for i in cercana],
            "dist_zona_m": distancias[cercana, np.arange(len(index))],
        },
        index=index,
    )


def build_panorama(
    counts: CellCounts,
    profile: BusinessProfile,
    brecha: Optional[pd.DataFrame] = None,
    modelo_brecha: str = "",
    brecha_validada: bool = False,
    mask: Optional[np.ndarray] = None,
) -> pd.DataFrame:
    """Panorama de las celdas activas (o de `mask`) para un perfil. Indexado por cell_id.

    `brecha`: tabla indexada por cell_id con `COLUMNAS_BRECHA` (ver validation.gap_from_evaluation), o None. Sin ella
    las columnas de brecha quedan en NaN. Las celdas de `brecha` que no estén en el panorama se ignoran."""
    lentes = compute_lenses(counts, profile, mask)
    out = pd.concat([locate(lentes.index), lentes], axis=1)
    for col in PERCENTILES:
        if col in out:
            out[f"pct_{col}"] = percentile_rank(out[col])
    pois = CellCounts({k: v for k, v in counts.arrays.items() if k[0] not in CONTEXTO}).total_grid()
    filas, cols = out["fila"].to_numpy(), out["col"].to_numpy()
    out["pois_vecindad"] = (grid.ring_sum(pois, 0) + grid.ring_sum(pois, 1))[filas, cols]
    out = pd.concat([out, confidence(lentes, out["pois_vecindad"])], axis=1)
    for col in COLUMNAS_BRECHA:
        out[col] = brecha[col].reindex(out.index) if brecha is not None else np.nan
    out["modelo_brecha"] = modelo_brecha if brecha is not None else ""
    out["brecha_validada"] = bool(brecha_validada) if brecha is not None else False
    out.insert(0, "perfil", profile.key)
    return out


# ---------------------------------------------------------------------------
# Archivos de salida
# ---------------------------------------------------------------------------
def _escribir_csv(df: pd.DataFrame, ruta: Path, indice: bool) -> None:
    df.to_csv(ruta, index=indice, float_format="%.6g", lineterminator="\n", encoding="utf-8")


def write_outputs(out_dir, panorama: pd.DataFrame, counts: CellCounts, manifiesto: Dict) -> Dict:
    """Escribe los dos CSV y el manifiesto en `out_dir` y devuelve el manifiesto completo (con filas y sha256 de cada
    CSV). `manifiesto` aporta la procedencia y los parámetros; este módulo añade lo que depende de los archivos."""
    directorio = Path(out_dir)
    directorio.mkdir(parents=True, exist_ok=True)
    ruta_p, ruta_c = directorio / ARCHIVOS["panorama"], directorio / ARCHIVOS["cell_counts"]
    _escribir_csv(panorama.reset_index(), ruta_p, False)
    # TODAS las celdas con algún conteo, no solo las activas: las celdas activas se definen solo con POIs de Overpass, pero
    # el contexto de OSM (edificios, alojamiento...) de celdas inactivas vecinas también suma en las lentes de las
    # activas. Con solo las activas, recalcular desde esta tabla daría otros números que el panorama.
    cuentas = counts.to_frame(counts.total_grid() > 0)
    _escribir_csv(cuentas, ruta_c, True)
    completo = dict(manifiesto)
    completo["formato"] = FORMATO
    completo["archivos"] = {
        ARCHIVOS["panorama"]: {"filas": int(len(panorama)), "sha256": file_hash(ruta_p)},
        ARCHIVOS["cell_counts"]: {"filas": int(len(cuentas)), "sha256": file_hash(ruta_c)},
    }
    (directorio / ARCHIVOS["manifest"]).write_text(
        json.dumps(completo, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return completo


def verify_outputs(out_dir) -> list:
    """Comprueba que los CSV de `out_dir` coinciden con su manifiesto. Devuelve la lista de problemas (vacía = íntegro)."""
    directorio = Path(out_dir)
    try:
        manifiesto = json.loads((directorio / ARCHIVOS["manifest"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"no se pudo leer el manifiesto: {e}"]
    problemas = []
    if manifiesto.get("formato") != FORMATO:
        problemas.append(f"formato {manifiesto.get('formato')!r}, se esperaba {FORMATO}")
    for nombre in (ARCHIVOS["panorama"], ARCHIVOS["cell_counts"]):
        ruta = directorio / nombre
        esperado = manifiesto.get("archivos", {}).get(nombre)
        if not ruta.exists():
            problemas.append(f"falta {nombre}")
        elif esperado is None:
            problemas.append(f"{nombre} no está en el manifiesto")
        elif file_hash(ruta) != esperado.get("sha256"):
            problemas.append(f"{nombre}: el contenido no coincide con el hash del manifiesto")
    return problemas


def read_panorama(out_dir, verificar: bool = True) -> pd.DataFrame:
    """Lee panorama.csv (con comprobación de integridad por defecto; lanza ValueError si no coincide)."""
    if verificar:
        problemas = verify_outputs(out_dir)
        if problemas:
            raise ValueError("; ".join(problemas))
    return pd.read_csv(
        Path(out_dir) / ARCHIVOS["panorama"], keep_default_na=True, na_values=[""], dtype={"modelo_brecha": str}
    ).fillna({"modelo_brecha": ""})


def read_counts(out_dir, verificar: bool = True) -> CellCounts:
    """Lee cell_counts.csv y reconstruye los conteos (ver CellCounts.from_frame)."""
    if verificar:
        problemas = verify_outputs(out_dir)
        if problemas:
            raise ValueError("; ".join(problemas))
    return CellCounts.from_frame(pd.read_csv(Path(out_dir) / ARCHIVOS["cell_counts"], index_col="cell_id"))
