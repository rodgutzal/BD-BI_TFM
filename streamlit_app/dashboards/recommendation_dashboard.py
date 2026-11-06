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
from src.location_scoring import recommend_locations, DEFAULT_WEIGHTS
from src.locations import LOCATIONS
from streamlit_app.dashboards.maps_dashboard import POI_CATEGORY_STYLE

_CACHE_TTL = 60


@st.cache_resource
def get_database():
    DB_PATH = ROOT_DIR / "data" / "mobility.db"
    CSV_PATH = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"
    return RouteDatabase(CSV_PATH, DB_PATH)


@st.cache_data(ttl=_CACHE_TTL, show_spinner="Calculando puntajes por zona...")
def _cached_recommend(_db, texto: str, w_demanda: float, w_competencia: float, w_accesibilidad: float):
    """Envuelve recommend_locations() para que Streamlit lo cachee por
    separado según el texto y los pesos. Los pesos van como 3 floats sueltos
    (no un dict): un dict no sirve como parte de la clave de caché de
    @st.cache_data de forma confiable."""
    weights = {"demanda": w_demanda, "competencia": w_competencia, "accesibilidad": w_accesibilidad}
    return recommend_locations(_db, texto, weights=weights)


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


def render_results_table(out):
    tabla = out.reset_index()[[
        "zone_name", "score", "demanda", "competencia_cruda", "competencia",
        "tiempo_viaje_prom", "dimensiones_con_dato",
    ]].rename(columns={
        "zone_name": "Zona", "score": "Puntaje", "demanda": "Población",
        "competencia_cruda": "Competencia (conteo real)", "competencia": "Competencia (ajustada)",
        "tiempo_viaje_prom": "Tiempo de viaje prom. (min)", "dimensiones_con_dato": "Datos completos (de 3)",
    })
    st.dataframe(
        tabla.style.format({
            "Puntaje": "{:.3f}", "Población": "{:,.0f}", "Competencia (ajustada)": "{:.1f}",
            "Tiempo de viaje prom. (min)": "{:.1f}",
        }, na_rep="sin dato"),
        width="stretch", hide_index=True,
    )


def render_score_map(out):
    fig = go.Figure(go.Scattermapbox(
        lat=[LOCATIONS[z].latitude for z in out.index],
        lon=[LOCATIONS[z].longitude for z in out.index],
        mode="markers+text",
        marker=dict(size=22, color=out["score"], colorscale="RdYlGn", showscale=True,
                    colorbar=dict(title="Puntaje")),
        text=list(out.index),
        textposition="top center",
        hovertext=[f"{z}<br>Puntaje: {s:.3f}" for z, s in zip(out.index, out["score"])],
        hoverinfo="text",
    ))
    center_lat = sum(loc.latitude for loc in LOCATIONS.values()) / len(LOCATIONS)
    center_lon = sum(loc.longitude for loc in LOCATIONS.values()) / len(LOCATIONS)
    fig.update_layout(
        mapbox=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=11.5),
        height=500, margin=dict(l=0, r=0, t=0, b=0),
    )
    st.plotly_chart(fig, width="stretch")


def main():
    st.title("🎯 ¿Dónde conviene abrir el negocio?")
    st.caption(
        "Sistema de apoyo a la decisión, no una predicción de machine learning: no existen datos "
        "históricos de resultados de negocio (ventas, cierres) con los que entrenar un modelo. "
        "Combina demanda, competencia y accesibilidad con criterios explícitos y visibles."
    )

    db = get_database()
    texto = st.text_input(
        "Describe el negocio que quieres abrir",
        placeholder="Ej.: una pizzería, un gimnasio, una farmacia, una tienda de ropa...",
    )
    weights = render_weight_controls()
    buscar = st.button("🔍 Buscar mejor ubicación", type="primary")

    if not buscar:
        return
    if not texto or not texto.strip():
        st.warning("Escribe una descripción del negocio primero.")
        return

    try:
        out = _cached_recommend(db, texto.strip(), weights["demanda"], weights["competencia"], weights["accesibilidad"])
    except ValueError as e:
        st.error(str(e))
        st.info("Prueba con palabras más concretas: restaurante, farmacia, gimnasio, escuela, centro comercial, tienda de ropa...")
        return

    categoria = out["categoria"].iloc[0]
    st.success(f"Interpretado como: **{POI_CATEGORY_STYLE.get(categoria, {}).get('label', categoria)}**")

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


if __name__ == "__main__":
    main()
