"""Panorama por celda de 250 m (fase 2b de docs/DISENO_ML_RECOMENDACION.md), dentro de la pantalla de Recomendación.

Muestra las tres lentes —competencia, mercado consumidor y proveedores— por separado, sobre un mapa, con la ficha de
cada celda y los controles para ajustar el perfil del negocio. NO hay puntaje combinado, y lo que ve el usuario son
conteos explícitos, no una predicción. La brecha de oferta aprendida se ofrece como una capa aparte, etiquetada como
exploratoria porque la validación espacial no la respaldó (§3.G y §3.H del diseño).

Los datos vienen de data/ml/ (tabla precalculada por tools/build_panorama.py en la máquina de entrenamiento); aquí no se
entrena nada ni se importa scikit-learn. Al ajustar el perfil, las lentes se recalculan desde los conteos precalculados.
"""

import hashlib
import html
import sys
from pathlib import Path
from typing import Optional

import plotly.graph_objects as go
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.locations import LOCATIONS
from src.ml import grid, panorama
from src.ml import panorama_view as pv
from src.ml import places
from src.ml.business_profiles import DEFAULT_PROFILES

DATA_ML = ROOT_DIR / "data" / "ml"


@st.cache_data(show_spinner=False)
def _cargar_guardado(ruta: str, firma: str):
    """panorama.csv verificado. `firma` (el hash del manifiesto) invalida la caché si se regenera la tabla."""
    return panorama.read_panorama(ruta)


@st.cache_resource(show_spinner=False)
def _cargar_conteos(ruta: str, firma: str):
    return panorama.read_counts(ruta)


@st.cache_data(show_spinner=False)
def _cargar_lugares(ruta: str, firma: str):
    return places.read_places(ruta)


def load_places(ruta: Path):
    """Serie cell_id → localidad de data/ml/cell_places.csv, o None si falta o no coincide con su manifiesto (entonces las
    celdas se rotulan con la zona de referencia, como antes)."""
    manifiesto = ruta / places.ARCHIVOS["manifest"]
    if not manifiesto.exists():
        return None
    return _cargar_lugares(str(ruta), manifiesto.read_text(encoding="utf-8"))


def load_data(ruta: Path):
    """(panorama guardado, conteos, manifiesto) o (None, None, motivo) si la tabla falta o no coincide con su manifiesto."""
    import json

    problemas = panorama.verify_outputs(ruta)
    if problemas:
        return None, None, "; ".join(problemas)
    firma = (ruta / panorama.ARCHIVOS["manifest"]).read_text(encoding="utf-8")
    manifiesto = json.loads(firma)
    return _cargar_guardado(str(ruta), firma), _cargar_conteos(str(ruta), firma), manifiesto


def render_profile_controls(categoria: str, base, counts, con_brecha: bool = False):
    """Controles del perfil. Devuelve (perfil, avisos). `con_brecha`: la tabla trae brecha para esta categoría (solo entonces
    se habla del modelo de brecha)."""
    opciones, def_directa, def_indirecta = pv.competition_options(base, counts)
    with st.expander("⚙️ Ajustar a quién vendes, qué es competencia y qué proveedores", expanded=False):
        st.caption(
            "Partes de un perfil por defecto (borrador del autor, a revisar). Lo que cambies aquí recalcula las "
            "lentes del mapa."
            + (
                "  **No** reentrena el modelo de brecha, que sigue usando las categorías estándar."
                if con_brecha
                else ""
            )
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


ZOOM_ISLA = 10.5  # toda la rejilla: para comparar celdas entre sí
ZOOM_CELDA = 15.5  # una celda de 250 m con sus calles alrededor


def cuadrado_celda(cell_id: str):
    """(latitudes, longitudes) del contorno cerrado de la celda, para dibujarla como el cuadrado de 250 m que es."""
    sur, oeste, norte, este = grid.cell_bounds(*grid.parse_cell_id(cell_id))
    return [sur, sur, norte, norte, sur], [oeste, este, este, oeste, oeste]


def build_map(vista, capa: str, seleccionada: Optional[str], acercar: bool = False):
    """Mapa de la capa elegida. Si hay celda elegida se dibuja su cuadrado de 250 m; con `acercar`, el mapa se centra en
    ella y se acerca hasta que se ven las calles (que es lo que permite reconocer el sitio)."""
    valores, titulo = pv.layer_values(vista, capa)
    con, sin = vista[valores.notna()], vista[valores.isna()]
    textos = [
        f"{i} · {html.escape(pv.place_label(r))}<br>{titulo}: {v:.2f}<br>Confianza: {r['confianza_nivel']}"
        for i, (_, r), v in zip(con.index, con.iterrows(), valores[con.index])
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
    elegida = seleccionada if seleccionada is not None and seleccionada in vista.index else None
    centro = dict(lat=float(vista["lat"].mean()), lon=float(vista["lon"].mean()))
    zoom = ZOOM_ISLA
    if elegida is not None:
        f = vista.loc[elegida]
        lat_sq, lon_sq = cuadrado_celda(elegida)
        fig.add_trace(
            go.Scattermapbox(
                lat=lat_sq,
                lon=lon_sq,
                mode="lines",
                fill="toself",
                fillcolor="rgba(31,119,180,0.25)",
                line=dict(width=3, color="#1f77b4"),
                name="celda elegida",
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scattermapbox(
                lat=[f["lat"]],
                lon=[f["lon"]],
                mode="markers+text",
                name="celda elegida",
                marker=dict(size=16, color="#1f77b4"),
                hoverinfo="skip",
                text=[f"{elegida} · {pv.place_label(f)}"],
                textposition="top right",
                textfont=dict(size=14, color="#0b3d6b"),
            )
        )
        if acercar:
            centro, zoom = dict(lat=float(f["lat"]), lon=float(f["lon"])), ZOOM_CELDA
    fig.update_layout(
        mapbox=dict(style="open-street-map", center=centro, zoom=zoom),
        height=520,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    return fig


def _valor(x, formato="{:.2f}"):
    return "sin datos" if x != x else formato.format(x)


def render_cell_card(fila, perfil, brecha_disponible: bool, perfil_personalizado: bool):
    st.markdown(f"##### Ficha de la celda {fila.name} · {pv.place_label(fila)}")
    st.caption(
        f"Zona de referencia: {fila['zona_cercana']} ({fila['dist_zona_m']:.0f} m del centro de la zona) · "
        f"[ver la celda en OpenStreetMap]({pv.map_link(fila['lat'], fila['lon'])})"
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


COLUMNAS_TABLA = {
    "Competencia directa": st.column_config.NumberColumn(format="%.2f"),
    "Mercado (0-1)": st.column_config.NumberColumn(format="%.2f"),
    "Proveedores": st.column_config.NumberColumn(format="%.1f"),
    "Mapa": st.column_config.LinkColumn("Mapa", display_text="Abrir"),
}


def firma_tabla(tabla) -> str:
    """Huella corta de las celdas (y su orden) de la tabla, para la clave de su selección."""
    return hashlib.md5("|".join(map(str, tabla.index)).encode("utf-8")).hexdigest()[:10]


def render_candidate_cells(vista, perfil, categoria: str, zona: Optional[str], destino=None):
    """Tabla de celdas de la zona recomendada (o de todas, sin zona) con las tres lentes, enlace al mapa y exportación a
    CSV en dos pasos: el usuario marca filas, pulsa «Confirmar selección» y solo entonces aparece la descarga."""
    zona = zona if zona in LOCATIONS else None  # una zona que el panorama no conoce no debe romper la sección
    with destino if destino is not None else st.container():
        ambito = f"la zona {zona}" if zona else "todas las zonas"
        st.markdown(f"#### 📍 Celdas de {ambito}: dónde mirar primero")
        candidatas = pv.candidate_cells(vista, zona)
        if candidatas.empty:
            st.info(
                f"No hay celdas con confianza de datos media o alta en {ambito}. Mira el panorama completo más abajo."
            )
            return
        todas = st.toggle(
            f"Ver las {len(candidatas)} celdas (no solo las {pv.MAX_FILAS_TABLA} primeras)",
            value=False,
            key=f"pano_todas_{categoria}",
            disabled=len(candidatas) <= pv.MAX_FILAS_TABLA,
        )
        mostradas = candidatas if todas else candidatas.head(pv.MAX_FILAS_TABLA)
        tabla = pv.candidates_table(mostradas)
        n_estrella = int(candidatas["oportunidad"].sum())
        st.caption(
            f"Radio de la zona: {pv.RADIO_ZONA_M:.0f} m desde su centro (el mismo con el que se cuenta su competencia); "
            f"solo celdas con confianza media o alta. ★ = mercado alto y competencia baja: **{n_estrella}** en {ambito}. "
            "El resto va ordenado por mercado, de mayor a menor. **No es un puntaje**: pulsa el título de una columna para "
            "ordenar por otra lente."
        )
        # La clave lleva las celdas (y su orden) que muestra la tabla: la selección es por POSICIÓN de fila, así que si la
        # tabla cambia (zona, perfil, «ver todas») se empieza sin filas marcadas en vez de marcar otras celdas.
        clave = f"pano_top_{categoria}_{firma_tabla(tabla)}"
        evento = st.dataframe(
            tabla,
            column_config=COLUMNAS_TABLA,
            on_select="rerun",
            selection_mode="multi-row",
            key=clave,
            width="stretch",
        )
        posiciones = [p for p in (evento.selection.rows if evento is not None else []) if 0 <= p < len(tabla)]
        marcadas = list(tabla.index[posiciones])
        confirmada_clave = f"pano_conf_{categoria}"
        firma_confirmacion = f"{zona}|{perfil!r}"
        if st.button(
            f"Confirmar selección ({len(marcadas)}) y preparar CSV",
            disabled=not marcadas,
            key=f"pano_confirmar_{categoria}",
            help="Marca una o más filas de la tabla; el CSV se prepara solo al confirmar.",
        ):
            st.session_state[confirmada_clave] = {"ids": marcadas, "firma": firma_confirmacion}
        if not marcadas:
            st.caption("Marca filas de la tabla para exportarlas.")
        guardada = st.session_state.get(confirmada_clave)
        if guardada and guardada["firma"] != firma_confirmacion:
            # Cambió la zona o el perfil: el CSV mezclaría la selección vieja con lentes de otro perfil.
            del st.session_state[confirmada_clave]
            st.caption(
                "Se descartó la selección confirmada porque cambiaron la zona o el perfil: vuelve a elegir y confirmar."
            )
            guardada = None
        confirmadas = [c for c in (guardada["ids"] if guardada else []) if c in vista.index]
        if confirmadas:
            if set(marcadas) != set(confirmadas):
                st.caption(
                    "La selección de la tabla cambió desde la última confirmación: vuelve a confirmar para actualizarla."
                )
            datos = pv.export_csv(pv.export_frame(vista, confirmadas, perfil))
            st.download_button(
                f"⬇️ Descargar CSV de {len(confirmadas)} celda(s) confirmada(s)",
                data=datos,
                file_name=f"celdas_{categoria}.csv",
                mime="text/csv",
                key=f"pano_descarga_{categoria}",
            )
            st.caption(
                "El CSV usa el perfil elegido (con tus ajustes, si los hay), e incluye lentes, percentiles, confianza y "
                "enlace al mapa. Datos © colaboradores de OpenStreetMap (ODbL)."
            )


def render_zone_lenses(vista, destino=None):
    """Las lentes resumidas por zona, para leerlas junto al desglose del puntaje por zona."""
    with destino if destino is not None else st.container():
        st.markdown("#### Lentes del panorama por zona")
        resumen = pv.zone_summary(vista)
        st.dataframe(
            resumen,
            column_config={
                "Competencia directa (mediana)": st.column_config.NumberColumn(format="%.2f"),
                "Mercado (índice mediano)": st.column_config.NumberColumn(format="%.2f"),
                "Proveedores (mediana)": st.column_config.NumberColumn(format="%.1f"),
                "Confianza (media, 0-1)": st.column_config.NumberColumn(format="%.2f"),
            },
            width="stretch",
        )
        st.caption(
            f"Celdas activas a {pv.RADIO_ZONA_M:.0f} m o menos del centro de cada zona (una celda puede estar en varias). "
            "Medianas, no sumas, porque las zonas tienen distinto número de celdas. Responde a tu perfil y es "
            "información aparte del puntaje de arriba: no se combinan."
        )


def render_panorama_section(
    categoria: str,
    data_dir: Optional[Path] = None,
    zona: Optional[str] = None,
    destino_celdas=None,
    destino_zonas=None,
):
    """Sección completa para una categoría de Overpass (food_drink, business, hospital, school, sport, leisure o mall).

    `zona`: la zona recomendada por el puntaje; con ella la tabla de celdas se limita a esa zona. `destino_celdas` y
    `destino_zonas`: contenedores de Streamlit creados antes (p. ej. justo bajo la zona recomendada) donde dibujar la
    tabla de celdas y el resumen por zona; sin ellos se dibujan dentro de la sección."""
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

    con_brecha = bool(guardado.loc[guardado["perfil"] == categoria, "brecha_relativa"].notna().any())
    perfil, avisos = render_profile_controls(categoria, base, counts, con_brecha)
    render_profile_status(perfil, base, avisos)
    vista = pv.attach_places(pv.compute_view(counts, perfil, guardado, categoria), load_places(ruta))
    render_candidate_cells(vista, perfil, categoria, zona, destino_celdas)
    render_zone_lenses(vista, destino_zonas)

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

    acercar = st.toggle(
        "🔍 Acercar a la celda elegida (para ver sus calles)",
        value=True,
        key=f"pano_acercar_{categoria}",
        help="Apágalo para volver a ver toda la rejilla y comparar unas celdas con otras.",
    )
    st.plotly_chart(build_map(vista, capa, elegida, acercar), width="stretch")
    st.caption(
        "La celda elegida se dibuja como el cuadrado de 250 m que es."
        + ("" if acercar else " Acércate con el control de arriba para ver sus calles.")
    )

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
        + (
            " Después se retiró la brecha de oferta del panorama publicado (condiciones de datos de terceros); las lentes no cambian."
            if manifiesto.get("derivado")
            else ""
        )
    )
