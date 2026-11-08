"""Las tres lentes de cada celda: competencia, mercado consumidor y proveedores.

Cada lente es una suma ponderada por vecindad (celda 1,0 + anillo 1 × 0,5 + anillo 2 × 0,25; ver grid.RING_WEIGHTS)
de los POIs que el perfil de negocio asigna a esa lente. Son indicadores EXPLÍCITOS (conteos), no predicciones: con
los datos que hay (sin etiquetas de éxito) el modelo no puede aprender cuánto vale un buen mercado o un proveedor
cercano; por eso se muestran por separado y los pesos del puntaje son visibles y ajustables.

PRECEDENCIA (un POI cuenta en una sola lente): competencia > mercado y proveedores. Un museo es competencia directa de
un negocio de ocio; contarlo además como 'generador de turistas' lo contaría dos veces, inflaría la correlación entre
lentes y haría que casi ninguna celda pareciera 'buen mercado con poca competencia' (medido: 0 % en ocio). Por la
misma razón, un comercio que compite contigo no se cuenta como tu proveedor.

Cada lente declara también su APOYO (cuántos POIs hay en la vecindad) y si tiene DATOS suficientes, que alimentan
la 'confianza de datos' del panorama: una celda con poca información no se presenta con la misma seguridad.
"""

from typing import Dict, Optional

import numpy as np
import pandas as pd

from src.ml import grid
from src.ml.business_profiles import BusinessProfile, segment_selectors, supplier_selectors
from src.ml.cell_counts import CellCounts

LENTES = ("competencia", "mercado", "proveedores")


def _vecindad(matriz: np.ndarray) -> np.ndarray:
    return grid.neighborhood_sum(matriz, grid.RING_WEIGHTS)


def compute_lenses(counts: CellCounts, profile: BusinessProfile, mask: Optional[np.ndarray] = None) -> pd.DataFrame:
    """Indicadores de las tres lentes para las celdas de `mask` (por defecto, las activas: con algún POI en la
    celda o su vecindad inmediata). Una fila por celda, indexada por cell_id.

    Columnas:
      competencia_directa, competencia_indirecta                  conteos ponderados
      mercado_<segmento> (conteo ponderado; NaN si el segmento no tiene POIs que lo midan),
      mercado_total (ÍNDICE 0-1: media de los segmentos con datos, cada uno escalado por su máximo en la rejilla)
      proveedores_<tipo> (NaN si no hay datos), proveedores_total, proveedores_diversidad (fracción de tipos presentes)
      apoyo_competencia, apoyo_mercado, apoyo_proveedores          POIs (sin ponderar) en la celda y sus 8 vecinas
      datos_competencia / datos_mercado / datos_proveedores        True si la lente se puede calcular
      lentes_con_datos                                             0-3
    """
    if mask is None:
        mask = counts.active_mask()
    filas, cols = np.nonzero(mask)
    ids = [grid.cell_id(f, c) for f, c in zip(filas, cols)]
    columnas: Dict[str, np.ndarray] = {}
    competidores = tuple(profile.competencia_directa) + tuple(profile.competencia_indirecta)   # precedencia, ver abajo

    def tomar(matriz):
        return matriz[filas, cols]

    def apoyo(selectors, exclude=()):
        matriz = counts.grid(selectors, exclude)
        return tomar(grid.ring_sum(matriz, 0) + grid.ring_sum(matriz, 1))

    # --- competencia ---
    columnas["competencia_directa"] = tomar(_vecindad(counts.grid(profile.competencia_directa)))
    columnas["competencia_indirecta"] = tomar(_vecindad(counts.grid(profile.competencia_indirecta)))
    todos_comp = tuple(profile.competencia_directa) + tuple(profile.competencia_indirecta)
    columnas["apoyo_competencia"] = apoyo(todos_comp)
    datos_comp = np.full(len(ids), len(todos_comp) > 0)

    # --- mercado ---
    # `mercado_total` es un ÍNDICE 0-1: la media de los segmentos con datos, cada uno escalado por su máximo en TODA la
    # rejilla. Sumar los conteos en bruto no sirve: con el contexto de la fase 1b los edificios (~90 por celda) aplastarían
    # a colegios u oficinas (~1) solo por la unidad de medida. Las columnas `mercado_<segmento>` siguen siendo conteos.
    suma_escalada = np.zeros(len(ids))
    selectores_mercado = []
    segmentos_con_datos = 0
    for segmento, sels in segment_selectors(profile).items():
        if sels and counts.count_in_area(sels, competidores) > 0:
            matriz = _vecindad(counts.grid(sels, competidores))
            valores = tomar(matriz)
            suma_escalada = suma_escalada + (valores / matriz.max() if matriz.max() > 0 else 0.0)
            selectores_mercado.extend(sels)
            segmentos_con_datos += 1
        else:
            valores = np.full(len(ids), np.nan)          # 'sin datos': no es lo mismo que 0 personas
        columnas[f"mercado_{segmento}"] = valores
    columnas["mercado_total"] = suma_escalada / segmentos_con_datos if segmentos_con_datos else np.full(len(ids), np.nan)
    columnas["apoyo_mercado"] = apoyo(selectores_mercado, competidores) if selectores_mercado else np.zeros(len(ids))
    datos_mercado = np.full(len(ids), segmentos_con_datos > 0)

    # --- proveedores ---
    total_prov = np.zeros(len(ids))
    presentes = np.zeros(len(ids))
    selectores_prov = []
    tipos = supplier_selectors(profile)
    tipos_con_datos = 0
    for tipo, sels in tipos.items():
        if sels and counts.count_in_area(sels, competidores) > 0:
            valores = tomar(_vecindad(counts.grid(sels, competidores)))
            total_prov = total_prov + valores
            presentes = presentes + (valores > 0)
            selectores_prov.extend(sels)
            tipos_con_datos += 1
        else:
            valores = np.full(len(ids), np.nan)
        columnas[f"proveedores_{tipo}"] = valores
    columnas["proveedores_total"] = total_prov if tipos_con_datos else np.full(len(ids), np.nan)
    columnas["proveedores_diversidad"] = (presentes / len(tipos)) if tipos_con_datos else np.full(len(ids), np.nan)
    columnas["apoyo_proveedores"] = apoyo(selectores_prov, competidores) if selectores_prov else np.zeros(len(ids))
    datos_prov = np.full(len(ids), tipos_con_datos > 0)

    out = pd.DataFrame(columnas, index=pd.Index(ids, name="cell_id"))
    out["datos_competencia"], out["datos_mercado"], out["datos_proveedores"] = datos_comp, datos_mercado, datos_prov
    out["lentes_con_datos"] = datos_comp.astype(int) + datos_mercado.astype(int) + datos_prov.astype(int)
    return out


def lens_coverage(counts: CellCounts, profile: BusinessProfile) -> pd.DataFrame:
    """Cuántos POIs hay en TODA la rejilla para cada segmento de mercado y cada tipo de proveedor del perfil.

    Una fila por elemento: lente, nombre, pois. `pois == 0` significa que ese elemento no se puede medir con los
    datos actuales (por ejemplo, un solo mayorista o ninguna etiqueta de distribuidores sanitarios)."""
    filas = []
    competidores = tuple(profile.competencia_directa) + tuple(profile.competencia_indirecta)
    for segmento, sels in segment_selectors(profile).items():
        filas.append({"lente": "mercado", "nombre": segmento, "pois": counts.count_in_area(sels, competidores) if sels else 0})
    for tipo, sels in supplier_selectors(profile).items():
        filas.append({"lente": "proveedores", "nombre": tipo, "pois": counts.count_in_area(sels, competidores) if sels else 0})
    for nombre, sels in (("directa", profile.competencia_directa), ("indirecta", profile.competencia_indirecta)):
        filas.append({"lente": "competencia", "nombre": nombre, "pois": counts.count_in_area(sels) if sels else 0})
    return pd.DataFrame(filas)
