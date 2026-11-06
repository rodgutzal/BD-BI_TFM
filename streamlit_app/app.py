"""Main app with multi-level dashboard selection."""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Import dashboard modules
from src.database import RouteDatabase
from streamlit_app.dashboards import (
    executive_dashboard, operations_dashboard, analyst_dashboard, maps_dashboard, recommendation_dashboard,
)

# El collector corre cada 15 min (ORS) y 27 min (TomTom). Pasada una hora sin
# ningún dato nuevo, es casi seguro que el stack está apagado o el collector
# caído (ver README, "El collector de tráfico no recolecta y nada avisa").
STALE_AFTER_MINUTES = 60


@st.cache_resource
def _get_database():
    return RouteDatabase(
        ROOT_DIR / "data" / "raw" / "route_weather_data.csv",
        ROOT_DIR / "data" / "mobility.db",
    )


@st.cache_data(ttl=60, show_spinner=False)
def _last_measurement_timestamp(_db):
    return _db.get_database_summary().get("last_timestamp")


def render_system_status() -> None:
    """Estado del sistema a partir del último dato de tráfico realmente
    guardado (antes eran mensajes fijos: "All systems operational" y
    "Last update: Now", que se mostraban aunque no llegara nada)."""
    try:
        last = _last_measurement_timestamp(_get_database())
    except Exception as e:
        st.sidebar.error(f"❌ No se pudo leer la base de datos: {e}")
        return

    if not last:
        st.sidebar.warning("⚠️ Sin mediciones en la base de datos")
        return

    last_ts = pd.to_datetime(last, utc=True)
    age_min = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
    if age_min > 60 * 48:
        age_txt = f"{age_min / 1440:.1f} días"
    elif age_min > 90:
        age_txt = f"{age_min / 60:.1f} h"
    else:
        age_txt = f"{age_min:.0f} min"

    if age_min > STALE_AFTER_MINUTES:
        st.sidebar.warning(f"⚠️ Sin datos nuevos hace {age_txt}. ¿Está el collector en marcha? (`docker compose ps`)")
    else:
        st.sidebar.success("✅ Recolección activa")
    st.sidebar.info(f"📊 Último dato: {last_ts:%Y-%m-%d %H:%M} UTC (hace {age_txt})")


def main():
    """Main application with dashboard selector."""
    st.set_page_config(
        page_title="Urban Mobility Analytics",
        page_icon="🚗",
        layout="wide"
    )

    # Dashboard selector
    st.sidebar.markdown("## 📊 Dashboard Selection")

    dashboard = st.sidebar.radio(
        "Choose your dashboard:",
        ["Executive", "Operations", "Analyst", "Maps", "Recomendación"],
        index=0,
        label_visibility="collapsed"
    )

    # User info
    st.sidebar.markdown("---")
    st.sidebar.markdown("""
    ### 👤 User Roles

    **Executive:** High-level KPIs and strategic insights

    **Operations:** Real-time monitoring and alerts

    **Analyst:** Data exploration and statistical analysis

    **Maps:** Geographic view of monitored routes

    **Recomendación:** ¿dónde conviene abrir un negocio? (usuario final)
    """)

    # System status (derivado del último dato real de tráfico en la base)
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔋 System Status")
    render_system_status()

    # Route dashboard based on selection
    if dashboard == "Executive":
        executive_dashboard.main()
    elif dashboard == "Operations":
        operations_dashboard.main()
    elif dashboard == "Analyst":
        analyst_dashboard.main()
    elif dashboard == "Maps":
        maps_dashboard.main()
    else:  # Recomendación
        recommendation_dashboard.main()


if __name__ == "__main__":
    main()
