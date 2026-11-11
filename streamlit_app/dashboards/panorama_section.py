"""Panorama por celda de 250 m (fase 2b de docs/DISENO_ML_RECOMENDACION.md), dentro de la pantalla de Recomendación.

Muestra las tres lentes —competencia, mercado consumidor y proveedores— por separado, sobre un mapa, con la ficha de
cada celda y los controles para ajustar el perfil del negocio. NO hay puntaje combinado, y lo que ve el usuario son
conteos explícitos, no una predicción. La brecha de oferta aprendida se ofrece como una capa aparte, etiquetada como
exploratoria porque la validación espacial no la respaldó (§3.G y §3.H del diseño).

Los datos vienen de data/ml/ (tabla precalculada por tools/build_panorama.py en la máquina de entrenamiento); aquí no se
entrena nada ni se importa scikit-learn. Al ajustar el perfil, las lentes se recalculan desde los conteos precalculados.
"""

import sys
from pathlib import Path
from typing import Optional

import plotly.graph_objects as go
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.ml import panorama
from src.ml import panorama_view as pv
from src.ml.business_profiles import DEFAULT_PROFILES

DATA_ML = ROOT_DIR / "data" / "ml"


@st.cache_data(show_spinner=False)
def _cargar_guardado(ruta: str, firma: str):
    """panorama.csv verificado. `firma` (el hash del manifiesto) invalida la caché si se regenera la tabla."""
    return panorama.read_panorama(ruta)


@st.cache_resource(show_spinner=False)
def _cargar_conteos(ruta: str, firma: str):
    return panorama.read_counts(ruta)


def load_data(ruta: Path):
    """(panorama guardado, conteos, manifiesto) o (None, None, motivo) si la tabla falta o no coincide con su manifiesto."""
    import json

    problemas = panorama.verify_outputs(ruta)
    if problemas:
        return None, None, "; ".join(problemas)
    firma = (ruta / panorama.ARCHIVOS["manifest"]).read_text(encoding="utf-8")
    manifiesto = json.loads(firma)
    return _cargar_guardado(str(ruta), firma), _cargar_conteos(str(ruta), firma), manifiesto


def render_profile_controls(categoria: str, base, counts):
    """Controles del perfil. Devuelve (perfil, avisos)."""
    opciones, def_directa, def_indirecta = pv.competition_options(base, counts)
    with st.expander("⚙️ Ajustar a quién vendes, qué es competencia y qué proveedores", expanded=False):
        st.caption(
            "Partes de un perfil por defecto (borrador del autor, a revisar). Lo que cambies aquí recalcula las "
            "lentes del mapa; **no** reentrena el modelo de brecha, que sigue usando las categorías estándar."
        )
        segmentos = st.multiselect(
            "Le vendes a…", pv.segment_names(), default=list(base.segmentos), key=f"pano_seg_{categoria}"
        )
        c1, c2 = st.columns(2)
        directa = c1.multiselect(
            "Competencia directa", list(opciones), default=def_directa, key=f"pano_dir_{categoria}"
        )
        indirecta = c2.multiselect(
            "Competencia indirecta (sustitutos)", list(opciones), default=def_indirecta, key=f"pano_ind_{categoria}"
        )
        proveedores = st.multiselect(
            "Proveedores que te importan",
            pv.supplier_names(),
            default=list(base.proveedores),
            key=f"pano_prov_{categoria}",
        )
    return pv.custom_profile(base, opciones, directa, indirecta, segmentos, proveedores)


def render_profile_status(perfil, base, avisos):
    """Indica siempre qué perfil se está usando, y avisa cuando se aparta del por defecto."""
    if perfil.personalizado:
        st.info(f"**Perfil personalizado** a partir de «{base.nombre}». Las lentes del mapa usan tus ajustes.")
    else:
        st.caption(f"Perfil usado: **{base.nombre}** (por defecto).")
    for aviso in avisos:
        st.warning(aviso)


def porcentaje(parte: int, total: int) -> str:
    """Porcentaje con un decimal. Con cero decimales 5 de 1139 (0,4 %) se veía como «0%», que parece «ninguna»."""
    return f"{parte / total:.1%}" if total else "—"


def build_map(vista, capa: str, seleccionada: Optional[str]):
    valores, titulo = pv.layer_values(vista, capa)
    con, sin = vista[valores.notna()], vista[valores.isna()]
    textos = [
        f"{i} · {r.zona_cercana}<br>{titulo}: {v:.2f}<br>Confianza: {r.confianza_nivel}"
        for i, r, v in zip(con.index, con.itertuples(), valores[con.index])
    ]
    fig = go.Figure()
    if len(sin):
        fig.add_trace(
            go.Scattermapbox(
                lat=sin["lat"],
                lon=sin["lon"],
                mode="markers",
                marker=dict(size=7, color="#bbbbbb"),
                hovertext=[f"{i}<br>sin datos" for i in sin.index],
                hoverinfo="text",
                name="sin datos",
            )
        )
    esc = "RdBu_r" if capa == pv.CAPA_BRECHA else "YlOrRd"
    fig.add_trace(
        go.Scattermapbox(
            lat=con["lat"],
            lon=con["lon"],
            mode="markers",
            marker=dict(
                size=9,
                color=valores[con.index],
                colorscale=esc,
                showscale=True,
                colorbar=dict(title=titulo),
                opacity=0.9,
                **({"cmid": 0} if capa == pv.CAPA_BRECHA else {}),
            ),
            hovertext=textos,
            hoverinfo="text",
            name=titulo,
        )
    )
    if seleccionada is not None and seleccionada in vista.index:
        f = vista.loc[seleccionada]
        fig.add_trace(
            go.Scattermapbox(
                lat=[f["lat"]],
                lon=[f["lon"]],
                mode="markers+text",
                name="celda elegida",
                marker=dict(size=16, color="#1f77b4"),
                hoverinfo="skip",
                text=[f"Celda elegida: {seleccionada}"],
                textposition="top right",
                textfont=dict(size=14, color="#0b3d6b"),
            )
        )
    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=float(vista["lat"].mean()), lon=float(vista["lon"].mean())),
            zoom=10.5,
        ),
        height=520,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    return fig


def _valor(x, formato="{:.2f}"):
    return "sin datos" if x != x else formato.format(x)


def render_cell_card(fila, perfil, brecha_disponible: bool, perfil_personalizado: bool):
    st.markdown(
        f"##### Ficha de la celda {fila.name} · zona más cercana: {fila['zona_cercana']} ({fila['dist_zona_m']:.0f} m)"
    )
    c1, c2, c3 = st.columns(3)
    c1.markdown("**Competencia**")
    c1.write(f"Directa: {_valor(fila['competencia_directa'])} · indirecta: {_valor(fila['competencia_indirecta'])}")
    c1.caption(
        f"Percentil entre las celdas: {_valor(fila['pct_competencia_directa'], '{:.0%}')} (más alto = más competencia)"
    )
    c2.markdown("**Mercado consumidor**")
    c2.write(f"Índice 0-1: {_valor(fila['mercado_total'])}")
    for col in [c for c in fila.index if c.startswith("mercado_") and c != "mercado_total"]:
        c2.caption(f"{col.removeprefix('mercado_').replace('_', ' ')}: {_valor(fila[col], '{:.1f}')}")
    c3.markdown("**Proveedores**")
    c3.write(
        f"Total: {_valor(fila['proveedores_total'], '{:.1f}')} · diversidad: {_valor(fila['proveedores_diversidad'])}"
    )
    for col in [
        c
        for c in fila.index
        if c.startswith("proveedores_") and c not in ("proveedores_total", "proveedores_diversidad")
    ]:
        if fila[col] == fila[col]:
            c3.caption(f"{col.removeprefix('proveedores_').replace('_', ' ')}: {fila[col]:.1f}")
    st.caption(
        f"**Confianza de datos: {fila['confianza_nivel']}** ({fila['confianza']:.2f} de 1). Resume cuántas lentes tienen datos "
        f"y cuántos POIs sustentan cada una (hay {int(fila['pois_vecindad'])} POIs en la celda y sus 8 vecinas); "
        "no es una probabilidad."
    )
    if brecha_disponible and fila["brecha_relativa"] == fila["brecha_relativa"]:
        st.warning(
            f"**Brecha de oferta EXPLORATORIA (no validada):** {fila['brecha_relativa']:+.2f} desviaciones típicas "
            f"(esperado {fila['esperado']:.1f} locales; entre {fila['brecha_p10']:+.2f} y {fila['brecha_p90']:+.2f} según "
            "cómo se reparta la validación). Positiva = menos locales de los que el modelo esperaría. La validación espacial "
            "no mostró que supere a la simple densidad de comercios, y el intervalo no es de confianza."
            + (" Usa las categorías estándar, no tu perfil." if perfil_personalizado else "")
        )


def render_panorama_section(categoria: str, data_dir: Optional[Path] = None):
    """Sección completa para una categoría de Overpass (food_drink, business, hospital, school, sport, leisure o mall)."""
    ruta = Path(data_dir) if data_dir is not None else DATA_ML
    st.divider()
    st.subheader("🗺️ Panorama por celda de 250 m")
    base = DEFAULT_PROFILES.get(categoria)
    if base is None:
        st.info("Esta categoría no tiene panorama por celda.")
        return
    guardado, counts, manifiesto = load_data(ruta)
    if guardado is None:
        st.info(f"El panorama por celda no está disponible: {manifiesto}. Se genera con `tools/build_panorama.py`.")
        return
    st.caption(
        "Tres lentes por separado —**competencia**, **mercado consumidor** y **proveedores**— sobre celdas de 250 m, con "
        "indicadores explícitos (conteos de POIs de OpenStreetMap ponderados por vecindad). **No hay un puntaje combinado**: "
        "las tres lentes están muy correlacionadas porque miden sobre todo cuán urbana es la celda, y los datos no permiten "
        "aprender cuánto vale cada una."
    )

    perfil, avisos = render_profile_controls(categoria, base, counts)
    render_profile_status(perfil, base, avisos)
    vista = pv.compute_view(counts, perfil, guardado, categoria)

    capas = pv.available_layers(vista)
    capa = st.radio("Qué mostrar en el mapa", capas, horizontal=True, key=f"pano_capa_{categoria}")
    if capa == pv.CAPA_BRECHA:
        st.warning(
            "Capa **exploratoria**: no está validada. En la validación espacial ningún modelo superó con claridad a la densidad de "
            "comercios, así que esta brecha puede reflejar solo cuán saturada o vacía está una zona. "
            + ("No cambia con tu perfil: usa las categorías estándar." if perfil.personalizado else "")
        )

    oportunidad = pv.opportunity_mask(vista)
    candidatas = vista[oportunidad].sort_values("mercado_total", ascending=False)
    opciones_celdas = list(candidatas.index) + [i for i in vista.index if i not in set(candidatas.index)]
    etiquetas = {i: pv.cell_label(i, vista.loc[i]) for i in opciones_celdas}
    elegida = st.selectbox(
        "Celda para ver su ficha (primero, las de mercado alto y competencia baja)",
        opciones_celdas,
        format_func=lambda i: ("★ " if i in candidatas.index else "") + etiquetas[i],
        key=f"pano_celda_{categoria}",
    )

    st.plotly_chart(build_map(vista, capa, elegida), width="stretch")

    st.caption(
        f"★ = mercado en el 25 % superior y competencia directa en el 25 % inferior, con confianza no baja: **{len(candidatas)} de "
        f"{len(vista)} celdas** ({porcentaje(len(candidatas), len(vista))}). Es un filtro, no un puntaje; si las lentes fueran independientes "
        "serían ~6 %, pero como se parecen, pocas celdas cumplen ambas cosas."
    )
    render_cell_card(vista.loc[elegida], perfil, bool(vista["brecha_relativa"].notna().any()), perfil.personalizado)
    st.caption(
        f"Datos: tabla precalculada el {manifiesto.get('procedencia', {}).get('ejecutado', 'fecha desconocida')} "
        f"(commit {manifiesto.get('procedencia', {}).get('commit', '?')}), {len(vista)} celdas activas. Los residentes se "
        "aproximan con edificios no claramente no residenciales (en Malta, ~78 % de los edificios son `building=yes`): es un "
        "proxy de superficie construida, no población."
    )
