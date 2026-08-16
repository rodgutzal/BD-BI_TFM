"""Main app with multi-level dashboard selection."""

import streamlit as st
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Import dashboard modules
from streamlit_app.dashboards import executive_dashboard, operations_dashboard, analyst_dashboard


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
        ["Executive", "Operations", "Analyst"],
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
    """)

    # System status
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔋 System Status")
    st.sidebar.success("✅ All systems operational")
    st.sidebar.info("📊 Last update: Now")

    # Route dashboard based on selection
    if dashboard == "Executive":
        executive_dashboard.main()
    elif dashboard == "Operations":
        operations_dashboard.main()
    else:  # Analyst
        analyst_dashboard.main()


if __name__ == "__main__":
    main()
