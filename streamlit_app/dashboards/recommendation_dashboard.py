"""Dashboard de recomendación de ubicación: ¿dónde conviene abrir un negocio?

Interfaz para el sistema de apoyo a la decisión de src/location_scoring.py —
ver ahí el porqué del método (MCDA, no machine learning) y el detalle de
cada dimensión.
"""

import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase
from src.location_scoring import DEFAULT_WEIGHTS, recommend_for_category
from src.locations import LOCATIONS
from src.ml.text_hibrido import CATEGORIAS, FUENTE_MODELO, Interpretacion, cargar_modelo_adoptado, interpretar
from streamlit_app.dashboards.maps_dashboard import POI_CATEGORY_STYLE
from streamlit_app.dashboards.panorama_section import render_panorama_section

_CACHE_TTL = 60


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


@st.cache_data(ttl=_CACHE_TTL, show_spinner="Calculando puntajes por zona...")
def _cached_recommend(_db, categoria: str, w_demanda: float, w_competencia: float, w_accesibilidad: float):
    """Envuelve recommend_for_category() para que Streamlit lo cachee por
    separado según la categoría y los pesos. Los pesos van como 3 floats sueltos
    (no un dict): un dict no sirve como parte de la clave de caché de
    @st.cache_data de forma confiable."""
    weights = {"demanda": w_demanda, "competencia": w_competencia, "accesibilidad": w_accesibilidad}
    return recommend_for_category(_db, categoria, weights=weights)


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


def normalize_weights(w_demanda: float, w_competencia: float, w_accesibilidad: float) -> dict:
    """Pesos relativos tal como vienen de los sliders (no hace falta que
    sumen 100) -> dict normalizado a 1.0, como exige score_zones(). Si los
    3 quedan en 0 (el usuario bajó todo), cae a los pesos por defecto en
    vez de dividir por cero."""
    total = w_demanda + w_competencia + w_accesibilidad
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {
        "demanda": w_demanda / total,
        "competencia": w_competencia / total,
        "accesibilidad": w_accesibilidad / total,
    }


def render_weight_controls() -> dict:
    with st.expander("⚙️ Ajustar qué tanto pesa cada factor"):
        st.caption("Importancia relativa de cada factor — no hace falta que sumen 100, se normalizan solos.")
        c1, c2, c3 = st.columns(3)
        w_demanda = c1.slider("Demanda (población)", 0, 100, int(DEFAULT_WEIGHTS["demanda"] * 100))
        w_competencia = c2.slider("Evitar competencia", 0, 100, int(DEFAULT_WEIGHTS["competencia"] * 100))
        w_accesibilidad = c3.slider("Accesibilidad", 0, 100, int(DEFAULT_WEIGHTS["accesibilidad"] * 100))
    return normalize_weights(w_demanda, w_competencia, w_accesibilidad)


def build_results_table(out):
    """Tabla de resultados con el desglose completo: para cada factor, el
    valor CRUDO (lo medido) y el valor NORMALIZADO 0-1 que entra en el
    puntaje. Nunca solo el número final.

    Las tres columnas normalizadas están todas orientadas igual: "más alto =
    mejor para el negocio". Por eso la de competencia aparece invertida
    (1 = la zona con menos competencia) y la de accesibilidad también (1 = la
    zona con menor tiempo de viaje). Una zona sin dato en un factor queda en
    blanco ("sin dato") y el puntaje la trata como neutral (0.5) en ese factor.
    """
    return out.reset_index()[
        [
            "zone_name",
            "score",
            "demanda",
            "demanda_norm",
            "competencia_cruda",
            "competencia",
            "competencia_norm",
            "tiempo_viaje_prom",
            "accesibilidad_norm",
            "dimensiones_con_dato",
        ]
    ].rename(
        columns={
            "zone_name": "Zona",
            "score": "Puntaje",
            "demanda": "Población",
            "demanda_norm": "Demanda (0-1)",
            "competencia_cruda": "Competencia (conteo real)",
            "competencia": "Competencia (ajustada)",
            "competencia_norm": "Baja competencia (0-1)",
            "tiempo_viaje_prom": "Tiempo de viaje prom. (min)",
            "accesibilidad_norm": "Accesibilidad (0-1)",
            "dimensiones_con_dato": "Datos completos (de 3)",
        }
    )


def render_results_table(out):
    tabla = build_results_table(out)
    st.dataframe(
        tabla.style.format(
            {
                "Puntaje": "{:.3f}",
                "Población": "{:,.0f}",
                "Competencia (ajustada)": "{:.1f}",
                "Tiempo de viaje prom. (min)": "{:.1f}",
                "Demanda (0-1)": "{:.2f}",
                "Baja competencia (0-1)": "{:.2f}",
                "Accesibilidad (0-1)": "{:.2f}",
            },
            na_rep="sin dato",
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Las columnas (0-1) son los valores normalizados que entran en el puntaje; en las tres, "
        "**más alto = mejor para el negocio** (por eso la competencia y el tiempo de viaje van invertidos). "
        "Puntaje = suma ponderada de las tres columnas (0-1) con los pesos elegidos arriba."
    )


def render_score_map(out):
    fig = go.Figure(
        go.Scattermapbox(
            lat=[LOCATIONS[z].latitude for z in out.index],
            lon=[LOCATIONS[z].longitude for z in out.index],
            mode="markers+text",
            marker=dict(
                size=22, color=out["score"], colorscale="RdYlGn", showscale=True, colorbar=dict(title="Puntaje")
            ),
            text=list(out.index),
            textposition="top center",
            hovertext=[f"{z}<br>Puntaje: {s:.3f}" for z, s in zip(out.index, out["score"])],
            hoverinfo="text",
        )
    )
    center_lat = sum(loc.latitude for loc in LOCATIONS.values()) / len(LOCATIONS)
    center_lon = sum(loc.longitude for loc in LOCATIONS.values()) / len(LOCATIONS)
    fig.update_layout(
        mapbox=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=11.5),
        height=500,
        margin=dict(l=0, r=0, t=0, b=0),
    )
    st.plotly_chart(fig, width="stretch")


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
    weights = render_weight_controls()
    buscar = st.button("🔍 Buscar mejor ubicación", type="primary")

    # Los resultados persisten al tocar los controles del panorama por celda (cada cambio vuelve a ejecutar la página y
    # `buscar` sería False): se recuerda el texto con que se buscó, y solo cambia al volver a pulsar el botón.
    if buscar:
        if not texto or not texto.strip():
            st.session_state.pop("reco_texto", None)
            st.warning("Escribe una descripción del negocio primero.")
            return
        st.session_state["reco_texto"] = texto.strip()
    texto = st.session_state.get("reco_texto")
    if not texto:
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
        return

    categoria = render_interpretacion(texto, interpretacion)
    out = _cached_recommend(db, categoria, weights["demanda"], weights["competencia"], weights["accesibilidad"])

    top_zone = out.index[0]
    st.metric("🏆 Zona recomendada", top_zone, f"puntaje {out['score'].iloc[0]:.3f}")

    render_score_map(out)
    st.markdown("#### Desglose por zona")
    render_results_table(out)

    if categoria == "food_drink":
        st.caption(
            "⚠️ La competencia de restauración está corregida (Overpass ve ~61% de lo real, "
            "medido contra Foursquare en la zona menos densa) — es una estimación, no un conteo directo."
        )
    if (out["dimensiones_con_dato"] < 3).any():
        st.caption("⚠️ Alguna zona no tenía dato completo en una de las 3 dimensiones y se trató como neutral.")
    st.caption(
        "Nota: Msida, Gzira, Sliema y St Julian's están a menos de 1.500 m entre sí — "
        "sus conteos de competencia se solapan de forma natural, no es un error."
    )
    render_panorama_section(categoria)


if __name__ == "__main__":
    main()
