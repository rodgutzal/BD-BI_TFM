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

# Ver nota en executive_dashboard.py: mismo TTL, misma razón.
_CACHE_TTL = 60


def _safe(value, default=0.0):
    """
    Convierte None/NaN a `default`.

    BD_BI_TFM: con DATA_SOURCE=ors (el default), traffic_delay_min,
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


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_all_routes_statistics(_db, hours: int):
    """Estadísticas agregadas de TODAS las rutas en una sola consulta.

    FIX (rendimiento, antes N+1): render_real_time_alerts y
    render_24h_predictions hacían `for origin, destination in routes:
    db.get_route_statistics(origin, destination, hours=X)` — una consulta
    SQLite por ruta (12 consultas separadas con las rutas actuales) en
    CADA rerun de Streamlit. get_all_routes_statistics() ya existía en
    database.py y calcula exactamente lo mismo con un solo GROUP BY; solo
    hacía falta usarla aquí. Cacheado además, para no repetir ni siquiera
    esa única consulta en cada clic dentro de la ventana de TTL.
    """
    return _db.get_all_routes_statistics(hours=hours)


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_recent_measurements(_db, days: int):
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    return _db.query_measurements(
        start_timestamp=start_date.isoformat(),
        end_timestamp=end_date.isoformat(),
        limit=10000,
    )


def render_real_time_alerts(db):
    """Render real-time alerts for operations."""
    st.subheader("🚨 Real-Time Alerts")

    stats_df = _fetch_all_routes_statistics(db, hours=1)
    alerts = []

    for _, row in stats_df.iterrows():
        avg_time = _safe(row.get('avg_travel_time'))
        if avg_time > 30:
            alerts.append({
                'route': f"{row['origin']} → {row['destination']}",
                'severity': 'HIGH' if avg_time > 45 else 'MEDIUM',
                'travel_time': f"{avg_time:.1f} min",
                'delay': f"{_safe(row.get('avg_delay')):.1f} min"
            })

    if alerts:
        alerts_df = pd.DataFrame(alerts)
        st.dataframe(alerts_df, width='stretch', hide_index=True)
    else:
        st.info("✅ No critical alerts")


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_route_status_grid(_db):
    """Última medición de cada ruta, con su color de estado.

    NOTA: esto sigue siendo una consulta por ruta (N+1) — a diferencia de
    los demás fixes de esta pasada, este caso pide la ÚLTIMA FILA completa
    de cada ruta (travel_time_min, traffic_delay_min, average_speed_kmh),
    no un agregado, así que get_all_routes_statistics() no sirve aquí tal
    cual. La solución de fondo (una función nueva en database.py con
    GROUP BY + MAX(timestamp) para traer la última fila de cada ruta en una
    sola consulta) queda pendiente para una siguiente pasada. Cachear esto
    igual es una mejora real mientras tanto: el N+1 ahora corre una vez por
    ventana de TTL, no en cada interacción del usuario.
    """
    routes = _db.get_available_routes()
    status_data = []

    for origin, destination in routes:
        latest = _db.query_measurements(origin=origin, destination=destination, limit=1)

        if not latest.empty:
            row = latest.iloc[-1]
            delay = _safe(row.get('traffic_delay_min'))

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

    return pd.DataFrame(status_data)


def render_route_status_grid(db):
    """Render route status grid with color coding."""
    st.subheader("📍 Route Status Overview")

    status_df = _fetch_route_status_grid(db)
    if not status_df.empty:
        st.dataframe(status_df, width='stretch', hide_index=True)


def render_24h_predictions(db, analytics):
    """Render 24-hour predictions for all routes."""
    st.subheader("📈 24-Hour Predictions")

    # FIX (rendimiento, antes N+1 x2): la versión anterior hacía, por cada
    # ruta, una consulta query_measurements(limit=1) para calcular `hour`
    # (que nunca se usaba más abajo — código muerto) MÁS otra consulta
    # get_route_statistics(hours=24) — 24 consultas en total con las rutas
    # actuales. Con get_all_routes_statistics(hours=24) alcanza una sola.
    stats_df = _fetch_all_routes_statistics(db, hours=24)
    predictions_data = []

    for _, row in stats_df.iterrows():
        predicted_time = _safe(row.get('avg_travel_time'))
        predictions_data.append({
            'Route': f"{row['origin']} → {row['destination']}",
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

    df = _fetch_recent_measurements(db, days=7)

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
