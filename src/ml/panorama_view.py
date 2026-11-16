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

from src.locations import LOCATIONS
from src.ml import grid
from src.ml.business_profiles import (
    PROVEEDORES_POI,
    SEGMENTOS_POI,
    BusinessProfile,
    _elementos,
    apply_overrides,
    desviacion_competencia,
)
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
            selector(categoria, sub) if sub else Selector(categoria, frozenset({""}))
        )
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
    return (
        _elementos(a.competencia_directa) == _elementos(b.competencia_directa)
        and _elementos(a.competencia_indirecta) == _elementos(b.competencia_indirecta)
        and set(a.segmentos) == set(b.segmentos)
        and set(a.proveedores) == set(b.proveedores)
    )


def custom_profile(
    base: BusinessProfile,
    opciones: Dict[str, Selector],
    directa: Sequence[str],
    indirecta: Sequence[str],
    segmentos: Sequence[str],
    proveedores: Sequence[str],
) -> Tuple[BusinessProfile, List[str]]:
    """Perfil con los ajustes del usuario y los avisos que corresponden. Si no cambia nada respecto al por defecto,
    devuelve el perfil por defecto (no personalizado) y ningún aviso.

    Un elemento elegido como competencia directa e indirecta a la vez cuenta solo como directa (si no, se contaría dos
    veces); se avisa."""
    avisos: List[str] = []
    en_ambas = [e for e in directa if e in set(indirecta)]
    if en_ambas:
        avisos.append(
            "Elegiste como competencia directa e indirecta a la vez: "
            + ", ".join(en_ambas)
            + ". Cuenta solo como directa."
        )
    ind = [e for e in indirecta if e not in set(directa)]
    perfil, extra = apply_overrides(
        base,
        competencia_directa=tuple(opciones[e] for e in directa),
        competencia_indirecta=tuple(opciones[e] for e in ind),
        segmentos=tuple(segmentos),
        proveedores=tuple(proveedores),
    )
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
    return (
        sub.set_index("cell_id")[list(COLUMNAS_BRECHA)],
        str(sub["modelo_brecha"].iloc[0]),
        bool(sub["brecha_validada"].iloc[0]),
    )


def compute_view(counts: CellCounts, perfil: BusinessProfile, guardado: pd.DataFrame, categoria: str) -> pd.DataFrame:
    """Panorama de las celdas activas con `perfil`, recalculado desde los conteos, con la brecha precalculada de la
    categoría (que no depende del perfil)."""
    brecha, modelo, validada = gap_table(guardado, categoria)
    return build_panorama(counts, perfil, brecha, modelo, validada)


def opportunity_mask(vista: pd.DataFrame) -> pd.Series:
    """Celdas de mercado alto y competencia baja: percentil de mercado ≥ 0,75, percentil de competencia directa ≤ 0,25 y
    confianza no baja. Es un FILTRO, no un puntaje: lo que se pide, a la vista. Como las lentes están muy correlacionadas
    (miden sobre todo cuán urbana es la celda), pocas celdas lo cumplen."""
    return (
        (vista["pct_mercado_total"] >= UMBRAL_MERCADO_ALTO)
        & (vista["pct_competencia_directa"] <= UMBRAL_COMPETENCIA_BAJA)
        & (vista["confianza_nivel"] != "baja")
    )


def cell_label(cell_id: str, fila: pd.Series) -> str:
    """Etiqueta de la celda para elegirla: «Triq il-Kbira, Birkirkara · r23c20»."""
    return f"{place_label(fila)} · {cell_id}"


# ---------------------------------------------------------------------------
# Lugar, celdas por zona y exportación
# ---------------------------------------------------------------------------
RADIO_ZONA_M = 1500.0  # el mismo radio con el que el puntaje por zona cuenta su competencia (location_scoring)
MAX_FILAS_TABLA = 15
FUENTE_DATOS = "© colaboradores de OpenStreetMap (ODbL)"


def attach_places(vista: pd.DataFrame, lugares: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Añade `calle` (la vía con nombre más cercana) y `localidad` (el consejo local de OSM), vacías si no se conocen.
    Sin `lugares` (archivo ausente o alterado) ambas quedan vacías y la pantalla rotula con la zona de referencia."""
    out = vista.copy()
    for col in ("localidad", "calle"):
        disponible = lugares is not None and col in lugares
        out[col] = lugares[col].reindex(out.index).fillna("") if disponible else ""
    return out


def place_label(fila: pd.Series) -> str:
    """Dónde está la celda, en palabras: «Triq il-Kbira, Birkirkara». Sin calle, solo la localidad; sin ninguna de las
    dos (celdas de mar o sin vías con nombre cerca), la zona de referencia."""
    calle = fila.get("calle", "") if hasattr(fila, "get") else ""
    localidad = fila.get("localidad", "") if hasattr(fila, "get") else ""
    calle = calle if isinstance(calle, str) else ""
    localidad = localidad if isinstance(localidad, str) else ""
    if calle and localidad:
        return f"{calle}, {localidad}"
    return calle or localidad or f"cerca de {fila['zona_cercana']}"


def map_link(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.5f}&mlon={lon:.5f}#map=18/{lat:.5f}/{lon:.5f}"


def zone_cells(vista: pd.DataFrame, zona: str) -> pd.Series:
    """Máscara de las celdas cuyo centro está a `RADIO_ZONA_M` o menos del centro de la zona. Una celda puede caer en
    varias zonas (Msida, Gzira, Sliema y St Julian's están a menos de 1,5 km entre sí): no se reparte."""
    if zona not in LOCATIONS:
        raise ValueError(f"Zona desconocida: {zona!r}")
    loc = LOCATIONS[zona]
    d = grid.haversine_m(loc.latitude, loc.longitude, vista["lat"].to_numpy(), vista["lon"].to_numpy())
    return pd.Series(d <= RADIO_ZONA_M, index=vista.index)


def candidate_cells(vista: pd.DataFrame, zona: Optional[str] = None) -> pd.DataFrame:
    """Celdas para revisar primero: las de la zona (todas si `zona` es None) con confianza no baja, ★ primero y luego por
    mercado de mayor a menor. NO es un puntaje: ★ es el filtro de siempre y el resto, solo el orden de una lente. Trae
    `oportunidad` (bool)."""
    dentro = zone_cells(vista, zona) if zona else pd.Series(True, index=vista.index)
    sub = vista[dentro & (vista["confianza_nivel"] != "baja")].copy()
    sub["oportunidad"] = opportunity_mask(vista).reindex(sub.index)
    return sub.sort_values(["oportunidad", "mercado_total"], ascending=[False, False], kind="stable")


def candidates_table(sub: pd.DataFrame) -> pd.DataFrame:
    """Tabla legible de `candidate_cells`, indexada por cell_id. Sin las columnas de lugar (vista sin `attach_places`)
    rotula con la zona de referencia."""
    tabla = pd.DataFrame(
        {
            "★": sub["oportunidad"].map({True: "★", False: ""}),
            "Lugar": sub.apply(place_label, axis=1) if len(sub) else pd.Series(dtype=str),
            "Competencia directa": sub["competencia_directa"],
            "Mercado (0-1)": sub["mercado_total"],
            "Proveedores": sub["proveedores_total"],
            "Confianza": sub["confianza_nivel"],
            "Mapa": [map_link(la, lo) for la, lo in zip(sub["lat"], sub["lon"])],
        },
        index=sub.index,
    )
    tabla.index.name = "Celda"
    return tabla


def zone_summary(vista: pd.DataFrame) -> pd.DataFrame:
    """Las lentes resumidas por zona (celdas a `RADIO_ZONA_M` o menos): celdas activas, cuántas son ★, mediana de cada
    lente y confianza media. Indexada por zona. Mediana, no suma: las zonas tienen distinto número de celdas."""
    estrella = opportunity_mask(vista)
    filas = {}
    for zona in LOCATIONS:
        dentro = zone_cells(vista, zona)
        sub = vista[dentro]
        filas[zona] = {
            "Celdas activas": int(dentro.sum()),
            "Celdas ★": int(estrella[dentro].sum()),
            "Competencia directa (mediana)": sub["competencia_directa"].median(),
            "Mercado (índice mediano)": sub["mercado_total"].median(),
            "Proveedores (mediana)": sub["proveedores_total"].median(),
            "Confianza (media, 0-1)": sub["confianza"].mean(),
        }
    out = pd.DataFrame.from_dict(filas, orient="index")
    out.index.name = "Zona"
    return out


def export_frame(vista: pd.DataFrame, ids: Sequence[str], perfil: BusinessProfile) -> pd.DataFrame:
    """Filas de `ids` listas para exportar: identificación, lentes y percentiles del perfil usado, confianza y enlace."""
    sub = vista.loc[[i for i in ids if i in vista.index]]
    lentes = [
        c for c in sub.columns if c.startswith(("competencia_", "mercado_", "proveedores_")) and sub[c].notna().any()
    ]
    pcts = [c for c in sub.columns if c.startswith("pct_")]
    out = pd.DataFrame(index=sub.index)
    out["calle"] = sub["calle"] if "calle" in sub else ""
    out["localidad"] = sub["localidad"] if "localidad" in sub else ""
    out["zona_referencia"], out["dist_zona_m"] = sub["zona_cercana"], sub["dist_zona_m"]
    out["lat"], out["lon"] = sub["lat"], sub["lon"]
    out = pd.concat([out, sub[lentes + pcts + ["confianza", "confianza_nivel", "pois_vecindad"]]], axis=1)
    out["oportunidad_estrella"] = opportunity_mask(vista).reindex(sub.index)
    out["perfil"], out["perfil_personalizado"] = perfil.nombre, bool(perfil.personalizado)
    out["enlace_mapa"] = [map_link(la, lo) for la, lo in zip(sub["lat"], sub["lon"])]
    out["fuente"] = FUENTE_DATOS
    out.index.name = "cell_id"
    return out


def export_csv(df: pd.DataFrame) -> bytes:
    """CSV en UTF-8 con BOM (Excel lee bien los acentos). Las coordenadas van con 6 decimales (~0,1 m): con `%.6g` como el
    resto de cifras perderían ~10 m."""
    df = df.copy()
    for col in ("lat", "lon"):
        if col in df:
            df[col] = df[col].map("{:.6f}".format)
    return df.to_csv(float_format="%.6g", lineterminator="\n").encode("utf-8-sig")


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
