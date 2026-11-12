"""Maps dashboard: visualización geográfica de las rutas monitorizadas."""

import logging
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase
from src.locations import LOCATIONS, ROUTES
from streamlit_app.dashboards.aislado import render_aislado

logger = logging.getLogger(__name__)

_CACHE_TTL = 60


@st.cache_resource
def get_database():
    DB_PATH = ROOT_DIR / "data" / "mobility.db"
    CSV_PATH = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"
    return RouteDatabase(CSV_PATH, DB_PATH)


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_all_routes_statistics(_db, hours: int = 1):
    """Ver nota equivalente en operations_dashboard.py — mismo fix, mismo
    método reusado. render_route_map y render_route_status_table hacían,
    cada una por su cuenta, `for origin, destination in selected_routes:
    db.get_route_statistics(...)` (una consulta por ruta, x2 funciones)."""
    return _db.get_all_routes_statistics(hours=hours)


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_pois(_db, categories: tuple):
    """`categories` como tupla (no lista) para que sea hasheable y sirva de
    clave de caché. FIX: render_poi_layer() y main() llamaban a
    db.get_pois(categories=...) por separado con los mismos argumentos —
    con esto, la segunda llamada reusa el resultado cacheado de la primera."""
    return _db.get_pois(categories=list(categories))


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_pois_foursquare(_db, categories: tuple):
    """Equivalente a _fetch_pois pero contra pois_foursquare (tabla
    separada — ver nota en database.py). Solo tiene datos si se corrió
    `docker compose --profile foursquare up -d poi-collector-foursquare`
    con FOURSQUARE_API_KEY configurada."""
    return _db.get_pois_foursquare(categories=list(categories))


# Categorías de infraestructura vía Overpass API (OpenStreetMap) — sin API
# key, siempre disponibles si se corrió poi-collector.
POI_CATEGORY_STYLE = {
    "school": {"color": "#3498db", "label": "🎓 Escuelas"},
    "hospital": {"color": "#e74c3c", "label": "🏥 Salud"},
    "mall": {"color": "#9b59b6", "label": "🛍️ Centros comerciales"},
    "business": {"color": "#f39c12", "label": "🏢 Comercios y oficinas"},
    "food_drink": {"color": "#d35400", "label": "🍽️ Restauración y bares"},
    "leisure": {"color": "#c2185b", "label": "🎭 Ocio y cultura"},
    "sport": {"color": "#27ae60", "label": "🏋️ Deporte"},
}

# Categorías de Overpass marcadas por defecto. Las tres más nuevas
# (food_drink/leisure/sport) suman miles de puntos: se ofrecen en el
# selector pero arrancan apagadas, para no cambiar en silencio lo que se ve
# ni recargar el mapa sin que el usuario lo pida.
OVERPASS_DEFAULT_CATEGORIES = ["school", "hospital", "mall", "business"]

# Categorías de negocio vía Foursquare Places API — COMPLEMENTARIAS a las de
# arriba (misma idea: refinan "business"), opcionales, requieren
# FOURSQUARE_API_KEY. Se muestran TODAS las que devuelva Foursquare, sin
# excluir nada — incluye baldes que se solapan a propósito con los de
# Overpass (school/health/mall), para poder comparar cobertura entre
# fuentes si se quiere.
POI_CATEGORY_STYLE_FOURSQUARE = {
    "restaurant": {"color": "#d35400", "label": "🍽️ Restaurantes"},
    "retail": {"color": "#16a085", "label": "🛒 Retail"},
    "services": {"color": "#2c3e50", "label": "💼 Servicios"},
    "entertainment": {"color": "#c2185b", "label": "🎭 Entretenimiento"},
    "school": {"color": "#3498db", "label": "🎓 Escuelas"},
    "health": {"color": "#e74c3c", "label": "🏥 Salud"},
    "mall": {"color": "#9b59b6", "label": "🛍️ Centros comerciales"},
    "other": {"color": "#7f8c8d", "label": "📌 Otros"},
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

    stats_df = _fetch_all_routes_statistics(db, hours=1)
    stats_by_route = {(row["origin"], row["destination"]): row for _, row in stats_df.iterrows()}

    for origin, destination in selected_routes:
        if origin not in LOCATIONS or destination not in LOCATIONS:
            continue
        o = LOCATIONS[origin]
        d = LOCATIONS[destination]

        row = stats_by_route.get((origin, destination))
        delay = row["avg_delay"] if row is not None else None
        travel_time = row["avg_travel_time"] if row is not None else None
        color = _delay_color(delay)
        delay_txt = f"{delay:.1f} min" if delay is not None and not pd.isna(delay) else "sin dato"
        time_txt = f"{travel_time:.1f} min" if travel_time is not None and not pd.isna(travel_time) else "sin dato"

        fig.add_trace(
            go.Scattermapbox(
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
            )
        )

    location_names = list(LOCATIONS.keys())
    fig.add_trace(
        go.Scattermapbox(
            mode="markers+text",
            lon=[LOCATIONS[n].longitude for n in location_names],
            lat=[LOCATIONS[n].latitude for n in location_names],
            marker=dict(size=13, color="#2c3e50"),
            text=location_names,
            textposition="top right",
            name="Ubicaciones",
            showlegend=False,
            hoverinfo="text",
        )
    )

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


def render_poi_layer(fig, db, selected_categories, source):
    """Añade una capa de marcadores de infraestructura (una traza por
    categoría, para que cada una aparezca como entrada independiente en la
    leyenda y se pueda ocultar/mostrar con un clic).

    `source` ("overpass" o "foursquare") decide de qué tabla se lee, de forma
    EXPLÍCITA. Antes la fuente se deducía del nombre de la categoría, pero
    `school` y `mall` existen en los dos catálogos: al elegir una fuente
    también se dibujaban esas dos categorías de la otra, y el selector "una
    fuente u otra" no aislaba del todo."""
    if not selected_categories or source not in ("overpass", "foursquare"):
        return

    categories = tuple(sorted(selected_categories))
    if source == "overpass":
        pois_df = _fetch_pois(db, categories)
        styles = POI_CATEGORY_STYLE
    else:
        pois_df = _fetch_pois_foursquare(db, categories)
        styles = POI_CATEGORY_STYLE_FOURSQUARE

    if pois_df.empty:
        return

    for category, group in pois_df.groupby("category"):
        style = styles.get(category, {"color": "#7f8c8d", "label": category})
        fig.add_trace(
            go.Scattermapbox(
                mode="markers",
                lon=group["longitude"],
                lat=group["latitude"],
                marker=dict(size=8, color=style["color"], opacity=0.85),
                name=style["label"],
                text=group["name"],
                hovertemplate=f"<b>%{{text}}</b><br>{style['label']}<extra></extra>",
            )
        )


def render_route_status_table(db, selected_routes):
    """Tabla con el estado actual (última hora) de las rutas seleccionadas."""
    stats_df = _fetch_all_routes_statistics(db, hours=1)
    stats_by_route = {(row["origin"], row["destination"]): row for _, row in stats_df.iterrows()}

    rows = []
    for origin, destination in selected_routes:
        row_stats = stats_by_route.get((origin, destination))
        delay = row_stats["avg_delay"] if row_stats is not None else None
        travel_time = row_stats["avg_travel_time"] if row_stats is not None else None

        if delay is None or pd.isna(delay):
            status = "⚪ Sin dato"
        elif delay <= 1:
            status = "🟢 Flujo libre"
        elif delay <= 4:
            status = "🟡 Moderado"
        else:
            status = "🔴 Denso"

        rows.append(
            {
                "Ruta": f"{origin} → {destination}",
                "Estado": status,
                "Tiempo de viaje (1h)": (
                    f"{travel_time:.1f} min" if travel_time is not None and not pd.isna(travel_time) else "Sin dato"
                ),
                "Retraso (1h)": f"{delay:.1f} min" if delay is not None and not pd.isna(delay) else "Sin dato",
            }
        )

    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("Selecciona al menos una ruta para ver su estado.")


def render_map_section(db, selected_routes, poi_labels, poi_source_key):
    """El mapa de rutas con la capa de infraestructura elegida y su leyenda de colores.

    La capa de POIs es opcional: si falla, el mapa de rutas se dibuja igualmente, sin ella, y se avisa. Se aplica a una
    copia de la figura para que una capa a medias no quede mezclada con el mapa."""
    fig = render_route_map(db, selected_routes)
    capa = go.Figure(fig)
    capa_fallida = None
    try:
        render_poi_layer(capa, db, poi_labels, poi_source_key)
        fig = capa
    except Exception as e:
        logger.exception("Falló la capa de infraestructura del mapa de Maps")
        capa_fallida = e
    st.plotly_chart(fig, width="stretch")
    if capa_fallida is not None:
        st.warning(
            "No se pudo dibujar la capa de infraestructura; el mapa de rutas se muestra sin ella. "
            f"({type(capa_fallida).__name__}: {capa_fallida})"
        )

    st.caption(
        "🟢 Flujo libre (≤1 min de retraso) · 🟡 Moderado (1-4 min) · "
        "🔴 Denso (>4 min) · ⚪ Sin datos en la última hora"
    )


def render_poi_summary(db, poi_source, poi_labels):
    """Cuántos elementos de la fuente elegida hay y cuándo se actualizaron (o cómo cargarlos si no hay)."""
    if poi_source == "Overpass (OSM)" and poi_labels:
        pois_df = _fetch_pois(db, tuple(sorted(poi_labels)))
        if pois_df.empty:
            st.info(
                "No hay datos de infraestructura (Overpass) todavía. Ejecuta "
                "`python -m src.poi_extraction` para cargarlos (no requiere API key)."
            )
        else:
            last_update = pd.to_datetime(pois_df["updated_at"]).max()
            st.caption(
                f"📍 {len(pois_df)} elementos de Overpass · "
                f"Última actualización: {last_update.strftime('%Y-%m-%d %H:%M UTC')} "
                "(se refresca automáticamente cada semana vía `src/poi_extraction.py`)"
            )

    elif poi_source == "Foursquare" and poi_labels:
        pois_fsq_df = _fetch_pois_foursquare(db, tuple(sorted(poi_labels)))
        if pois_fsq_df.empty:
            st.info(
                "No hay datos de Foursquare todavía. Requiere `FOURSQUARE_API_KEY` en `.env` "
                "y correr el servicio opcional: "
                "`docker compose --profile foursquare up -d poi-collector-foursquare` "
                "(o `python -m src.poi_extraction_foursquare` fuera de Docker)."
            )
        else:
            last_update_fsq = pd.to_datetime(pois_fsq_df["updated_at"]).max()
            st.caption(
                f"🍽️ {len(pois_fsq_df)} POIs de Foursquare (todas las categorías, sin filtrar) · "
                f"Última actualización: {last_update_fsq.strftime('%Y-%m-%d %H:%M UTC')}"
            )


def _aislar(nombre: str, render) -> None:
    """Ejecuta una sección de Maps; si falla, el error queda en su sitio y las demás secciones siguen."""
    render_aislado(nombre, render, logger, ambito="Maps")


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
        poi_source = st.radio(
            "Fuente de infraestructura",
            ["Ninguna", "Overpass (OSM)", "Foursquare"],
            horizontal=True,
        )

        if poi_source == "Overpass (OSM)":
            poi_labels = st.multiselect(
                "Categorías a mostrar",
                list(POI_CATEGORY_STYLE.keys()),
                default=OVERPASS_DEFAULT_CATEGORIES,
                format_func=lambda c: POI_CATEGORY_STYLE[c]["label"],
            )
        elif poi_source == "Foursquare":
            poi_labels = st.multiselect(
                "Categorías a mostrar",
                list(POI_CATEGORY_STYLE_FOURSQUARE.keys()),
                default=list(POI_CATEGORY_STYLE_FOURSQUARE.keys()),
                format_func=lambda c: POI_CATEGORY_STYLE_FOURSQUARE[c]["label"],
            )
        else:
            poi_labels = []

    poi_source_key = {"Overpass (OSM)": "overpass", "Foursquare": "foursquare"}.get(poi_source)

    # Cada sección va aislada: si una falla (una consulta, el mapa), las demás se siguen viendo.
    _aislar("Mapa de rutas", lambda: render_map_section(db, selected_routes, poi_labels, poi_source_key))
    _aislar("Resumen de infraestructura", lambda: render_poi_summary(db, poi_source, poi_labels))

    st.divider()

    st.subheader("📊 Estado actual por ruta")
    _aislar("Estado actual por ruta", lambda: render_route_status_table(db, selected_routes))


if __name__ == "__main__":
    main()
