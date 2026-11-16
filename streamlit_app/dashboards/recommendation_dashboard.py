"""Dashboard de recomendación de ubicación: ¿dónde conviene abrir un negocio?

Interfaz para el sistema de apoyo a la decisión de src/location_scoring.py —
ver ahí el porqué del método (MCDA, no machine learning) y el detalle de
cada dimensión.
"""

import html
import sys
from pathlib import Path
from typing import Optional

import plotly.graph_objects as go
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase
from src.location_scoring import (
    CRITERIOS,
    build_zone_features,
    criterios_disponibles,
    filter_zones,
    pesos_por_defecto,
    recommend_for_category,
)
from src.locations import LOCATIONS
from src.ml import panorama_view as pv
from src.ml.business_profiles import DEFAULT_PROFILES
from src.ml.text_hibrido import CATEGORIAS, FUENTE_MODELO, Interpretacion, cargar_modelo_adoptado, interpretar
from streamlit_app.dashboards import panorama_section as ps
from streamlit_app.dashboards.maps_dashboard import POI_CATEGORY_STYLE
from streamlit_app.dashboards.panorama_section import render_panorama_section

_CACHE_TTL = 60
# Solo para poder enseñar los controles ANTES de que haya un negocio escrito. Qué criterios hay depende de la
# categoría: `business`, `hospital` y `leisure` no tienen ningún proveedor con datos, así que para ellas no se ofrecen
# «proveedores» ni «diversidad». En cuanto se interpreta el texto, los controles se rehacen con los de esa categoría.
CATEGORIA_INICIAL = "food_drink"


@st.cache_resource
def get_database():
    DB_PATH = ROOT_DIR / "data" / "mobility.db"
    CSV_PATH = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"
    return RouteDatabase(CSV_PATH, DB_PATH)


@st.cache_resource
def get_text_model():
    """El clasificador de texto adoptado en la fase 3 (verificado con su manifiesto), o None si falta o no cuadra: en
    ese caso la pantalla usa solo las palabras clave, como antes."""
    return cargar_modelo_adoptado()


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _medianas_por_zona(categoria: str):
    """Las lentes del panorama agregadas por zona, con el perfil POR DEFECTO de la categoría.

    El perfil por defecto es a propósito: el puntaje por zona se calcula ARRIBA, antes de que el usuario toque los
    controles del panorama, que están más abajo. Atarlos crearía un círculo —el perfil cambiaría el puntaje, el puntaje
    elige la zona, la zona filtra el panorama—. La pantalla lo dice. Devuelve None sin `data/ml/`."""
    guardado, counts, _ = ps.load_data(ps.DATA_ML)
    if guardado is None or categoria not in DEFAULT_PROFILES:
        return None
    return pv.zone_lens_medians(pv.compute_view(counts, DEFAULT_PROFILES[categoria], guardado, categoria))


@st.cache_data(ttl=_CACHE_TTL, show_spinner="Calculando puntajes por zona...")
def _cached_recommend(_db, categoria: str, pesos: tuple):
    """Envuelve recommend_for_category() para que Streamlit lo cachee por categoría y pesos. Los pesos van como una
    tupla de pares (clave, peso) y no como dict: un dict no sirve como parte de la clave de caché de forma confiable."""
    return recommend_for_category(_db, categoria, weights=dict(pesos), medianas=_medianas_por_zona(categoria))


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _criterios(_db, categoria: str):
    """Los criterios que se pueden puntuar hoy para esta categoría. Sin `data/ml/` son los tres de la base."""
    return criterios_disponibles(build_zone_features(_db, categoria, medianas=_medianas_por_zona(categoria)))


def etiqueta_categoria(categoria: str) -> str:
    return POI_CATEGORY_STYLE.get(categoria, {}).get("label", categoria)


def render_interpretacion(texto: str, interpretacion: Interpretacion) -> str:
    """Dice cómo se entendió el texto y quién lo decidió, y deja cambiar la categoría. Devuelve la categoría a usar.

    El modelo entrenado entra solo donde las palabras clave no reconocen el negocio. Su lectura se marca como decidida por
    el modelo, con su confianza, y se abre el selector: es una lectura que el usuario no puede anticipar por una palabra
    visible y casi no está medida (19 respuestas en la evaluación, 1 equivocada: ver docs/DISENO_ML_RECOMENDACION.md
    §3.L2). No se sabe que sea peor que las palabras clave, que también se equivocan (10 % de sus respuestas en esa
    evaluación). En ambos casos el usuario puede corregir la categoría."""
    categoria = interpretacion.categoria
    if interpretacion.fuente == FUENTE_MODELO:
        st.warning(
            f"Interpretado como: **{etiqueta_categoria(categoria)}**, por el modelo entrenado "
            f"(confianza {interpretacion.confianza:.0%}). No reconocí una palabra clave en tu texto, así que lo decidió el "
            "modelo: revisa que sea lo que querías."
        )
    else:
        st.success(f"Interpretado como: **{etiqueta_categoria(categoria)}**")
    with st.expander("¿No es lo que querías? Cambiar la categoría", expanded=interpretacion.fuente == FUENTE_MODELO):
        elegida = st.selectbox(
            "Categoría a usar",
            CATEGORIAS,
            index=CATEGORIAS.index(categoria),
            format_func=etiqueta_categoria,
            key=f"reco_cat::{texto}",  # otro texto, otra elección: no arrastra la corrección de una búsqueda anterior
        )
    if elegida != categoria:
        st.info(
            f"Usando la categoría que elegiste: **{etiqueta_categoria(elegida)}** (se había interpretado {etiqueta_categoria(categoria)})."
        )
    return elegida


def normalize_weights(crudos: dict, criterios) -> dict:
    """Pesos tal como vienen de los deslizadores (no hace falta que sumen 100) -> dict normalizado a 1,0, como exige
    score_zones().

    Un factor en 0 se deja FUERA del resultado, no se pasa con peso cero: es lo que promete la ayuda del control, y así
    no cuenta como «factor puntuado» ni dispara el aviso de datos incompletos por algo que no aporta nada. Si el
    usuario lo baja todo a cero no hay nada que comparar: se vuelve a los de fábrica en vez de dividir entre cero."""
    total = sum(crudos.values())
    if total <= 0:
        return pesos_por_defecto(criterios)
    return {clave: valor / total for clave, valor in crudos.items() if valor > 0}


def render_zone_filter() -> list:
    """Qué zonas entran en el ranking. Es un FILTRO, no un peso: no toca el puntaje, solo quita filas."""
    elegidas = st.multiselect(
        "Zonas a considerar",
        list(LOCATIONS),
        default=list(LOCATIONS),
        help="Si solo te interesan algunas zonas, quédate con ellas. El puntaje de cada una no cambia.",
        key="reco_zonas",
    )
    if not elegidas:
        st.warning("No dejaste ninguna zona: se muestran todas.")
    return elegidas or list(LOCATIONS)


def render_weight_controls(criterios) -> dict:
    """Un deslizador por criterio disponible. Devuelve los pesos ya normalizados a 1."""
    with st.expander("⚙️ Ajustar qué tanto pesa cada factor"):
        st.caption(
            "Importancia relativa de cada factor — no hace falta que sumen 100, se normalizan solos. Pon uno en 0 para "
            "dejarlo fuera del puntaje."
        )
        crudos = {}
        columnas = st.columns(2)
        for i, criterio in enumerate(criterios):
            crudos[criterio.clave] = columnas[i % 2].slider(
                criterio.etiqueta,
                0,
                100,
                int(criterio.peso_defecto * 100),
                help=criterio.ayuda,
                key=f"reco_peso_{criterio.clave}",
            )
        faltan = [c.corta for c in CRITERIOS if c.clave not in {x.clave for x in criterios}]
        if faltan:
            st.caption(
                f"No se ofrecen **{', '.join(faltan)}**: no hay datos de eso para este negocio, y un factor que no se "
                "puede medir no debe poder moverse."
            )
        del_panorama = [c.corta for c in criterios if c.columna.endswith("_mediana")]
        if del_panorama:
            st.caption(
                "**Población** es el censo; **mercado por segmento** es un proxy de OpenStreetMap que mide otra cosa, "
                f"así que van por separado. {', '.join(del_panorama)} usan el perfil por defecto de la categoría: los "
                "ajustes del panorama de más abajo no los cambian."
            )
    return normalize_weights(crudos, criterios)


def build_contributions_table(out, criterios):
    """Qué aportó cada criterio al puntaje de cada zona. Con seis pesos, el número final solo es creíble si se puede
    abrir: cada columna es peso × valor normalizado, y la suma de la fila es el puntaje."""
    columnas = {f"aporte_{c.clave}": c.etiqueta for c in criterios if f"aporte_{c.clave}" in out}
    tabla = out[["score"] + list(columnas)].rename(columns={"score": "Puntaje", **columnas})
    tabla.index.name = "Zona"
    return tabla.reset_index()


def render_contributions(out, criterios):
    tabla = build_contributions_table(out, criterios)
    with st.expander("🔍 De dónde sale cada puntaje"):
        st.dataframe(
            tabla.style.format({c: "{:.3f}" for c in tabla.columns if c != "Zona"}),
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "Cada columna es **peso × valor normalizado (0-1)** de ese factor; la fila suma el puntaje. Un factor sin "
            "dato en una zona entra como neutral (0,5 × su peso), no como el peor caso."
        )


# Para los tres criterios de la base, el valor CRUDO también se enseña: son magnitudes que una persona reconoce
# (habitantes, locales, minutos). Los tres del panorama son índices medianos de celdas, que en bruto no dicen nada:
# de esos se enseña solo el 0-1 ya orientado.
CRUDAS = {
    "demanda": ("demanda", "Población"),
    "competencia": ("competencia", "Competencia (ajustada)"),
    "accesibilidad": ("tiempo_viaje_prom", "Tiempo de viaje prom. (min)"),
}


def build_results_table(out, criterios):
    """Tabla de resultados con el desglose: para los factores medidos directamente, el valor CRUDO (lo medido) y el
    NORMALIZADO 0-1 que entra en el puntaje; para los demás, el 0-1. Nunca solo el número final.

    Todas las columnas (0-1) están orientadas igual: «más alto = mejor para el negocio». Por eso la de competencia
    aparece invertida (1 = la zona con menos competencia) y la de accesibilidad también (1 = la de menor tiempo de
    viaje). Una zona sin dato en un factor queda en blanco («sin dato») y el puntaje la trata como neutral (0,5)."""
    columnas = {"zone_name": "Zona", "score": "Puntaje"}
    for criterio in criterios:
        if f"{criterio.clave}_norm" not in out:
            continue  # criterio sin datos: no se puntuó, no se enseña
        if criterio.clave == "competencia" and "competencia_cruda" in out:
            columnas["competencia_cruda"] = "Competencia (conteo real)"
        cruda = CRUDAS.get(criterio.clave)
        if cruda and cruda[0] in out:
            columnas[cruda[0]] = cruda[1]
        columnas[f"{criterio.clave}_norm"] = f"{criterio.corta} (0-1)"
    n = int(out["criterios_puntuados"].iloc[0]) if "criterios_puntuados" in out and len(out) else len(criterios)
    columnas["dimensiones_con_dato"] = f"Datos completos (de {n})"
    return out.reset_index()[list(columnas)].rename(columns=columnas)


def render_results_table(out, criterios):
    tabla = build_results_table(out, criterios)
    formato = {
        "Puntaje": "{:.3f}",
        "Población": "{:,.0f}",
        "Competencia (conteo real)": "{:,.0f}",
        "Competencia (ajustada)": "{:.1f}",
        "Tiempo de viaje prom. (min)": "{:.1f}",
    }
    formato.update({c: "{:.2f}" for c in tabla.columns if c.endswith("(0-1)")})
    st.dataframe(
        tabla.style.format({k: v for k, v in formato.items() if k in tabla.columns}, na_rep="sin dato"),
        width="stretch",
        hide_index=True,
    )
    puntuados = len([c for c in criterios if f"{c.clave}_norm" in out])
    st.caption(
        f"Las columnas (0-1) son los valores normalizados que entran en el puntaje; en las {puntuados}, "
        "**más alto = mejor para el negocio** (por eso la competencia y el tiempo de viaje van invertidos). "
        "Puntaje = suma ponderada de esas columnas con los pesos elegidos arriba; ábrelo en «de dónde sale cada "
        "puntaje» para ver cuánto puso cada factor."
    )


ZOOM_ISLA = 11.5  # las 7 zonas de un vistazo
ZOOM_ZONA = 13.5  # la zona recomendada con sus celdas distinguibles


def _traza_zonas(out, destacada: Optional[str], con_celdas: bool):
    """Las 7 zonas. Sin celdas llevan el color del puntaje (y su barra); con celdas la barra es de la lente, así que
    aquí el color solo distingue la recomendada de las demás: dos barras de color en un mapa no se leen."""
    comun = dict(
        lat=[LOCATIONS[z].latitude for z in out.index],
        lon=[LOCATIONS[z].longitude for z in out.index],
        mode="markers+text",
        text=list(out.index),
        textposition="top center",
        hovertext=[f"{z}<br>Puntaje: {s:.3f}" for z, s in zip(out.index, out["score"])],
        hoverinfo="text",
        name="zonas",
    )
    if not con_celdas:
        return go.Scattermapbox(
            marker=dict(
                size=22, color=out["score"], colorscale="RdYlGn", showscale=True, colorbar=dict(title="Puntaje")
            ),
            **comun,
        )
    colores = ["#1a7f37" if z == destacada else "#8a8a8a" for z in out.index]
    return go.Scattermapbox(marker=dict(size=16, color=colores, opacity=0.9), **comun)


def build_score_map(out, panorama=None, zona: Optional[str] = None, capa: Optional[str] = None, isla: bool = False):
    """Mapa de la recomendación. Con `panorama` y una `zona` conocida dibuja **las celdas de esa zona** coloreadas por
    la lente `capa`, las celdas marcadas en la tabla como su cuadrado de 250 m, y las zonas como contexto. Sin panorama
    es el mapa de zonas de siempre."""
    con_celdas = panorama is not None and zona in LOCATIONS and capa is not None
    fig = go.Figure()
    centro = dict(
        lat=sum(loc.latitude for loc in LOCATIONS.values()) / len(LOCATIONS),
        lon=sum(loc.longitude for loc in LOCATIONS.values()) / len(LOCATIONS),
    )
    zoom = ZOOM_ISLA
    if con_celdas:
        celdas = panorama.vista[pv.zone_cells(panorama.vista, zona)]
        valores, titulo = pv.layer_values(celdas, capa)
        con, sin = celdas[valores.notna()], celdas[valores.isna()]
        if len(sin):  # sin dato no es lo mismo que valor bajo: se dibujan en gris, no se omiten en silencio
            fig.add_trace(
                go.Scattermapbox(
                    lat=sin["lat"],
                    lon=sin["lon"],
                    mode="markers",
                    marker=dict(size=9, color="#bbbbbb"),
                    hovertext=[
                        f"{i} · {html.escape(pv.place_label(r))}<br>sin datos"
                        for i, (_, r) in zip(sin.index, sin.iterrows())
                    ],
                    hoverinfo="text",
                    name="sin datos",
                )
            )
        fig.add_trace(
            go.Scattermapbox(
                lat=con["lat"],
                lon=con["lon"],
                mode="markers",
                marker=dict(
                    size=13,
                    color=valores[con.index],
                    colorscale="YlOrRd",
                    showscale=True,
                    colorbar=dict(title=titulo),
                    opacity=0.9,
                ),
                hovertext=[
                    f"{i} · {html.escape(pv.place_label(r))}<br>{titulo}: {v:.2f}<br>Confianza: {r['confianza_nivel']}"
                    for i, (_, r), v in zip(con.index, con.iterrows(), valores[con.index])
                ],
                hoverinfo="text",
                name=titulo,
            )
        )
        for cell_id in [c for c in panorama.marcadas if c in celdas.index]:
            lat_sq, lon_sq = ps.cuadrado_celda(cell_id)
            fig.add_trace(
                go.Scattermapbox(
                    lat=lat_sq,
                    lon=lon_sq,
                    mode="lines",
                    fill="toself",
                    fillcolor="rgba(31,119,180,0.25)",
                    line=dict(width=3, color="#1f77b4"),
                    name="celda marcada",
                    hoverinfo="skip",
                )
            )
        if not isla:
            centro, zoom = dict(lat=LOCATIONS[zona].latitude, lon=LOCATIONS[zona].longitude), ZOOM_ZONA
    fig.add_trace(_traza_zonas(out, zona, con_celdas))
    fig.update_layout(
        mapbox=dict(style="open-street-map", center=centro, zoom=zoom),
        height=520,
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
    )
    return fig


def capa_por_defecto(capas) -> int:
    """El mercado primero: es lo que se busca al abrir un negocio. Las demás lentes quedan a un clic."""
    for i, capa in enumerate(capas):
        if capa.startswith("Mercado"):
            return i
    return 0


def capas_del_mapa(vista) -> list:
    """Las lentes que puede mostrar este mapa. La brecha de oferta se queda fuera a propósito: no está validada y este
    es el mapa con el que se decide; vive en el panorama de abajo, con su advertencia."""
    return [c for c in pv.available_layers(vista) if c != pv.CAPA_BRECHA]


def render_score_map(out, panorama=None, zona: Optional[str] = None, categoria: str = ""):
    """Dibuja el mapa. Con panorama ofrece además con qué lente colorear las celdas y si alejarse a toda la isla."""
    capas = capas_del_mapa(panorama.vista) if panorama is not None else []
    if panorama is None or zona not in LOCATIONS or not capas:
        st.plotly_chart(build_score_map(out), width="stretch")
        st.caption(f"Las {len(out)} zonas que estás comparando, coloreadas por su puntaje.")
        return
    c1, c2 = st.columns([3, 1])
    # Las claves llevan la categoría, como el resto de controles: buscar otro negocio no debe arrastrar la lente elegida.
    capa = c1.radio(
        "Color de las celdas",
        capas,
        index=capa_por_defecto(capas),
        horizontal=True,
        key=f"reco_capa_celdas_{categoria}",
    )
    isla = c2.toggle("Ver toda la isla", value=False, key=f"reco_mapa_isla_{categoria}")
    st.plotly_chart(build_score_map(out, panorama, zona, capa, isla), width="stretch")
    valores, _ = pv.layer_values(panorama.vista[pv.zone_cells(panorama.vista, zona)], capa)
    n, sin_dato = int(valores.notna().sum()), int(valores.isna().sum())
    st.caption(
        f"Los puntos de color son las **{n} celdas de 250 m** de {zona} (a {pv.RADIO_ZONA_M:.0f} m o menos de su centro) "
        f"con dato de **{capa.split(' (')[0].lower()}**; pasa el ratón para ver su calle."
        + (f" Otras {sin_dato} no tienen dato de esta lente y van en gris." if sin_dato else "")
        + f" Los círculos con nombre son las {len(out)} zonas que comparas: el verde es la recomendada. **El color de "
        "las celdas es una lente, "
        "no el puntaje de la zona** — ese puntaje no existe por celda, porque la población y el tiempo de viaje se miden "
        "por zona. Las celdas que marques en la tabla de arriba se dibujan aquí con su cuadrado de 250 m."
    )


def main():
    st.title("🎯 ¿Dónde conviene abrir el negocio?")
    st.caption(
        "Sistema de apoyo a la decisión, no una predicción de machine learning: no existen datos "
        "históricos de resultados de negocio (ventas, cierres) con los que entrenar un modelo. "
        "Combina demanda, competencia y accesibilidad con criterios explícitos y visibles. "
        "Solo el texto que escribes se interpreta con ayuda de un clasificador entrenado, cuando las palabras clave no "
        "reconocen el negocio; siempre puedes corregir la categoría."
    )

    db = get_database()
    texto = st.text_input(
        "Describe el negocio que quieres abrir",
        placeholder="Ej.: una pizzería, un gimnasio, una farmacia, una tienda de ropa...",
    )
    zonas = render_zone_filter()
    # Qué criterios se pueden puntuar depende de la CATEGORÍA, que no se conoce hasta interpretar el texto: se reserva
    # el sitio de los ajustes y se rellenan más abajo, ya con la categoría decidida.
    destino_ajustes = st.container()
    buscar = st.button("🔍 Buscar mejor ubicación", type="primary")

    def ajustes(cat: str):
        with destino_ajustes:
            return render_weight_controls(_criterios(db, cat))

    # Los resultados persisten al tocar los controles del panorama por celda (cada cambio vuelve a ejecutar la página y
    # `buscar` sería False): se recuerda el texto con que se buscó, y solo cambia al volver a pulsar el botón.
    if buscar:
        if not texto or not texto.strip():
            st.session_state.pop("reco_texto", None)
            st.warning("Escribe una descripción del negocio primero.")
            ajustes(CATEGORIA_INICIAL)
            return
        st.session_state["reco_texto"] = texto.strip()
    texto = st.session_state.get("reco_texto")
    if not texto:
        ajustes(CATEGORIA_INICIAL)
        return

    interpretacion = interpretar(texto, get_text_model())
    if interpretacion.categoria is None:
        st.error(
            f"No pude identificar el tipo de negocio en: '{texto}'. "
            "Prueba con una descripción más específica (ej. 'restaurante', 'farmacia', 'gimnasio')."
        )
        st.info(
            "Prueba con palabras más concretas: restaurante, farmacia, gimnasio, escuela, centro comercial, tienda de ropa..."
        )
        ajustes(CATEGORIA_INICIAL)
        return

    categoria = render_interpretacion(texto, interpretacion)
    criterios = _criterios(db, categoria)
    weights = ajustes(categoria)
    # Se puntúan SIEMPRE las 7 zonas y después se filtran: así el puntaje de cada una sigue midiendo su posición entre
    # todas, y elegir zonas solo quita filas en vez de cambiar las notas de las que quedan.
    todas = _cached_recommend(db, categoria, tuple(sorted(weights.items())))
    out = filter_zones(todas, zonas)

    top_zone = out.index[0]
    st.metric("🏆 Zona recomendada", top_zone, f"puntaje {out['score'].iloc[0]:.3f}")
    if len(out) < len(todas):
        st.caption(
            f"Comparando **{len(out)} de {len(todas)} zonas**, las que elegiste arriba. El puntaje de cada una no "
            "cambia por filtrar: sigue midiendo su posición entre las 7."
        )
    # Se reservan aquí, bajo la zona recomendada y bajo el desglose, los sitios de lo que calcula el panorama por celda
    # (que depende del perfil, cuyos controles están más abajo): se rellenan al llegar a esa sección.
    destino_celdas = st.container()
    # El mapa muestra las celdas de la zona, que dependen del perfil cuyos controles están más abajo: se reserva el sitio
    # y se dibuja al final, cuando el panorama ya se calculó.
    destino_mapa = st.container()

    st.markdown("#### Desglose por zona")
    render_results_table(out, criterios)
    render_contributions(out, criterios)
    destino_zonas = st.container()

    if categoria == "food_drink":
        st.caption(
            "⚠️ La competencia de restauración está corregida (Overpass ve ~61% de lo real, "
            "medido contra Foursquare en la zona menos densa) — es una estimación, no un conteo directo."
        )
    puntuados = int(out["criterios_puntuados"].iloc[0])
    if (out["dimensiones_con_dato"] < puntuados).any():
        st.caption(f"⚠️ Alguna zona no tenía dato completo en uno de los {puntuados} factores y se trató como neutral.")
    st.caption(
        "Nota: Msida, Gzira, Sliema y St Julian's están a menos de 1.500 m entre sí — "
        "sus conteos de competencia se solapan de forma natural, no es un error."
    )
    panorama = render_panorama_section(
        categoria, zona=top_zone, destino_celdas=destino_celdas, destino_zonas=destino_zonas
    )
    with destino_mapa:
        render_score_map(out, panorama, top_zone, categoria)


if __name__ == "__main__":
    main()
