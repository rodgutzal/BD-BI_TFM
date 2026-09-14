"""Maps dashboard: visualización geográfica de las rutas monitorizadas."""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase
from src.locations import LOCATIONS, ROUTES


@st.cache_resource
def get_database():
    DB_PATH = ROOT_DIR / "data" / "mobility.db"
    CSV_PATH = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"
    return RouteDatabase(CSV_PATH, DB_PATH)


POI_CATEGORY_STYLE = {
    "school": {"color": "#3498db", "label": "🎓 Escuelas"},
    "hospital": {"color": "#e74c3c", "label": "🏥 Salud"},
    "mall": {"color": "#9b59b6", "label": "🛍️ Centros comerciales"},
    "business": {"color": "#f39c12", "label": "🏢 Negocios"},
}


def _delay_color(delay) -> str:
    """Colorea la ruta según el retraso medio (última hora)."""
    if delay is None or pd.isna(delay):
        return "#95a5a6"  # gris: sin dato reciente
    if delay <= 1:
        return "#2ecc71"  # verde: flujo libre
    if delay <= 4:
        return "#f1c40f"  # amarillo: moderado
    return "#e74c3c"  # rojo: denso


def render_route_map(db, selected_routes):
    """Construye la figura con las ubicaciones y las rutas coloreadas por su
    estado actual. No dibuja el gráfico — devuelve el `Figure` para que el
    caller pueda añadir capas adicionales (ej. POIs) antes de renderizarlo."""
    fig = go.Figure()

    for origin, destination in selected_routes:
        if origin not in LOCATIONS or destination not in LOCATIONS:
            continue
        o = LOCATIONS[origin]
        d = LOCATIONS[destination]

        stats = db.get_route_statistics(origin, destination, hours=1)
        delay = stats.get("avg_delay")
        travel_time = stats.get("avg_travel_time")
        color = _delay_color(delay)
        delay_txt = f"{delay:.1f} min" if delay is not None else "sin dato"
        time_txt = f"{travel_time:.1f} min" if travel_time is not None else "sin dato"

        fig.add_trace(go.Scattermapbox(
            mode="lines",
            lon=[o.longitude, d.longitude],
            lat=[o.latitude, d.latitude],
            line=dict(width=4, color=color),
            name=f"{origin} → {destination}",
            showlegend=False,
            hovertemplate=(
                f"<b>{origin} → {destination}</b><br>"
                f"Tiempo de viaje (1h): {time_txt}<br>"
                f"Retraso (1h): {delay_txt}<extra></extra>"
            ),
        ))

    location_names = list(LOCATIONS.keys())
    fig.add_trace(go.Scattermapbox(
        mode="markers+text",
        lon=[LOCATIONS[n].longitude for n in location_names],
        lat=[LOCATIONS[n].latitude for n in location_names],
        marker=dict(size=13, color="#2c3e50"),
        text=location_names,
        textposition="top right",
        name="Ubicaciones",
        showlegend=False,
        hoverinfo="text",
    ))

    center_lat = sum(loc.latitude for loc in LOCATIONS.values()) / len(LOCATIONS)
    center_lon = sum(loc.longitude for loc in LOCATIONS.values()) / len(LOCATIONS)

    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=center_lat, lon=center_lon),
            zoom=11.5,
        ),
        height=600,
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(bgcolor="rgba(255,255,255,0.8)"),
    )

    return fig


def render_poi_layer(fig, db, selected_categories):
    """Añade una capa de marcadores de infraestructura (una traza por
    categoría, para que cada una aparezca como entrada independiente en la
    leyenda y se pueda ocultar/mostrar con un clic)."""
    if not selected_categories:
        return

    pois_df = db.get_pois(categories=selected_categories)
    if pois_df.empty:
        return

    for category, group in pois_df.groupby("category"):
        style = POI_CATEGORY_STYLE.get(category, {"color": "#7f8c8d", "label": category})
        fig.add_trace(go.Scattermapbox(
            mode="markers",
            lon=group["longitude"],
            lat=group["latitude"],
            marker=dict(size=8, color=style["color"], opacity=0.85),
            name=style["label"],
            text=group["name"],
            hovertemplate=f"<b>%{{text}}</b><br>{style['label']}<extra></extra>",
        ))


def render_route_status_table(db, selected_routes):
    """Tabla con el estado actual (última hora) de las rutas seleccionadas."""
    rows = []
    for origin, destination in selected_routes:
        stats = db.get_route_statistics(origin, destination, hours=1)
        delay = stats.get("avg_delay")
        travel_time = stats.get("avg_travel_time")

        if delay is None:
            status = "⚪ Sin dato"
        elif delay <= 1:
            status = "🟢 Flujo libre"
        elif delay <= 4:
            status = "🟡 Moderado"
        else:
            status = "🔴 Denso"

        rows.append({
            "Ruta": f"{origin} → {destination}",
            "Estado": status,
            "Tiempo de viaje (1h)": f"{travel_time:.1f} min" if travel_time is not None else "Sin dato",
            "Retraso (1h)": f"{delay:.1f} min" if delay is not None else "Sin dato",
        })

    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("Selecciona al menos una ruta para ver su estado.")


def main():
    """Maps dashboard main function."""
    st.set_page_config(page_title="Maps Dashboard", layout="wide")

    st.markdown("# 🗺️ Mapa de Rutas")
    st.markdown("Visualización geográfica de las rutas monitorizadas y su estado de tráfico actual")

    db = get_database()

    col1, col2 = st.columns(2)
    with col1:
        route_labels = [f"{origin} → {destination}" for origin, destination in ROUTES]
        selected_labels = st.multiselect(
            "Rutas a mostrar",
            route_labels,
            default=route_labels,
        )
        selected_routes = [ROUTES[route_labels.index(label)] for label in selected_labels]

    with col2:
        poi_labels = st.multiselect(
            "Infraestructura a mostrar",
            list(POI_CATEGORY_STYLE.keys()),
            default=[],
            format_func=lambda c: POI_CATEGORY_STYLE[c]["label"],
        )

    fig = render_route_map(db, selected_routes)
    render_poi_layer(fig, db, poi_labels)
    st.plotly_chart(fig, width="stretch")

    st.caption(
        "🟢 Flujo libre (≤1 min de retraso) · 🟡 Moderado (1-4 min) · "
        "🔴 Denso (>4 min) · ⚪ Sin datos en la última hora"
    )

    if poi_labels:
        pois_df = db.get_pois(categories=poi_labels)
        if pois_df.empty:
            st.info(
                "No hay datos de infraestructura todavía. Ejecuta "
                "`python -m src.poi_extraction` para cargarlos desde Overpass API "
                "(no requiere API key)."
            )
        else:
            last_update = pd.to_datetime(pois_df["updated_at"]).max()
            st.caption(
                f"📍 {len(pois_df)} elementos de infraestructura · "
                f"Última actualización: {last_update.strftime('%Y-%m-%d %H:%M UTC')} "
                "(se refresca automáticamente cada semana vía `src/poi_extraction.py`)"
            )

    st.divider()

    st.subheader("📊 Estado actual por ruta")
    render_route_status_table(db, selected_routes)


if __name__ == "__main__":
    main()
