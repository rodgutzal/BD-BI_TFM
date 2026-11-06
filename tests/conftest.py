"""Configuración común de pytest."""

import os

# Matplotlib elige por defecto el backend gráfico Tk cuando existe (p. ej. en Windows). Los
# tests de dashboards ejecutan scripts de Streamlit en un hilo (AppTest) y dibujan figuras
# (plot_tree): con Tk eso termina con "Tcl_AsyncDelete: async handler deleted by the wrong
# thread" y el proceso de pytest se cae al cerrar (código de salida 3) aunque todos los tests
# pasen. Los tests nunca necesitan una ventana, así que se fuerza el backend sin interfaz.
os.environ.setdefault("MPLBACKEND", "Agg")
