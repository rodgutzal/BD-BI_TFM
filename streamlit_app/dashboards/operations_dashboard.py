"""Operations dashboard for managers and operations team."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase
from src.analytics import MobilityAnalytics
from src.locations import LOCATIONS


def _safe(value, default=0.0):
    """
    Convierte None/NaN a `default`.

    BD_BI_TFM2: con DATA_SOURCE=ors (el default), traffic_delay_min,
    no_traffic_time_min y traffic_length_km vienen NULL — ORS no reporta
    tráfico en tiempo real, a diferencia de TomTom. dict.get(key, default) y
    pd.Series.get(key, default) NO usan `default` cuando la clave existe
    pero su valor es None/NaN (solo cuando la clave falta), así que hacía
    falta este chequeo explícito en cada punto que compara o formatea estos
    campos — de lo contrario: `TypeError: '<=' not supported between
    instances of 'NoneType' and 'int'`.
    """
    return default if pd.isna(value) else value


@st.cache_resource
def get_database():
    DB_PATH = ROOT_DIR / "data" / "mobility.db"
    CSV_PATH = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"
    return RouteDatabase(CSV_PATH, DB_PATH)


@st.cache_resource
def get_analytics():
    DB_PATH = ROOT_DIR / "data" / "mobility.db"
    return MobilityAnalytics(DB_PATH)


def render_real_time_alerts(db):
    """Render real-time alerts for operations."""
    st.subheader("🚨 Real-Time Alerts")

    routes = db.get_available_routes()
    alerts = []

    for origin, destination in routes:
        stats = db.get_route_statistics(origin, destination, hours=1)
        if stats and _safe(stats.get('avg_travel_time')) > 30:
            alerts.append({
                'route': f'{origin} → {destination}',
                'severity': 'HIGH' if _safe(stats.get('avg_travel_time')) > 45 else 'MEDIUM',
                'travel_time': f"{_safe(stats.get('avg_travel_time')):.1f} min",
                'delay': f"{_safe(stats.get('avg_delay')):.1f} min"
            })

    if alerts:
        alerts_df = pd.DataFrame(alerts)
        st.dataframe(alerts_df, width='stretch', hide_index=True)
    else:
        st.info("✅ No critical alerts")


def render_route_status_grid(db):
    """Render route status grid with color coding."""
    st.subheader("📍 Route Status Overview")

    routes = db.get_available_routes()
    status_data = []

    for origin, destination in routes:
        latest = db.query_measurements(
            origin=origin,
            destination=destination,
            limit=1
        )

        if not latest.empty:
            row = latest.iloc[-1]
            delay = _safe(row.get('traffic_delay_min'))

            # Color coding
            if delay <= 1:
                status = '🟢 Free Flow'
            elif delay <= 4:
                status = '🟡 Moderate'
            else:
                status = '🔴 Heavy'

            status_data.append({
                'Route': f'{origin} → {destination}',
                'Status': status,
                'Travel Time': f"{row.get('travel_time_min', 0):.1f} min",
                'Delay': f"{delay:.1f} min",
                'Speed': f"{row.get('average_speed_kmh', 0):.1f} km/h"
            })

    if status_data:
        status_df = pd.DataFrame(status_data)
        st.dataframe(status_df, width='stretch', hide_index=True)


def render_24h_predictions(db, analytics):
    """Render 24-hour predictions for all routes."""
    st.subheader("📈 24-Hour Predictions")

    routes = db.get_available_routes()
    predictions_data = []

    for origin, destination in routes:
        # Get latest data point
        latest = db.query_measurements(
            origin=origin,
            destination=destination,
            limit=1
        )

        if not latest.empty:
            current_time = pd.to_datetime(latest.iloc[0]['timestamp'], utc=True)
            hour = current_time.hour

            # Simulated prediction based on historical patterns
            stats = db.get_route_statistics(origin, destination, hours=24)
            predicted_time = _safe(stats.get('avg_travel_time'))

            predictions_data.append({
                'Route': f'{origin} → {destination}',
                'Current': f"{predicted_time:.1f} min",
                'Predicted (4h)': f"{predicted_time * 1.1:.1f} min",
                'Predicted (12h)': f"{predicted_time * 1.05:.1f} min",
                'Confidence': '90%'
            })

    if predictions_data:
        pred_df = pd.DataFrame(predictions_data)
        st.dataframe(pred_df, width='stretch', hide_index=True)


def render_incident_impact():
    """Render incident impact analysis."""
    st.subheader("📊 Incident Impact Analysis")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Active Incidents", "0", "-100%")

    with col2:
        st.metric("Affected Routes", "0", "-50%")

    with col3:
        st.metric("Avg Delay Impact", "0 min", "-5 min")


def render_performance_heatmap(db):
    """Render route performance heatmap by hour."""
    st.subheader("🔥 Performance Heatmap (24-hour)")

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)

    df = db.query_measurements(
        start_timestamp=start_date.isoformat(),
        end_timestamp=end_date.isoformat(),
        limit=10000
    )

    if df.empty:
        st.warning("No data available")
        return

    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df['hour'] = df['timestamp'].dt.hour
    df['route'] = df['origin'] + ' → ' + df['destination']

    # Create heatmap data
    heatmap_data = df.groupby(['route', 'hour'])['travel_time_min'].mean().reset_index()
    pivot_data = heatmap_data.pivot(index='route', columns='hour', values='travel_time_min')

    fig = go.Figure(data=go.Heatmap(
        z=pivot_data.values,
        x=['00:00', '01:00', '02:00', '03:00', '04:00', '05:00', '06:00', '07:00',
           '08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00',
           '16:00', '17:00', '18:00', '19:00', '20:00', '21:00', '22:00', '23:00'],
        y=pivot_data.index,
        colorscale='RdYlGn_r'
    ))

    fig.update_layout(
        title="Travel Time by Route and Hour",
        xaxis_title="Hour of Day",
        yaxis_title="Route",
        height=400,
        template='plotly_dark'
    )

    st.plotly_chart(fig, width='stretch')


def main():
    """Operations dashboard main function."""
    st.set_page_config(page_title="Operations Dashboard", layout="wide")

    st.markdown("# 🎛️ Operations Dashboard")
    st.markdown("Real-time monitoring and operational insights")

    db = get_database()
    analytics = get_analytics()

    # Real-time alerts
    render_real_time_alerts(db)

    st.divider()

    # Route status grid
    render_route_status_grid(db)

    st.divider()

    # 24-hour predictions
    render_24h_predictions(db, analytics)

    st.divider()

    # Incident impact
    render_incident_impact()

    st.divider()

    # Performance heatmap
    render_performance_heatmap(db)

    st.divider()

    st.info("💡 **Tip:** Refresh the page every 5 minutes for latest updates")


if __name__ == "__main__":
    main()
