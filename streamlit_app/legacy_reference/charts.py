"""Funciones para crear gráficas claras e intuitivas."""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_travel_time_chart(df: pd.DataFrame) -> go.Figure:
    """Crea gráfica clara de tiempo de viaje con y sin tráfico."""
    if df.empty:
        return go.Figure().add_annotation(text="Sin datos disponibles")

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["travel_time_min"],
        mode="lines+markers",
        name="⏱️ Con Tráfico",
        line=dict(color="#FF6B6B", width=3),
        marker=dict(size=6),
        hovertemplate="<b>Con tráfico</b><br>%{y:.1f} min<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["no_traffic_time_min"],
        mode="lines",
        name="🚀 Sin Tráfico",
        line=dict(color="#51CF66", width=2, dash="dash"),
        hovertemplate="<b>Sin tráfico</b><br>%{y:.1f} min<extra></extra>",
    ))

    avg_travel = df["travel_time_min"].mean()
    fig.add_hline(
        y=avg_travel,
        line_dash="dot",
        line_color="rgba(255,255,255,0.3)",
        annotation_text=f"Promedio: {avg_travel:.1f} min",
        annotation_position="right",
    )

    fig.update_layout(
        title="⏱️ Tiempo de Viaje",
        yaxis_title="Minutos",
        xaxis_title="Hora",
        hovermode="x unified",
        template="plotly_dark",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
    )

    return fig


def create_traffic_delay_chart(df: pd.DataFrame) -> go.Figure:
    """Crea gráfica del retraso por tráfico con indicadores visuales."""
    if df.empty:
        return go.Figure().add_annotation(text="Sin datos disponibles")

    colors = []
    for delay in df["traffic_delay_min"]:
        if pd.isna(delay):
            colors.append("#ADB5BD")  # Gris - Sin datos de tráfico (ej. fuente ORS)
        elif delay <= 1:
            colors.append("#51CF66")  # Verde - Sin tráfico
        elif delay <= 4:
            colors.append("#FFD93D")  # Amarillo - Tráfico moderado
        else:
            colors.append("#FF6B6B")  # Rojo - Tráfico pesado

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df["timestamp"],
        y=df["traffic_delay_min"],
        marker_color=colors,
        hovertemplate="<b>Retraso</b><br>%{y:.1f} min<extra></extra>",
        name="Retraso",
    ))

    avg_delay = df["traffic_delay_min"].mean()
    fig.add_hline(
        y=avg_delay,
        line_dash="dash",
        line_color="white",
        annotation_text=f"Promedio: {avg_delay:.1f} min",
        annotation_position="right",
    )

    fig.update_layout(
        title="🚗 Retraso por Tráfico",
        yaxis_title="Minutos de Retraso",
        xaxis_title="Hora",
        hovermode="x",
        template="plotly_dark",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        showlegend=False,
    )

    return fig


def create_speed_chart(df: pd.DataFrame) -> go.Figure:
    """Crea gráfica de velocidad promedio con zona de confort."""
    if df.empty:
        return go.Figure().add_annotation(text="Sin datos disponibles")

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["average_speed_kmh"],
        mode="lines+markers",
        name="Velocidad",
        line=dict(color="#4ECDC4", width=3),
        marker=dict(size=6),
        fill="tozeroy",
        fillcolor="rgba(78, 205, 196, 0.2)",
        hovertemplate="<b>Velocidad</b><br>%{y:.1f} km/h<extra></extra>",
    ))

    avg_speed = df["average_speed_kmh"].mean()
    fig.add_hline(
        y=avg_speed,
        line_dash="dot",
        line_color="rgba(255,255,255,0.3)",
        annotation_text=f"Promedio: {avg_speed:.1f} km/h",
        annotation_position="right",
    )

    fig.update_layout(
        title="⚡ Velocidad Promedio",
        yaxis_title="km/h",
        xaxis_title="Hora",
        hovermode="x unified",
        template="plotly_dark",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        showlegend=False,
    )

    return fig


def create_temperature_chart(df: pd.DataFrame) -> go.Figure:
    """Crea gráfica de temperatura con código de colores."""
    if df.empty or "origin_temperature" not in df.columns:
        return go.Figure().add_annotation(text="Sin datos de temperatura disponibles")

    # Usar 'origin_temperature' o 'temperature' como fallback
    temp_col = "origin_temperature" if "origin_temperature" in df.columns else "temperature"
    if temp_col not in df.columns:
        return go.Figure().add_annotation(text="Sin datos de temperatura disponibles")

    colors = []
    for temp in df[temp_col]:
        if pd.isna(temp):
            colors.append("gray")
        elif temp < 15:
            colors.append("#4A90E2")  # Azul - Frío
        elif temp < 25:
            colors.append("#51CF66")  # Verde - Moderado
        else:
            colors.append("#FF6B6B")  # Rojo - Cálido

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df[temp_col],
        mode="lines+markers",
        name="Temperatura",
        line=dict(color="#FF9F1C", width=3),
        marker=dict(size=6, color=colors),
        fill="tozeroy",
        fillcolor="rgba(255, 159, 28, 0.2)",
        hovertemplate="<b>Temperatura</b><br>%{y:.1f}°C<extra></extra>",
    ))

    fig.update_layout(
        title="🌡️ Temperatura",
        yaxis_title="°C",
        xaxis_title="Hora",
        hovermode="x unified",
        template="plotly_dark",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        showlegend=False,
    )

    return fig


def create_humidity_chart(df: pd.DataFrame) -> go.Figure:
    """Crea gráfica de humedad."""
    if df.empty or "origin_humidity" not in df.columns:
        return go.Figure().add_annotation(text="Sin datos de humedad disponibles")

    # Usar 'origin_humidity' o 'humidity' como fallback
    humid_col = "origin_humidity" if "origin_humidity" in df.columns else "humidity"
    if humid_col not in df.columns:
        return go.Figure().add_annotation(text="Sin datos de humedad disponibles")

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df[humid_col],
        mode="lines+markers",
        name="Humedad",
        line=dict(color="#6C5CE7", width=3),
        marker=dict(size=6),
        fill="tozeroy",
        fillcolor="rgba(108, 92, 231, 0.2)",
        hovertemplate="<b>Humedad</b><br>%{y:.0f}%<extra></extra>",
    ))

    fig.update_layout(
        title="💧 Humedad",
        yaxis_title="% Humedad",
        xaxis_title="Hora",
        hovermode="x unified",
        template="plotly_dark",
        height=400,
        margin=dict(l=0, r=0, t=40, b=0),
        showlegend=False,
        yaxis=dict(range=[0, 100]),
    )

    return fig
