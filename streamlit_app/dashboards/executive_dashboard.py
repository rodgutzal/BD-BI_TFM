"""Executive dashboard for C-level insights."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase
from src.analytics import MobilityAnalytics
from src.data_warehouse.gold_layer import GoldLayer

# TTL corto pero no-cero: el collector escribe cada 15-27 min (modo híbrido),
# así que no hace falta re-consultar en cada clic/interacción para "sentirse"
# en vivo — 60s balancea frescura real vs. no golpear SQLite en cada rerun
# de Streamlit (que re-ejecuta todo el script en cada interacción).
_CACHE_TTL = 60


@st.cache_resource
def get_database():
    DB_PATH = ROOT_DIR / "data" / "mobility.db"
    CSV_PATH = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"
    return RouteDatabase(CSV_PATH, DB_PATH)


@st.cache_resource
def get_analytics():
    DB_PATH = ROOT_DIR / "data" / "mobility.db"
    return MobilityAnalytics(DB_PATH)


@st.cache_resource
def get_gold_layer():
    DB_PATH = ROOT_DIR / "data" / "mobility.db"
    return GoldLayer(DB_PATH)


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_daily_average(_db, days: int):
    """Promedio diario de tiempo de viaje de los últimos `days` días,
    agregado en SQL.

    FIX: antes se traían las mediciones con `query_measurements(limit=10000)`
    —que devuelve las 10.000 MÁS RECIENTES— y se agrupaban por día en pandas.
    Con ~1.800 filas/día eso eran ~5 días, no los 30 que decía el gráfico.
    """
    return _db.get_daily_average(days)


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_travel_times(_db, days: int):
    """Todos los tiempos de viaje de los últimos `days` días (solo esa
    columna, sin LIMIT) para el histograma."""
    return _db.query_columns(["travel_time_min"], days)


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_executive_summary(_gold, days: int):
    return _gold.get_executive_summary(days=days)


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_period_comparison(_gold, days: int):
    """Promedios de los últimos `days` días (incluido hoy) y de los `days`
    anteriores, para calcular los deltas de las tarjetas KPI. Antes los
    deltas eran texto fijo ("-2 min", "+5%") que no dependía de los datos."""
    today = datetime.now(timezone.utc).date()
    tomorrow = (today + timedelta(days=1)).isoformat()
    cur_start = (today - timedelta(days=days - 1)).isoformat()
    prev_start = (today - timedelta(days=2 * days - 1)).isoformat()
    return {
        'current': _gold.get_period_metrics(cur_start, tomorrow),
        'previous': _gold.get_period_metrics(prev_start, cur_start),
    }


def _delta(current, previous, fmt: str):
    """Texto del delta, o None si falta alguno de los dos periodos."""
    if current is None or previous is None:
        return None
    return fmt.format(current - previous)


def _hay_datos(summary: dict) -> bool:
    """¿El resumen se calculó con mediciones? Sin filas en el periodo (una base recién creada, o un colector parado
    más de 30 días) la capa Gold devuelve ceros, y un 0 % de fiabilidad no es una medición sino la ausencia de ella."""
    return bool(summary.get('total_measurements'))


def render_kpi_cards(summary: dict, comparison: dict = None):
    """Render executive KPI cards.

    `comparison` trae los promedios del periodo actual y del anterior
    (ver _fetch_period_comparison). Sin periodo anterior con datos no se
    muestra delta, en lugar de inventar uno.
    """
    comparison = comparison or {}
    cur = comparison.get('current') or {}
    prev = comparison.get('previous') or {}
    hay = _hay_datos(summary)
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "System Avg Travel Time",
            f"{summary.get('system_avg_travel_time', 0):.1f} min" if hay else "—",
            delta=_delta(cur.get('avg_travel_time'), prev.get('avg_travel_time'), "{:+.1f} min vs. periodo anterior"),
            delta_color="inverse",  # menos tiempo de viaje es mejor
        )

    with col2:
        st.metric(
            "System Reliability",
            f"{summary.get('system_reliability', 0):.1f}%" if hay else "—",
            delta=_delta(cur.get('reliability'), prev.get('reliability'), "{:+.1f} pts vs. periodo anterior"),
        )

    with col3:
        st.metric(
            "Active Routes",
            summary.get('total_routes', 0),
        )

    with col4:
        st.metric(
            "Total Measurements",
            f"{summary.get('total_measurements', 0):,}"
        )


def render_route_performance(best_routes, worst_routes):
    """Render best vs worst route comparison."""
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🏆 Best Performing Routes")
        best_df = pd.DataFrame(best_routes)
        if not best_df.empty:
            best_df['route'] = best_df['origin'] + ' → ' + best_df['destination']
            st.dataframe(
                best_df[['route', 'avg_time', 'avg_reliability']].head(5),
                width='stretch',
                hide_index=True
            )

    with col2:
        st.subheader("⚠️ Routes Needing Attention")
        worst_df = pd.DataFrame(worst_routes)
        if not worst_df.empty:
            worst_df['route'] = worst_df['origin'] + ' → ' + worst_df['destination']
            st.dataframe(
                worst_df[['route', 'avg_time', 'avg_reliability']].tail(5),
                width='stretch',
                hide_index=True
            )


def render_trend_chart(days: int = 30):
    """Render 30-day trend chart."""
    db = get_database()

    daily = _fetch_daily_average(db, days)

    if daily.empty:
        st.warning("No data available for trend analysis")
        return

    daily_avg = daily.set_index('date')['avg_travel_time']

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily_avg.index,
        y=daily_avg.values,
        mode='lines+markers',
        name='Avg Travel Time',
        line=dict(color='#1f77b4', width=3),
        marker=dict(size=8)
    ))

    # Add trend line
    if len(daily_avg) > 1:
        z = np.polyfit(range(len(daily_avg)), daily_avg.values, 1)
        p = np.poly1d(z)
        fig.add_trace(go.Scatter(
            x=daily_avg.index,
            y=p(range(len(daily_avg))),
            mode='lines',
            name='Trend',
            line=dict(color='red', width=2, dash='dash')
        ))

    fig.update_layout(
        title=f"System Performance - {days} Day Trend",
        xaxis_title="Date",
        yaxis_title="Avg Travel Time (min)",
        hovermode='x unified',
        template='plotly_dark',
        height=400
    )

    st.plotly_chart(fig, width='stretch')


def render_distribution_chart():
    """Render travel time distribution."""
    db = get_database()

    df = _fetch_travel_times(db, days=30)

    if df.empty:
        st.warning("No data available")
        return

    fig = go.Figure()

    # Histogram
    fig.add_trace(go.Histogram(
        x=df['travel_time_min'],
        name='Travel Time Distribution',
        nbinsx=50,
        marker=dict(color='rgba(31, 119, 180, 0.7)')
    ))

    # Add mean and median lines
    mean_val = df['travel_time_min'].mean()
    median_val = df['travel_time_min'].median()

    fig.add_vline(x=mean_val, line_dash="dash", line_color="red", annotation_text="Mean")
    fig.add_vline(x=median_val, line_dash="dot", line_color="green", annotation_text="Median")

    fig.update_layout(
        title="Travel Time Distribution (30 days)",
        xaxis_title="Travel Time (minutes)",
        yaxis_title="Frequency",
        template='plotly_dark',
        height=400,
        showlegend=True
    )

    st.plotly_chart(fig, width='stretch')


def main():
    """Executive dashboard main function."""
    st.set_page_config(page_title="Executive Dashboard", layout="wide")

    st.markdown("# 📊 Executive Dashboard")
    st.markdown("System-wide performance metrics and strategic insights")

    # Get summary
    gold = get_gold_layer()
    summary = _fetch_executive_summary(gold, days=30)

    if 'error' in summary:
        st.error("Error loading summary data")
        return

    # KPI Cards
    st.subheader("Key Performance Indicators")
    render_kpi_cards(summary, _fetch_period_comparison(gold, days=30))

    st.divider()

    # Route Performance
    st.subheader("Route Performance Analysis")
    render_route_performance(
        summary.get('best_routes', []),
        summary.get('worst_routes', [])
    )

    st.divider()

    # Trend Analysis
    col1, col2 = st.columns(2)
    with col1:
        render_trend_chart(days=30)
    with col2:
        render_distribution_chart()

    st.divider()

    # Alerts
    st.subheader("⚠️ System Alerts")
    alerts = []

    if not _hay_datos(summary):
        # Sin mediciones no hay nada que evaluar: antes la fiabilidad 0 % disparaba «Low system reliability».
        st.info("Sin mediciones en los últimos 30 días: no se evalúan alertas.")
        return
    if summary.get('system_avg_travel_time', 0) > 30:
        alerts.append("🔴 High average travel time detected (>30 min)")
    if summary.get('system_reliability', 0) < 50:
        alerts.append("🟡 Low system reliability (<50%)")

    if alerts:
        for alert in alerts:
            st.warning(alert)
    else:
        st.success("✅ All systems operating normally")


if __name__ == "__main__":
    import numpy as np
    main()
