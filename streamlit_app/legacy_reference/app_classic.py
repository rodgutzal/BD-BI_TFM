"""Dashboard original de BD_BI_TFM (previo a la fusión).

BD_BI_TFM2: NO es el entrypoint activo (streamlit_app/app.py es ahora
app_multi_dashboard.py). Se conserva aquí solo como referencia histórica
del proyecto base — el CSV que leía (`traffic_weather_data.csv`, columnas
datetime/duration_min/temperature/humidity, solo ORS) ya no existe con ese
nombre en el esquema unificado (ver data/raw/legacy_ors_traffic_weather_data.csv
para el archivo original tal cual, o data/raw/route_weather_data.csv para
el histórico fusionado con el esquema nuevo). Para volver a correrlo tal
cual necesitarías apuntar DATA_PATH a legacy_ors_traffic_weather_data.csv.
"""

import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Urban Mobility Analytics (Classic)", page_icon="🚦", layout="wide")

st.title("🚦 Urban Mobility Analytics Dashboard (Classic / BD_BI_TFM)")
st.write("Análisis de movilidad urbana usando OpenRouteService y OpenWeather.")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_PATH = ROOT_DIR / "data" / "raw" / "legacy_ors_traffic_weather_data.csv"

df = pd.read_csv(DATA_PATH)

col1, col2, col3, col4 = st.columns(4)

col1.metric("Ruta", f"{df['origin'].iloc[-1]} → {df['destination'].iloc[-1]}")
col2.metric("Distancia", f"{df['distance_km'].iloc[-1]} km")
col3.metric("Duración estimada", f"{df['duration_min'].iloc[-1]} min")
col4.metric("Movilidad", df["mobility_level"].iloc[-1])

st.subheader("📊 Dataset")
st.dataframe(df, use_container_width=True)

st.subheader("⏱️ Duración estimada")
st.line_chart(df["duration_min"])

st.subheader("🌦️ Temperatura")
st.line_chart(df["temperature"])

st.subheader("💧 Humedad")
st.line_chart(df["humidity"])