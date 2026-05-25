import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Urban Mobility Analytics", page_icon="🚦", layout="wide")

st.title("🚦 Urban Mobility Analytics Dashboard")
st.write("Análisis de movilidad urbana usando OpenRouteService y OpenWeather.")

DATA_PATH = Path("data/raw/traffic_weather_data.csv")

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