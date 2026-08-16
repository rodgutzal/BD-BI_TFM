"""Professional Streamlit dashboard for Urban Mobility Analytics.

BD_BI_TFM2: NO es el entrypoint activo (streamlit_app/app.py es ahora
app_multi_dashboard.py, con las vistas Executive/Operations/Analyst). Este
archivo se conserva en legacy_reference/ como referencia — la vista de
ruta única con mapa, comparación de clima origen/destino y exportación
sigue siendo funcional si se quiere correr por separado:

    streamlit run streamlit_app/legacy_reference/app_advanced.py
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analytics import MobilityAnalytics
from src.database import RouteDatabase
from src.locations import LOCATIONS
from streamlit_app.legacy_reference.components import (
    render_alerts,
    render_export_buttons,
    render_header,
    render_historical_table,
    render_map,
    render_metric_cards,
    render_sidebar_filters,
    render_traffic_status,
)
from streamlit_app.legacy_reference.charts import (
    create_travel_time_chart,
    create_traffic_delay_chart,
    create_speed_chart,
    create_temperature_chart,
    create_humidity_chart,
)

DB_PATH = ROOT_DIR / "data" / "mobility.db"
CSV_PATH = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"


@st.cache_resource
def get_database():
    """Cache database connection."""
    return RouteDatabase(CSV_PATH, DB_PATH)


@st.cache_resource
def get_analytics():
    """Cache analytics instance."""
    return MobilityAnalytics(DB_PATH)


def initialize_session_state():
    """Inicializa el estado de sesión."""
    db = get_database()

    if "available_routes" not in st.session_state:
        routes = db.get_available_routes()
        st.session_state.available_routes = routes if routes else []

    if "route_statistics" not in st.session_state:
        st.session_state.route_statistics = {}


def load_data_for_route(origin: str, destination: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """Carga datos para una ruta específica."""
    db = get_database()

    df = db.query_measurements(
        origin=origin,
        destination=destination,
        start_timestamp=start_date.isoformat(),
        end_timestamp=end_date.isoformat(),
        limit=10000,
    )

    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp")

    return df


def get_route_statistics(origin: str, destination: str) -> dict:
    """Obtiene estadísticas de una ruta."""
    db = get_database()
    return db.get_route_statistics(origin, destination, hours=24)


def main():
    """Función principal del dashboard."""
    render_header()
    initialize_session_state()

    if not st.session_state.available_routes:
        st.error("❌ No data available. Please run the collector first.")
        st.stop()

    selected_route, start_date, end_date = render_sidebar_filters()

    if not selected_route:
        st.error("Please select a route")
        st.stop()

    origin, destination = selected_route

    df = load_data_for_route(origin, destination, start_date, end_date)

    if df.empty:
        st.warning("No data available for this route and time period")
        st.stop()

    latest = df.iloc[-1]
    stats = get_route_statistics(origin, destination)
    st.session_state.route_statistics = stats

    st.subheader(f"📍 {origin} → {destination}")
    render_metric_cards(latest)

    render_traffic_status(latest)
    render_alerts(df, stats)

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📍 Route Map")
        origin_coords = (LOCATIONS[origin].latitude, LOCATIONS[origin].longitude)
        dest_coords = (LOCATIONS[destination].latitude, LOCATIONS[destination].longitude)
        render_map(origin_coords, dest_coords)

    with col2:
        st.subheader("🌤️ Weather Comparison")

        weather_col1, weather_col2 = st.columns(2)

        with weather_col1:
            st.markdown("**Origin Weather**")
            origin_temp = latest.get("origin_temperature")
            origin_humidity = latest.get("origin_humidity")
            origin_weather = latest.get("origin_weather")

            if pd.notna(origin_temp):
                st.metric("Temperature", f"{origin_temp:.1f}°C")
            if pd.notna(origin_humidity):
                st.metric("Humidity", f"{origin_humidity:.0f}%")
            if pd.notna(origin_weather):
                st.caption(origin_weather.title())

        with weather_col2:
            st.markdown("**Destination Weather**")
            dest_temp = latest.get("destination_temperature")
            dest_humidity = latest.get("destination_humidity")
            dest_weather = latest.get("destination_weather")

            if pd.notna(dest_temp):
                st.metric("Temperature", f"{dest_temp:.1f}°C")
            if pd.notna(dest_humidity):
                st.metric("Humidity", f"{dest_humidity:.0f}%")
            if pd.notna(dest_weather):
                st.caption(dest_weather.title())

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Travel Time",
        "🚗 Traffic Analysis",
        "🌡️ Weather Impact",
        "📊 Rankings"
    ])

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_travel_time_chart(df), use_container_width=True)
        with col2:
            st.plotly_chart(create_speed_chart(df), use_container_width=True)

    with tab2:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_traffic_delay_chart(df), use_container_width=True)
        with col2:
            st.info("🚦 **Interpretación de Colores:**\n\n"
                   "🟢 **Verde** = Sin retraso (0-1 min)\n"
                   "🟡 **Amarillo** = Tráfico moderado (1-4 min)\n"
                   "🔴 **Rojo** = Tráfico pesado (>4 min)")

    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(create_temperature_chart(df), use_container_width=True)
        with col2:
            st.plotly_chart(create_humidity_chart(df), use_container_width=True)

    with tab4:
        st.subheader("Route Rankings (Last 24h)")

        analytics = get_analytics()
        routes_stats = analytics.compare_routes(hours=24)

        if not routes_stats.empty:
            routes_stats_sorted = routes_stats.sort_values("avg_travel_time")

            rank_data = []
            for idx, row in routes_stats_sorted.iterrows():
                rank_data.append({
                    "Rank": len(rank_data) + 1,
                    "Route": f"{row['origin']} → {row['destination']}",
                    "Travel Time": f"{row['avg_travel_time']:.1f}min",
                    "Delay": f"{row['avg_delay']:.1f}min",
                    "Speed": f"{row['avg_speed']:.1f}km/h",
                    "Distance": f"{row.get('distance_km', 'N/A')}km",
                })

            st.dataframe(
                pd.DataFrame(rank_data),
                use_container_width=True,
                hide_index=True,
            )

    st.divider()

    st.subheader("📋 Historical Data")
    render_historical_table(df)

    st.divider()

    st.subheader("📥 Export Data")
    render_export_buttons(df, f"mobility_{origin}_{destination}")


if __name__ == "__main__":
    main()
