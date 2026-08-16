"""Componentes reutilizables para el dashboard Streamlit."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import pandas as pd
import streamlit as st


def _safe(value, default=0.0):
    """None/NaN -> default. Con DATA_SOURCE=ors, traffic_delay_min y
    no_traffic_time_min vienen NULL (ORS no reporta tráfico en tiempo
    real) — ver la misma nota en streamlit_app/dashboards/operations_dashboard.py."""
    return default if pd.isna(value) else value


def render_header():
    """Renderiza el encabezado del dashboard."""
    st.set_page_config(
        page_title="Urban Mobility Analytics",
        page_icon="🚗",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("🚗 Urban Mobility Analytics")
        st.caption("Real-time traffic and weather monitoring in Malta")
    with col2:
        st.metric("Status", "🟢 Live")


def render_sidebar_filters() -> Tuple[str, datetime, datetime]:
    """Renderiza el menú lateral con filtros. Retorna route, start_date, end_date."""
    with st.sidebar:
        st.header("⚙️ Filters")

        available_routes = st.session_state.get("available_routes", [])

        if available_routes:
            route_display = [f"{o} → {d}" for o, d in available_routes]
            selected_idx = st.selectbox(
                "Select Route",
                range(len(route_display)),
                format_func=lambda i: route_display[i],
            )
            selected_route = available_routes[selected_idx]
        else:
            selected_route = None
            st.warning("No routes available")

        st.divider()

        time_range = st.radio(
            "Time Range",
            ["Last 24h", "Last 7d", "Last 30d", "Custom"],
            horizontal=False,
        )

        now = datetime.now(timezone.utc)

        if time_range == "Last 24h":
            start_date = now - timedelta(hours=24)
            end_date = now
        elif time_range == "Last 7d":
            start_date = now - timedelta(days=7)
            end_date = now
        elif time_range == "Last 30d":
            start_date = now - timedelta(days=30)
            end_date = now
        else:
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input(
                    "Start Date",
                    value=(now - timedelta(days=7)).date(),
                )
                start_date = datetime.combine(start_date, datetime.min.time()).replace(
                    tzinfo=timezone.utc
                )
            with col2:
                end_date = st.date_input(
                    "End Date",
                    value=now.date(),
                )
                end_date = datetime.combine(end_date, datetime.max.time()).replace(
                    tzinfo=timezone.utc
                )

        st.divider()

        auto_refresh = st.checkbox("Auto-refresh", value=True)
        refresh_interval = st.slider(
            "Refresh interval (seconds)",
            min_value=30,
            max_value=300,
            value=120,
            step=30,
            disabled=not auto_refresh,
        )

        if auto_refresh:
            st_autorefresh = __import__("streamlit_autorefresh")
            st_autorefresh.st_autorefresh(
                interval=refresh_interval * 1000,
                key="dashboard_refresh"
            )

        st.divider()

        if st.button("🔄 Refresh Now", use_container_width=True):
            st.rerun()

        st.divider()

        if selected_route:
            origin, destination = selected_route
            stats = st.session_state.get("route_statistics", {})
            if stats:
                st.subheader("Route Stats (24h)")
                st.metric("Measurements", stats.get("count", 0))
                st.metric("Avg Travel Time", f"{stats.get('avg_travel_time', 0):.1f}min")
                st.metric("Min/Max", f"{stats.get('min_travel_time', 0):.1f}/{stats.get('max_travel_time', 0):.1f}min")

    return selected_route, start_date, end_date


def render_metric_cards(latest_row: pd.Series):
    """Renderiza tarjetas de métricas principales."""
    travel_time = float(latest_row.get("travel_time_min", 0))
    normal_time = float(_safe(latest_row.get("no_traffic_time_min")))
    traffic_delay = float(_safe(latest_row.get("traffic_delay_min")))
    distance = float(latest_row.get("distance_km", 0))
    avg_speed = float(latest_row.get("average_speed_kmh", 0))

    traffic_pct = (traffic_delay / travel_time * 100) if travel_time > 0 else 0

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Travel Time",
            f"{travel_time:.1f} min",
            delta=f"{traffic_delay:.1f}min delay" if traffic_delay > 0 else "No delay",
            delta_color="inverse" if traffic_delay > 0 else "off",
        )

    with col2:
        st.metric(
            "Without Traffic",
            f"{normal_time:.1f} min",
        )

    with col3:
        st.metric(
            "Distance",
            f"{distance:.2f} km",
        )

    with col4:
        st.metric(
            "Avg Speed",
            f"{avg_speed:.1f} km/h",
        )

    col5, col6, col7, col8 = st.columns(4)

    with col5:
        if traffic_delay <= 0.5:
            delta_color = "off"
            symbol = "✅"
        elif traffic_delay <= 4:
            delta_color = "off"
            symbol = "⚠️"
        else:
            delta_color = "inverse"
            symbol = "🚨"

        st.metric(
            "Traffic Delay",
            f"{traffic_delay:.1f} min",
            delta=f"{symbol}",
        )

    with col6:
        st.metric(
            "Congestion",
            f"{traffic_pct:.0f}%",
        )

    with col7:
        origin_temp = latest_row.get("origin_temperature")
        temp_str = f"{origin_temp:.1f}°C" if pd.notna(origin_temp) else "N/A"
        st.metric("Origin Temp", temp_str)

    with col8:
        origin_humidity = latest_row.get("origin_humidity")
        humidity_str = f"{origin_humidity:.0f}%" if pd.notna(origin_humidity) else "N/A"
        st.metric("Origin Humidity", humidity_str)


def render_traffic_status(latest_row: pd.Series):
    """Renderiza indicador de estado de tráfico."""
    traffic_delay = float(_safe(latest_row.get("traffic_delay_min")))

    if traffic_delay <= 1:
        status = "🟢 Light Traffic"
        color = "green"
    elif traffic_delay <= 4:
        status = "🟡 Moderate Traffic"
        color = "yellow"
    else:
        status = "🔴 Heavy Traffic"
        color = "red"

    weather = str(latest_row.get("origin_weather", "Unknown")).title()
    last_update = latest_row.get("timestamp", "Unknown")

    st.markdown(
        f"""
        <div style="
            background-color: rgba(200, 200, 200, 0.1);
            padding: 1rem;
            border-radius: 0.5rem;
            border-left: 4px solid {color};
        ">
            <b>{status}</b> · Weather: {weather} · Last update: {last_update}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_map(origin: Tuple[float, float], destination: Tuple[float, float], polyline=None):
    """Renderiza el mapa con origen, destino y polyline."""
    import json

    map_data = pd.DataFrame(
        [
            {"lat": origin[0], "lon": origin[1], "type": "Origin"},
            {"lat": destination[0], "lon": destination[1], "type": "Destination"},
        ]
    )

    st.map(
        map_data,
        latitude="lat",
        longitude="lon",
        zoom=10,
        use_container_width=True,
    )


def render_alerts(df: pd.DataFrame, stats: dict):
    """Renderiza alertas basadas en condiciones."""
    alerts = []

    avg_delay = stats.get("avg_delay") or 0
    if avg_delay > 5:
        alerts.append(("🚨 High Delay", f"Average delay: {avg_delay:.1f}min", "error"))

    if df.empty:
        alerts.append(("⚠️ No Data", "No measurements available", "warning"))
    else:
        latest = df.iloc[-1]
        last_update_time = pd.to_datetime(latest.get("timestamp"), utc=True)
        minutes_ago = (datetime.now(timezone.utc) - last_update_time).total_seconds() / 60

        if minutes_ago > 5:
            alerts.append((
                "⚠️ Stale Data",
                f"No update in {int(minutes_ago)} minutes",
                "warning"
            ))

    if alerts:
        st.divider()
        for title, message, alert_type in alerts:
            if alert_type == "error":
                st.error(f"{title}: {message}")
            elif alert_type == "warning":
                st.warning(f"{title}: {message}")
            else:
                st.info(f"{title}: {message}")


def render_historical_table(df: pd.DataFrame):
    """Renderiza tabla histórica de mediciones."""
    if df.empty:
        st.info("No historical data available")
        return

    display_columns = [
        "timestamp", "origin", "destination", "travel_time_min",
        "no_traffic_time_min", "traffic_delay_min", "distance_km",
        "average_speed_kmh", "origin_temperature", "origin_humidity",
        "origin_weather"
    ]

    available_columns = [col for col in display_columns if col in df.columns]

    df_display = df[available_columns].copy()

    if "timestamp" in df_display.columns:
        df_display["timestamp"] = pd.to_datetime(
            df_display["timestamp"], utc=True
        ).dt.strftime("%Y-%m-%d %H:%M:%S")

    st.dataframe(
        df_display.sort_values(
            "timestamp",
            ascending=False
        ).head(100),
        use_container_width=True,
        hide_index=True,
    )


def render_export_buttons(df: pd.DataFrame, filename_prefix: str = "mobility_data"):
    """Renderiza botones de exportación."""
    col1, col2 = st.columns(2)

    with col1:
        csv_data = df.to_csv(index=False)
        st.download_button(
            label="📥 Download as CSV",
            data=csv_data,
            file_name=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col2:
        json_data = df.to_json(orient="records", indent=2)
        st.download_button(
            label="📥 Download as JSON",
            data=json_data,
            file_name=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True,
        )
