"""Operations dashboard for managers and operations team."""

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase

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
def _fetch_route_hour_average(_db, days: int):
    """Promedio por ruta y hora de los últimos `days` días, agregado en SQL.

    FIX: antes se traían las 10.000 mediciones MÁS RECIENTES
    (`query_measurements(limit=10000)`) y se agrupaban en pandas; con
    recolección continua eso eran ~5 días, no los 7 que dice el título.
    """
    return _db.get_route_hour_average(days)


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
                'delay': f"{row.get('avg_delay'):.1f} min" if pd.notna(row.get('avg_delay')) else 'sin dato'
            })

    if alerts:
        alerts_df = pd.DataFrame(alerts)
        st.dataframe(alerts_df, width='stretch', hide_index=True)
    else:
        st.info("✅ No critical alerts")


# Una lectura de tráfico más vieja que esto ya no sirve para decir "cómo está
# ahora": TomTom mide cada 27 min, así que 90 min equivalen a ~3 ciclos perdidos.
STALE_TRAFFIC_MINUTES = 90


def _status_label(delay) -> str:
    """Color de estado según el retraso por tráfico (min)."""
    if delay <= 1:
        return '🟢 Free Flow'
    if delay <= 4:
        return '🟡 Moderate'
    return '🔴 Heavy'


def _age_text(ts, now) -> str:
    minutes = (now - pd.to_datetime(ts, utc=True)).total_seconds() / 60
    if minutes < 90:
        return f"hace {max(minutes, 0):.0f} min"
    if minutes < 60 * 48:
        return f"hace {minutes / 60:.1f} h"
    return f"hace {minutes / 1440:.1f} días"


def build_route_status_grid(latest: pd.DataFrame, latest_traffic: pd.DataFrame, now=None) -> pd.DataFrame:
    """Estado por ruta. `latest` = última medición de cada ruta (cualquier
    fuente); `latest_traffic` = última medición CON dato de tráfico.

    Antes el estado salía de `traffic_delay_min` de la última fila, y `_safe()`
    convertía el NULL en 0: con ORS —que no reporta tráfico— cualquier ruta
    cuya última medición fuera de ORS aparecía como "🟢 Free Flow" sin ningún
    dato que lo respaldara. Ahora el estado se calcula con la última lectura
    que SÍ tiene tráfico (TomTom), se indica de hace cuánto es, y si no existe
    o está desactualizada (> STALE_TRAFFIC_MINUTES) se dice, en vez de pintar
    verde. El tiempo de viaje y la velocidad vienen de la última medición.
    """
    now = now if now is not None else pd.Timestamp.now(tz="UTC")
    traffic_by_route = {
        (r["origin"], r["destination"]): r for _, r in latest_traffic.iterrows()
    }
    rows = []
    for _, row in latest.iterrows():
        key = (row["origin"], row["destination"])
        traffic = traffic_by_route.get(key)

        if traffic is None:
            status, delay_txt, traffic_txt = '⚪ Sin dato de tráfico', 'sin dato', 'nunca'
        else:
            minutes = (now - pd.to_datetime(traffic["timestamp"], utc=True)).total_seconds() / 60
            traffic_txt = f"{_age_text(traffic['timestamp'], now)} ({traffic['data_source']})"
            delay_txt = f"{traffic['traffic_delay_min']:.1f} min"
            status = '⚪ Lectura desactualizada' if minutes > STALE_TRAFFIC_MINUTES else _status_label(traffic['traffic_delay_min'])

        travel = row.get('travel_time_min')
        speed = row.get('average_speed_kmh')
        rows.append({
            'Route': f'{key[0]} → {key[1]}',
            'Status': status,
            'Travel Time': f"{travel:.1f} min" if pd.notna(travel) else 'sin dato',
            'Delay': delay_txt,
            'Speed': f"{speed:.1f} km/h" if pd.notna(speed) else 'sin dato',
            'Traffic reading': traffic_txt,
            'Last measurement': f"{_age_text(row['timestamp'], now)} ({row['data_source']})",
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_route_status_grid(_db):
    """Última medición de cada ruta y última lectura de tráfico de cada ruta.

    Dos consultas en total (antes: una por ruta, N+1), con
    RouteDatabase.get_latest_per_route().
    """
    latest = _db.get_latest_per_route()
    latest_traffic = _db.get_latest_per_route(require_column='traffic_delay_min')
    return build_route_status_grid(latest, latest_traffic)


def render_route_status_grid(db):
    """Render route status grid with color coding."""
    st.subheader("📍 Route Status Overview")

    status_df = _fetch_route_status_grid(db)
    if not status_df.empty:
        st.dataframe(status_df, width='stretch', hide_index=True)


def render_last_24h_summary(db):
    """Promedio real de las últimas 24 h por ruta (datos medidos, no
    proyecciones).

    Reemplaza a "24-Hour Predictions" e "Incident Impact Analysis": la
    primera multiplicaba el promedio por 1.1 / 1.05 y mostraba una
    "Confidence 90%" fija, sin ningún modelo detrás; la segunda mostraba
    ceros y deltas escritos a mano, porque el proyecto no recolecta
    incidentes. Ninguna de las dos se calculaba a partir de los datos.
    """
    st.subheader("📈 Últimas 24 horas por ruta")

    stats_df = _fetch_all_routes_statistics(db, hours=24)
    if stats_df.empty:
        st.info("Sin mediciones en las últimas 24 horas.")
        return

    summary_df = pd.DataFrame({
        'Ruta': stats_df['origin'] + ' → ' + stats_df['destination'],
        'Mediciones': stats_df['measurements'],
        'Tiempo promedio (min)': stats_df['avg_travel_time'],
        'Mínimo (min)': stats_df['min_travel_time'],
        'Máximo (min)': stats_df['max_travel_time'],
    })
    st.dataframe(summary_df, width='stretch', hide_index=True)


def render_performance_heatmap(db):
    """Render route performance heatmap by hour."""
    st.subheader("🔥 Performance Heatmap (24-hour)")

    df = _fetch_route_hour_average(db, days=7)

    if df.empty:
        st.warning("No data available")
        return

    df['route'] = df['origin'] + ' → ' + df['destination']

    # Una fila por ruta y hora (ya promediadas en SQL). Se fuerzan las 24
    # columnas: si alguna hora no tiene mediciones, el pivote traía menos
    # columnas que las 24 etiquetas fijas del eje X y el mapa se desalineaba.
    pivot_data = (
        df.pivot(index='route', columns='hour', values='avg_travel_time')
        .reindex(columns=range(24))
    )

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

    # Real-time alerts
    render_real_time_alerts(db)

    st.divider()

    # Route status grid
    render_route_status_grid(db)

    st.divider()

    # Medición real de las últimas 24 h (reemplaza predicciones/incidentes ficticios)
    render_last_24h_summary(db)

    st.divider()

    # Performance heatmap
    render_performance_heatmap(db)

    st.divider()

    st.info("💡 **Tip:** Refresh the page every 5 minutes for latest updates")


if __name__ == "__main__":
    main()
