"""Analyst dashboard for data team and researchers."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.database import RouteDatabase
from src.analytics import MobilityAnalytics
from src.analytics.time_series_analysis import TimeSeriesAnalytics


@st.cache_resource
def get_database():
    DB_PATH = ROOT_DIR / "data" / "mobility.db"
    CSV_PATH = ROOT_DIR / "data" / "raw" / "route_weather_data.csv"
    return RouteDatabase(CSV_PATH, DB_PATH)


@st.cache_resource
def get_analytics():
    DB_PATH = ROOT_DIR / "data" / "mobility.db"
    return MobilityAnalytics(DB_PATH)


def render_data_explorer():
    """Interactive data explorer."""
    st.subheader("📊 Raw Data Explorer")

    db = get_database()
    routes = db.get_available_routes()

    col1, col2 = st.columns(2)

    with col1:
        selected_route = st.selectbox(
            "Select Route",
            routes,
            format_func=lambda x: f"{x[0]} → {x[1]}"
        )

    with col2:
        days = st.slider("Days of History", 1, 90, 30)

    if selected_route:
        origin, destination = selected_route
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        df = db.query_measurements(
            origin=origin,
            destination=destination,
            start_timestamp=start_date.isoformat(),
            end_timestamp=end_date.isoformat(),
            limit=10000
        )

        if not df.empty:
            st.dataframe(df, width='stretch', height=400)

            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"data_{origin}_{destination}.csv",
                mime="text/csv"
            )
        else:
            st.warning("No data available")


def render_statistical_tests():
    """Run statistical tests."""
    st.subheader("📈 Statistical Analysis")

    db = get_database()
    routes = db.get_available_routes()

    selected_route = st.selectbox(
        "Select Route for Analysis",
        routes,
        format_func=lambda x: f"{x[0]} → {x[1]}",
        key="stats_route"
    )

    if selected_route:
        origin, destination = selected_route
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)

        df = db.query_measurements(
            origin=origin,
            destination=destination,
            start_timestamp=start_date.isoformat(),
            end_timestamp=end_date.isoformat(),
            limit=10000
        )

        if not df.empty and len(df) > 10:
            ts_analysis = TimeSeriesAnalytics(df)

            tab1, tab2, tab3, tab4 = st.tabs([
                "Stationarity Tests",
                "Autocorrelation",
                "Patterns",
                "Anomalies"
            ])

            with tab1:
                st.markdown("**Stationarity Tests** (ADF & KPSS)")
                stationarity = ts_analysis.stationarity_tests('travel_time_min')
                if 'adf' in stationarity:
                    st.json(stationarity['adf'])
                if 'kpss' in stationarity:
                    st.json(stationarity['kpss'])

            with tab2:
                st.markdown("**Autocorrelation Analysis**")
                acf_data = ts_analysis.autocorrelation_analysis('travel_time_min')
                if 'acf' in acf_data:
                    st.json(acf_data['acf'])

            with tab3:
                st.markdown("**Day-of-Week Patterns**")
                patterns = ts_analysis.day_of_week_patterns('travel_time_min')
                if 'by_day' in patterns:
                    st.json(patterns['by_day'])

            with tab4:
                st.markdown("**Anomaly Detection**")
                anomalies = ts_analysis.change_point_detection('travel_time_min')
                if 'change_points' in anomalies:
                    st.write(f"**Total anomalies detected:** {anomalies['total_changes']}")
                    if anomalies['change_points']:
                        st.json(anomalies['change_points'][:10])


def render_model_performance():
    """Display model performance metrics."""
    st.subheader("🤖 Model Performance")

    db = get_database()

    # Check available models
    models_dir = ROOT_DIR / "models"
    model_files = []
    if models_dir.exists():
        model_files = list(models_dir.glob("*_ensemble.pkl"))
        if model_files:
            st.write(f"**Available Trained Models:** {len(model_files)}")
            for model_file in model_files:
                st.write(f"- {model_file.name}")
        else:
            st.info("No trained models yet. Run train_models.py to train ensemble models.")
    else:
        st.info("Models directory not found — run train_ensemble_models.py to create it.")

    # Model comparison
    routes = db.get_available_routes()
    if routes:
        st.markdown("**Model Metrics by Route**")
        model_data = []
        for origin, destination in routes:
            model_data.append({
                'Route': f'{origin} → {destination}',
                'Model Status': '✅ Trained' if any(m for m in model_files if f"{origin}_{destination}" in m.name) else '❌ Not Trained',
                'Samples': len(db.query_measurements(origin=origin, destination=destination, limit=1000))
            })

        if model_data:
            model_df = pd.DataFrame(model_data)
            st.dataframe(model_df, width='stretch', hide_index=True)


def render_correlation_matrix():
    """Render correlation matrix between variables."""
    st.subheader("📊 Feature Correlation Analysis")

    db = get_database()

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=30)

    df = db.query_measurements(
        start_timestamp=start_date.isoformat(),
        end_timestamp=end_date.isoformat(),
        limit=10000
    )

    if not df.empty:
        # Select numeric columns
        numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
        selected_cols = st.multiselect(
            "Select columns for correlation",
            numeric_cols,
            default=['travel_time_min', 'average_speed_kmh', 'origin_temperature']
        )

        if selected_cols and len(selected_cols) > 1:
            corr_matrix = df[selected_cols].corr()

            fig = go.Figure(data=go.Heatmap(
                z=corr_matrix.values,
                x=corr_matrix.columns,
                y=corr_matrix.columns,
                colorscale='RdBu',
                zmid=0,
                text=corr_matrix.values,
                texttemplate='%{text:.2f}',
                textfont={"size": 10}
            ))

            fig.update_layout(
                title="Feature Correlation Matrix",
                height=500,
                template='plotly_dark'
            )

            st.plotly_chart(fig, width='stretch')


def render_data_quality_report():
    """Data quality report."""
    st.subheader("✅ Data Quality Report")

    db = get_database()

    col1, col2, col3, col4 = st.columns(4)

    total_records = db.query_measurements(limit=100000)
    total = len(total_records)

    with col1:
        st.metric("Total Records", f"{total:,}")

    with col2:
        missing_pct = (total_records.isna().sum().sum() / (total * len(total_records.columns))) * 100
        st.metric("Missing Values", f"{missing_pct:.1f}%", "✅" if missing_pct < 5 else "⚠️")

    with col3:
        duplicates = total - len(total_records.drop_duplicates())
        st.metric("Duplicates", duplicates, "✅" if duplicates == 0 else "⚠️")

    with col4:
        st.metric("Date Range", "30+ days")

    # Data completeness by route
    st.markdown("**Completeness by Route**")
    routes = db.get_available_routes()
    completeness_data = []

    for origin, destination in routes:
        df = db.query_measurements(origin=origin, destination=destination, limit=1000)
        completeness = (1 - (df.isna().sum().sum() / (len(df) * len(df.columns)))) * 100
        completeness_data.append({
            'Route': f'{origin} → {destination}',
            'Completeness': f"{completeness:.1f}%",
            'Records': len(df)
        })

    if completeness_data:
        comp_df = pd.DataFrame(completeness_data)
        st.dataframe(comp_df, width='stretch', hide_index=True)


def render_sql_query():
    """Editor de SQL de solo lectura sobre data/mobility.db."""
    import sqlite3

    st.subheader("🗄️ SQL Query")
    st.caption(
        "Consultas de solo lectura sobre `data/mobility.db` (SQLite). "
        "La conexión se abre en modo `mode=ro`: cualquier intento de "
        "INSERT/UPDATE/DELETE/DROP falla a nivel del propio SQLite, no solo "
        "por un chequeo de texto — no puede corromper los datos que el "
        "collector está escribiendo en paralelo."
    )

    db_path = ROOT_DIR / "data" / "mobility.db"

    examples = {
        "— elegir un ejemplo —": "",
        "Últimas 20 mediciones": (
            "SELECT timestamp, origin, destination, data_source, travel_time_min, "
            "traffic_delay_min\nFROM route_measurements\nORDER BY timestamp DESC\nLIMIT 20;"
        ),
        "Conteo por fuente de datos": (
            "SELECT data_source, COUNT(*) AS filas\nFROM route_measurements\n"
            "GROUP BY data_source;"
        ),
        "Tiempo promedio por ruta (24h)": (
            "SELECT origin, destination, ROUND(AVG(travel_time_min), 2) AS avg_min, "
            "COUNT(*) AS n\nFROM route_measurements\n"
            "WHERE timestamp >= datetime('now', '-24 hours')\n"
            "GROUP BY origin, destination\nORDER BY avg_min DESC;"
        ),
        "KPIs de hoy (Gold layer)": (
            "SELECT * FROM gold_route_kpis\nWHERE date = date('now')\n"
            "ORDER BY reliability_score DESC;"
        ),
        "Tablas disponibles": (
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ),
    }

    selected_example = st.selectbox("Ejemplos", list(examples.keys()))
    default_query = examples[selected_example] or "SELECT * FROM route_measurements LIMIT 20;"

    query = st.text_area("Consulta SQL", value=default_query, height=140)
    run = st.button("▶ Ejecutar", type="primary")

    if run:
        if not query.strip():
            st.warning("Escribe una consulta primero.")
            return

        try:
            # mode=ro: SQLite rechaza cualquier escritura a nivel de motor,
            # no solo por parsear el texto (que se puede burlar con
            # comentarios, subqueries, PRAGMAs, etc.)
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            result_df = pd.read_sql_query(query, conn)
            conn.close()

            st.success(f"{len(result_df)} filas")
            st.dataframe(result_df, width='stretch', hide_index=True)

            if not result_df.empty:
                st.download_button(
                    "⬇ Descargar CSV",
                    result_df.to_csv(index=False).encode("utf-8"),
                    file_name="query_result.csv",
                    mime="text/csv",
                )
        except Exception as e:
            st.error(f"Error en la consulta: {e}")


def render_full_export():
    """Exporta el dataset completo (todas las rutas) en un único CSV."""
    st.subheader("📦 Exportación completa")
    st.caption(
        "Descarga en un solo CSV las mediciones de **todas las rutas**, "
        "a diferencia de la pestaña 'Data Explorer' que solo exporta la "
        "ruta seleccionada arriba. Es una consulta de solo lectura sobre "
        "`mobility.db` (mismo `query_measurements()` que usan las demás "
        "pestañas) — no modifica la base de datos."
    )

    db = get_database()

    col1, col2 = st.columns(2)
    with col1:
        limit_dates = st.checkbox("Limitar por rango de fechas", value=False)
    with col2:
        export_days = st.slider(
            "Días de historial a incluir",
            1, 365, 90,
            disabled=not limit_dates
        )

    if st.button("🔄 Generar exportación completa", type="primary"):
        with st.spinner("Consultando la base de datos..."):
            if limit_dates:
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=export_days)
                full_df = db.query_measurements(
                    start_timestamp=start_date.isoformat(),
                    end_timestamp=end_date.isoformat(),
                    limit=1_000_000
                )
            else:
                full_df = db.query_measurements(limit=1_000_000)

        if full_df.empty:
            st.warning("No hay datos disponibles para el rango seleccionado.")
        else:
            routes_included = full_df[["origin", "destination"]].drop_duplicates()
            st.success(
                f"{len(full_df):,} filas de {len(routes_included)} rutas "
                "listas para descargar."
            )
            st.dataframe(full_df.head(50), width='stretch', height=300)

            csv_data = full_df.to_csv(index=False)
            st.download_button(
                label="📥 Descargar CSV completo",
                data=csv_data,
                file_name=f"mobility_data_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                key="download_full_export"
            )


def main():
    """Analyst dashboard main function."""
    st.set_page_config(page_title="Analyst Dashboard", layout="wide")

    st.markdown("# 🔬 Analyst Dashboard")
    st.markdown("Data exploration, statistical analysis, and model performance")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Data Explorer",
        "Statistical Tests",
        "Correlations",
        "Model Performance",
        "Data Quality",
        "SQL Query",
        "Exportar Todo"
    ])

    with tab1:
        render_data_explorer()

    with tab2:
        render_statistical_tests()

    with tab3:
        render_correlation_matrix()

    with tab4:
        render_model_performance()

    with tab5:
        render_data_quality_report()

    with tab6:
        render_sql_query()

    with tab7:
        render_full_export()

    st.divider()
    st.markdown("""
    **Advanced Analytics Tools:**
    - Time series decomposition and stationarity tests
    - Autocorrelation and partial autocorrelation analysis
    - Anomaly detection via change point identification
    - Multi-model ensemble predictions
    - Data quality and completeness metrics
    """)


if __name__ == "__main__":
    main()
