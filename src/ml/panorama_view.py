"""Lógica del panorama por celda para la pantalla de Recomendación (fase 2b), sin Streamlit: se puede probar sin abrir la
interfaz y no importa scikit-learn.

Qué hace:
  - Construye las opciones y el perfil personalizado: qué cuenta como competencia directa e indirecta, a quién vende el
    negocio y qué proveedores le importan (partiendo del perfil por defecto; ver business_profiles.apply_overrides).
  - Recalcula el panorama con ese perfil desde los conteos precalculados (data/ml/cell_counts.csv), sin la base.
  - Le une la brecha de oferta precalculada, que NO se recalcula: es del perfil estándar de la categoría.
  - Marca las celdas «de mercado alto y competencia baja» con un filtro transparente (percentiles), no con un puntaje.
"""

from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.ml.business_profiles import (PROVEEDORES_POI, SEGMENTOS_POI, BusinessProfile, _elementos, apply_overrides,
                                      desviacion_competencia)
from src.ml.cell_counts import CellCounts, Selector, selector
from src.ml.osm_context import CONTEXTO
from src.ml.panorama import COLUMNAS_BRECHA, build_panorama

# Capas del mapa: etiqueta → (columna con el valor, columna con el percentil). Las tres lentes por separado; la brecha
# va aparte y etiquetada (sección «capa exploratoria»).
CAPAS = {
    "Competencia directa (conteo ponderado)": ("competencia_directa", "pct_competencia_directa"),
    "Mercado (índice 0-1)": ("mercado_total", "pct_mercado_total"),
    "Proveedores (conteo ponderado)": ("proveedores_total", "pct_proveedores_total"),
    "Diversidad de proveedores (0-1)": ("proveedores_diversidad", "pct_proveedores_diversidad"),
}
CAPA_BRECHA = "Brecha de oferta — EXPLORATORIA, no validada"
UMBRAL_MERCADO_ALTO = 0.75
UMBRAL_COMPETENCIA_BAJA = 0.25
TODA_LA_CATEGORIA = " (toda la categoría)"


# ---------------------------------------------------------------------------
# Opciones de competencia
# ---------------------------------------------------------------------------
def expand_selectors(selectors: Sequence[Selector]) -> Dict[str, Selector]:
    """Etiqueta legible → selector, con cada subcategoría por separado. La unión de los selectores resultantes es la
    misma que la de los originales."""
    out: Dict[str, Selector] = {}
    for s in selectors:
        if s.subcategories is not None:
            for sub in sorted(s.subcategories):
                out[f"{s.category}: {sub}"] = selector(s.category, sub)
        elif s.excluding:
            muestra = ", ".join(sorted(s.excluding)[:3])
            out[f"{s.category} (todo salvo {len(s.excluding)} subcategorías, p. ej. {muestra})"] = s
        else:
            out[f"{s.category}{TODA_LA_CATEGORIA}"] = s
    return out


def available_pairs(counts: CellCounts) -> Dict[str, Selector]:
    """(categoría: subcategoría) que existen en los datos, sin las categorías de contexto de OSM (edificios, transporte...),
    que no son comercios. Sirven para AÑADIR competencia a un perfil."""
    out: Dict[str, Selector] = {}
    for categoria, sub in counts.pairs():
        if categoria in CONTEXTO or counts.arrays[(categoria, sub)].sum() <= 0:
            continue
        out[f"{categoria}: {sub}" if sub else f"{categoria}: (sin subcategoría)"] = (
            selector(categoria, sub) if sub else Selector(categoria, frozenset({""})))
    return out


def competition_options(base: BusinessProfile, counts: CellCounts):
    """(opciones, por defecto directa, por defecto indirecta): `opciones` es etiqueta → selector, con la competencia por
    defecto del perfil y todo lo que se puede añadir; los otros dos son las etiquetas por defecto de cada tipo."""
    directa = expand_selectors(base.competencia_directa)
    indirecta = expand_selectors(base.competencia_indirecta)
    opciones = {**available_pairs(counts), **indirecta, **directa}
    return opciones, list(directa), list(indirecta)


def same_profile(a: BusinessProfile, b: BusinessProfile) -> bool:
    """¿Definen lo mismo? Compara los elementos atómicos de la competencia, y los segmentos y proveedores como conjuntos."""
    return (_elementos(a.competencia_directa) == _elementos(b.competencia_directa)
            and _elementos(a.competencia_indirecta) == _elementos(b.competencia_indirecta)
            and set(a.segmentos) == set(b.segmentos) and set(a.proveedores) == set(b.proveedores))


def custom_profile(base: BusinessProfile, opciones: Dict[str, Selector], directa: Sequence[str], indirecta: Sequence[str],
                   segmentos: Sequence[str], proveedores: Sequence[str]) -> Tuple[BusinessProfile, List[str]]:
    """Perfil con los ajustes del usuario y los avisos que corresponden. Si no cambia nada respecto al por defecto,
    devuelve el perfil por defecto (no personalizado) y ningún aviso.

    Un elemento elegido como competencia directa e indirecta a la vez cuenta solo como directa (si no, se contaría dos
    veces); se avisa."""
    avisos: List[str] = []
    en_ambas = [e for e in directa if e in set(indirecta)]
    if en_ambas:
        avisos.append("Elegiste como competencia directa e indirecta a la vez: " + ", ".join(en_ambas)
                      + ". Cuenta solo como directa.")
    ind = [e for e in indirecta if e not in set(directa)]
    perfil, extra = apply_overrides(
        base, competencia_directa=tuple(opciones[e] for e in directa),
        competencia_indirecta=tuple(opciones[e] for e in ind),
        segmentos=tuple(segmentos), proveedores=tuple(proveedores))
    avisos += extra
    if same_profile(perfil, base) and not avisos:
        return base, []
    return perfil, avisos


def deviation(perfil: BusinessProfile, base: BusinessProfile) -> float:
    """Fracción de la competencia por defecto que el perfil ya no incluye (ver business_profiles.desviacion_competencia)."""
    return desviacion_competencia(perfil, base)


# ---------------------------------------------------------------------------
# Panorama con el perfil elegido
# ---------------------------------------------------------------------------
def gap_table(guardado: pd.DataFrame, categoria: str) -> Tuple[Optional[pd.DataFrame], str, bool]:
    """Brecha precalculada de `categoria` desde panorama.csv: (tabla indexada por cell_id, modelo, validada). Si esa
    categoría no tiene brecha, (None, '', False)."""
    sub = guardado[guardado["perfil"] == categoria]
    if sub.empty or sub["esperado"].isna().all():
        return None, "", False
    return (sub.set_index("cell_id")[list(COLUMNAS_BRECHA)], str(sub["modelo_brecha"].iloc[0]),
            bool(sub["brecha_validada"].iloc[0]))


def compute_view(counts: CellCounts, perfil: BusinessProfile, guardado: pd.DataFrame, categoria: str) -> pd.DataFrame:
    """Panorama de las celdas activas con `perfil`, recalculado desde los conteos, con la brecha precalculada de la
    categoría (que no depende del perfil)."""
    brecha, modelo, validada = gap_table(guardado, categoria)
    return build_panorama(counts, perfil, brecha, modelo, validada)


def opportunity_mask(vista: pd.DataFrame) -> pd.Series:
    """Celdas de mercado alto y competencia baja: percentil de mercado ≥ 0,75, percentil de competencia directa ≤ 0,25 y
    confianza no baja. Es un FILTRO, no un puntaje: lo que se pide, a la vista. Como las lentes están muy correlacionadas
    (miden sobre todo cuán urbana es la celda), pocas celdas lo cumplen."""
    return ((vista["pct_mercado_total"] >= UMBRAL_MERCADO_ALTO)
            & (vista["pct_competencia_directa"] <= UMBRAL_COMPETENCIA_BAJA)
            & (vista["confianza_nivel"] != "baja"))


def cell_label(cell_id: str, fila: pd.Series) -> str:
    return f"{cell_id} · {fila['zona_cercana']} ({fila['dist_zona_m']:.0f} m del centro de zona)"


def layer_values(vista: pd.DataFrame, capa: str) -> Tuple[pd.Series, str]:
    """(valores, título) de la capa del mapa. La de brecha es la brecha relativa, en desviaciones típicas."""
    if capa == CAPA_BRECHA:
        return vista["brecha_relativa"], "Brecha relativa"
    columna, _ = CAPAS[capa]
    return vista[columna], capa.split(" (")[0]


def available_layers(vista: pd.DataFrame) -> List[str]:
    """Capas con datos: se omite la que es toda NaN y la brecha si la categoría no la tiene."""
    capas = [c for c, (col, _) in CAPAS.items() if col in vista and vista[col].notna().any()]
    if vista["brecha_relativa"].notna().any():
        capas.append(CAPA_BRECHA)
    return capas


def segment_names() -> List[str]:
    return list(SEGMENTOS_POI)


def supplier_names() -> List[str]:
    return list(PROVEEDORES_POI)
