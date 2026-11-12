"""Analyst dashboard for data team and researchers."""

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.analytics import MobilityAnalytics
from src.analytics.time_series_analysis import TimeSeriesAnalytics
from src.database import RouteDatabase
from streamlit_app.dashboards import predictive_modeling_dashboard
from streamlit_app.dashboards.aislado import render_aislado

# Ver nota en executive_dashboard.py: mismo TTL, misma razón. Especialmente
# importante aquí: st.tabs() ejecuta el contenido de las 7 pestañas en CADA
# rerun (Streamlit no salta el código de una pestaña solo porque no esté
# visible), así que sin caché, cualquier interacción en cualquier pestaña
# re-dispara las consultas de las 7 a la vez.
_CACHE_TTL = 60

logger = logging.getLogger(__name__)

# Tope de filas para consultas de UNA sola ruta. 90 días x ~150 mediciones/día
# por ruta ≈ 13.500 filas: el tope anterior (10.000) las recortaba.
_ROUTE_ROW_LIMIT = 100_000

# El perfil de calidad recorre TODA la tabla (una pasada, ~8 s en el bind mount de
# Windows de Docker) y los datos nuevos llegan cada 15-27 min: no hace falta refrescarlo
# cada minuto. Un mismo perfil alimenta las rutas disponibles, los conteos por ruta y el
# informe de calidad (antes: más de diez consultas, varias repetidas).
_PROFILE_TTL = 300


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
def _fetch_measurements(_db, origin=None, destination=None, days=None, limit=10000):
    """Helper cacheado genérico para query_measurements. `days=None` trae
    sin filtro de fecha (usa el `limit` como único tope)."""
    kwargs = {"origin": origin, "destination": destination, "limit": limit}
    if days is not None:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        kwargs["start_timestamp"] = start_date.isoformat()
        kwargs["end_timestamp"] = end_date.isoformat()
    return _db.query_measurements(**kwargs)


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def _fetch_columns(_db, columns: tuple, days: int):
    """Solo `columns` de todas las mediciones de los últimos `days` días
    (sin LIMIT). `columns` es una tupla para que sirva de clave de caché."""
    return _db.query_columns(list(columns), days)


@st.cache_data(ttl=_PROFILE_TTL, show_spinner="Perfilando la base de datos...")
def _fetch_data_profile(_db):
    """Perfil de toda la tabla en una sola pasada (ver RouteDatabase.get_data_profile)."""
    return _db.get_data_profile()


def _routes(db) -> list:
    """Rutas disponibles como lista de (origen, destino), sacadas del perfil: no cuesta
    una consulta más. Antes get_available_routes() (un `SELECT DISTINCT` que recorre toda
    la tabla) se llamaba 4 veces al abrir Analyst."""
    r = _fetch_data_profile(db)["routes"]
    return list(zip(r["origin"], r["destination"]))


def render_data_explorer():
    """Interactive data explorer."""
    st.subheader("📊 Raw Data Explorer")

    db = get_database()
    routes = _routes(db)

    col1, col2 = st.columns(2)

    with col1:
        selected_route = st.selectbox("Select Route", routes, format_func=lambda x: f"{x[0]} → {x[1]}")

    with col2:
        days = st.slider("Days of History", 1, 90, 30)

    if selected_route:
        origin, destination = selected_route
        # limit=_ROUTE_ROW_LIMIT: query_measurements devuelve las filas MÁS
        # RECIENTES; con el tope anterior (10.000) una ruta con 90 días de
        # historia quedaba recortada sin avisar.
        df = _fetch_measurements(db, origin=origin, destination=destination, days=days, limit=_ROUTE_ROW_LIMIT)

        if not df.empty:
            st.dataframe(df, width="stretch", height=400)

            # Download button
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV", data=csv, file_name=f"data_{origin}_{destination}.csv", mime="text/csv"
            )
        else:
            st.warning("No data available")


def render_statistical_tests():
    """Run statistical tests."""
    st.subheader("📈 Statistical Analysis")

    db = get_database()
    routes = _routes(db)

    selected_route = st.selectbox(
        "Select Route for Analysis", routes, format_func=lambda x: f"{x[0]} → {x[1]}", key="stats_route"
    )

    if selected_route:
        origin, destination = selected_route
        df = _fetch_measurements(db, origin=origin, destination=destination, days=30, limit=_ROUTE_ROW_LIMIT)

        if not df.empty and len(df) > 10:
            ts_analysis = TimeSeriesAnalytics(df)

            tab1, tab2, tab3, tab4 = st.tabs(["Stationarity Tests", "Autocorrelation", "Patterns", "Anomalies"])

            with tab1:
                st.markdown("**Stationarity Tests** (ADF & KPSS)")
                stationarity = ts_analysis.stationarity_tests("travel_time_min")
                if "adf" in stationarity:
                    st.json(stationarity["adf"])
                if "kpss" in stationarity:
                    st.json(stationarity["kpss"])

            with tab2:
                st.markdown("**Autocorrelation Analysis**")
                acf_data = ts_analysis.autocorrelation_analysis("travel_time_min")
                if "acf" in acf_data:
                    st.json(acf_data["acf"])

            with tab3:
                st.markdown("**Day-of-Week Patterns**")
                patterns = ts_analysis.day_of_week_patterns("travel_time_min")
                if "by_day" in patterns:
                    st.json(patterns["by_day"])

            with tab4:
                st.markdown("**Anomaly Detection**")
                anomalies = ts_analysis.change_point_detection("travel_time_min")
                if "change_points" in anomalies:
                    st.write(f"**Total anomalies detected:** {anomalies['total_changes']}")
                    if anomalies["change_points"]:
                        st.json(anomalies["change_points"][:10])


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
    # Muestras por ruta: salen del perfil de la base (una sola pasada compartida con el
    # informe de calidad). Antes: una consulta por ruta con LIMIT 1000 (que ni daba el
    # conteo real) y luego get_all_routes_statistics() con una ventana de 10 años, un
    # recorrido completo de la tabla solo para contar filas.
    profile_routes = _fetch_data_profile(db)["routes"]
    samples_by_route = {(row["origin"], row["destination"]): int(row["rows"]) for _, row in profile_routes.iterrows()}

    routes = _routes(db)
    if routes:
        st.markdown("**Model Metrics by Route**")
        model_data = []
        for origin, destination in routes:
            model_data.append(
                {
                    "Route": f"{origin} → {destination}",
                    "Model Status": (
                        "✅ Trained"
                        if any(m for m in model_files if f"{origin}_{destination}" in m.name)
                        else "❌ Not Trained"
                    ),
                    "Samples": samples_by_route.get((origin, destination), 0),
                }
            )

        if model_data:
            model_df = pd.DataFrame(model_data)
            st.dataframe(model_df, width="stretch", hide_index=True)

    st.divider()
    predictive_modeling_dashboard.render()


def render_correlation_matrix():
    """Render correlation matrix between variables."""
    st.subheader("📊 Feature Correlation Analysis")

    db = get_database()
    numeric_cols = db.get_numeric_columns()

    if numeric_cols:
        defaults = [c for c in ("travel_time_min", "average_speed_kmh", "origin_temperature") if c in numeric_cols]
        selected_cols = st.multiselect(
            "Select columns for correlation",
            numeric_cols,
            default=defaults,
        )

        if selected_cols and len(selected_cols) > 1:
            # Solo las columnas elegidas, de TODAS las mediciones de los
            # últimos 30 días (antes: las 10.000 más recientes, ~5 días).
            df = _fetch_columns(db, tuple(selected_cols), days=30)
            corr_matrix = df.corr()

            fig = go.Figure(
                data=go.Heatmap(
                    z=corr_matrix.values,
                    x=corr_matrix.columns,
                    y=corr_matrix.columns,
                    colorscale="RdBu",
                    zmid=0,
                    text=corr_matrix.values,
                    texttemplate="%{text:.2f}",
                    textfont={"size": 10},
                )
            )

            fig.update_layout(title="Feature Correlation Matrix", height=500, template="plotly_dark")

            st.plotly_chart(fig, width="stretch")


def _completeness_by_route(db) -> pd.DataFrame:
    """% de completitud (celdas no vacías) por ruta, sacado del perfil de la base.

    Antes: una consulta por ruta (`LIMIT 1000`, 12 en total; ~33 s en el bind mount de
    Windows de Docker) sobre una muestra de las 1.000 filas más recientes y contando
    también `id`, `polyline` y `created_at`. Ahora sale de la misma pasada que el resto
    del informe, sobre TODAS las filas y solo las columnas de medición.
    """
    routes = _fetch_data_profile(db)["routes"]
    return pd.DataFrame(
        {
            "Route": routes["origin"] + " → " + routes["destination"],
            "Completeness": routes["completeness_pct"].map(lambda v: f"{v:.1f}%"),
            "Records": routes["rows"],
        }
    )


def render_data_quality_report():
    """Data quality report."""
    st.subheader("✅ Data Quality Report")

    db = get_database()
    profile = _fetch_data_profile(db)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Records", f"{profile['total_rows']:,}")

    with col2:
        missing_pct = profile["missing_pct"]
        st.metric("Missing Values", f"{missing_pct:.1f}%", "✅" if missing_pct < 5 else "⚠️")

    with col3:
        # Filas repetidas para la misma ruta, instante y fuente. La clave UNIQUE de la tabla
        # debería impedirlas, así que lo normal es 0: es una comprobación de que la
        # restricción sigue en pie. (La versión anterior contaba duplicados exactos de la
        # fila entera INCLUYENDO `id`, que es autoincremental, así que daba 0 siempre.)
        duplicates = profile["duplicates"]
        st.metric("Duplicates", duplicates, "✅" if duplicates == 0 else "⚠️")

    with col4:
        # Rango real de la base completa (antes: texto fijo "30+ days").
        first_ts, last_ts = profile["first_timestamp"], profile["last_timestamp"]
        if first_ts and last_ts:
            span_days = (pd.to_datetime(last_ts, utc=True) - pd.to_datetime(first_ts, utc=True)).days
            st.metric(
                "Date Range", f"{span_days} days", f"{str(first_ts)[:10]} → {str(last_ts)[:10]}", delta_color="off"
            )
        else:
            st.metric("Date Range", "sin datos")

    st.caption(
        f"Calculado sobre **toda** la base en una sola pasada ({len(profile['measurement_columns'])} columnas de "
        "medición; no se cuentan `id`, `polyline` ni `created_at`). Se refresca cada 5 minutos."
    )
    # Data completeness by route
    st.markdown("**Completeness by Route**")
    comp_df = _completeness_by_route(db)
    if not comp_df.empty:
        st.dataframe(comp_df, width="stretch", hide_index=True)


def _read_only_query(db_path, query: str) -> pd.DataFrame:
    """Ejecuta `query` sobre la base en solo lectura REAL.

    `mode=ro` impide modificar los datos (INSERT/UPDATE/DELETE/DROP/CREATE fallan), pero NO impide que
    `ATTACH DATABASE 'x'` ni `VACUUM INTO 'x'` creen archivos nuevos en disco (medido): con `VACUUM INTO`
    se vuelca una copia completa de la base a cualquier ruta escribible. Por eso, además, se instala un
    *authorizer* que solo deja pasar SELECT/WITH y funciones, y deniega el resto (ATTACH, VACUUM, PRAGMA,
    escrituras, `load_extension`...). La conexión se cierra siempre, también si la consulta falla.
    """
    import sqlite3

    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}

    def authorizer(action, arg1, arg2, db_name, source):
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.set_authorizer(authorizer)
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()


def render_sql_query():
    """Editor de SQL de solo lectura sobre data/mobility.db."""
    st.subheader("🗄️ SQL Query")
    st.caption(
        "Consultas de solo lectura sobre `data/mobility.db` (SQLite). "
        "La conexión se abre en modo `mode=ro` y solo se permiten `SELECT`/`WITH`: "
        "INSERT/UPDATE/DELETE/DROP, `ATTACH`, `VACUUM` y `PRAGMA` los rechaza el propio "
        "SQLite, no un chequeo de texto — no puede corromper los datos que el "
        "collector está escribiendo en paralelo ni crear archivos en disco."
    )

    db_path = ROOT_DIR / "data" / "mobility.db"

    examples = {
        "— elegir un ejemplo —": "",
        "Últimas 20 mediciones": (
            "SELECT timestamp, origin, destination, data_source, travel_time_min, "
            "traffic_delay_min\nFROM route_measurements\nORDER BY timestamp DESC\nLIMIT 20;"
        ),
        "Conteo por fuente de datos": (
            "SELECT data_source, COUNT(*) AS filas\nFROM route_measurements\n" "GROUP BY data_source;"
        ),
        "Tiempo promedio por ruta (24h)": (
            "SELECT origin, destination, ROUND(AVG(travel_time_min), 2) AS avg_min, "
            "COUNT(*) AS n\nFROM route_measurements\n"
            "WHERE timestamp >= datetime('now', '-24 hours')\n"
            "GROUP BY origin, destination\nORDER BY avg_min DESC;"
        ),
        "KPIs de hoy (Gold layer)": (
            "SELECT * FROM gold_route_kpis\nWHERE date = date('now')\n" "ORDER BY reliability_score DESC;"
        ),
        "Tablas disponibles": ("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"),
        "POIs de Foursquare por categoría": (
            "SELECT category, COUNT(*) AS n\nFROM pois_foursquare\n" "GROUP BY category\nORDER BY n DESC;"
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
            result_df = _read_only_query(db_path, query)

            st.success(f"{len(result_df)} filas")
            st.dataframe(result_df, width="stretch", hide_index=True)

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
        export_days = st.slider("Días de historial a incluir", 1, 365, 90, disabled=not limit_dates)

    include_polyline = st.checkbox(
        "Incluir la columna `polyline` (geometría de la ruta)",
        value=True,
        help=(
            "Es el 93% del tamaño: con ella el CSV pesa cientos de MB y construirlo necesita "
            "~14× más memoria (el contenedor del dashboard tiene un límite de 1 GiB). "
            "Se deja marcada por defecto para que el archivo siga siendo idéntico al de siempre; "
            "el notebook de la Asignatura 7 hace `select(-polyline)` y la espera. Desmárcala para "
            'una exportación ligera (en ese caso usa `select(-any_of("polyline"))` en R).'
        ),
    )

    if st.button("🔄 Generar exportación completa", type="primary"):
        with st.spinner("Consultando la base de datos..."):
            if limit_dates:
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=export_days)
                full_df = db.query_measurements(
                    start_timestamp=start_date.isoformat(),
                    end_timestamp=end_date.isoformat(),
                    limit=1_000_000,
                    include_polyline=include_polyline,
                )
            else:
                full_df = db.query_measurements(limit=1_000_000, include_polyline=include_polyline)

        if full_df.empty:
            st.warning("No hay datos disponibles para el rango seleccionado.")
        else:
            routes_included = full_df[["origin", "destination"]].drop_duplicates()
            st.success(f"{len(full_df):,} filas de {len(routes_included)} rutas " "listas para descargar.")
            st.dataframe(full_df.head(50), width="stretch", height=300)

            csv_data = full_df.to_csv(index=False)
            st.download_button(
                label="📥 Descargar CSV completo",
                data=csv_data,
                file_name=f"mobility_data_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                key="download_full_export",
            )


def _render_aislado(nombre: str, render) -> None:
    """Ejecuta el contenido de una pestaña; si falla, el error se muestra DENTRO de esa pestaña y las demás siguen.

    st.tabs() ejecuta las siete pestañas en cada rerun, así que sin esto una excepción en una (una consulta, un modelo,
    una tabla ausente) tumbaba la página entera y ninguna pestaña se veía. Solo se captura `Exception`: `st.stop()` y
    `st.rerun()` usan excepciones de control (BaseException) y deben seguir propagándose.
    """
    render_aislado(nombre, render, logger, ambito="Analyst", unidad="la pestaña", plural="pestañas")


def main():
    """Analyst dashboard main function."""
    st.set_page_config(page_title="Analyst Dashboard", layout="wide")

    st.markdown("# 🔬 Analyst Dashboard")
    st.markdown("Data exploration, statistical analysis, and model performance")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        [
            "Data Explorer",
            "Statistical Tests",
            "Correlations",
            "Model Performance",
            "Data Quality",
            "SQL Query",
            "Exportar Todo",
        ]
    )

    with tab1:
        _render_aislado("Data Explorer", render_data_explorer)

    with tab2:
        _render_aislado("Statistical Tests", render_statistical_tests)

    with tab3:
        _render_aislado("Correlations", render_correlation_matrix)

    with tab4:
        _render_aislado("Model Performance", render_model_performance)

    with tab5:
        _render_aislado("Data Quality", render_data_quality_report)

    with tab6:
        _render_aislado("SQL Query", render_sql_query)

    with tab7:
        _render_aislado("Exportar Todo", render_full_export)

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
