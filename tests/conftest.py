"""Configuración común de pytest."""

import os

# Matplotlib elige por defecto el backend gráfico Tk cuando existe (p. ej. en Windows). Los
# tests de dashboards ejecutan scripts de Streamlit en un hilo (AppTest) y dibujan figuras
# (plot_tree): con Tk eso termina con "Tcl_AsyncDelete: async handler deleted by the wrong
# thread" y el proceso de pytest se cae al cerrar (código de salida 3) aunque todos los tests
# pasen. Los tests nunca necesitan una ventana, así que se fuerza el backend sin interfaz.
os.environ.setdefault("MPLBACKEND", "Agg")


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def datos_ml_con_brecha(tmp_path_factory):
    """Una copia de `data/ml/` con una brecha de oferta SINTÉTICA (solo food_drink y business), para probar el comportamiento
    de la capa opcional de brecha. La tabla versionada ya NO publica brecha (docs/DATOS_Y_LICENCIAS.md): estos valores no son
    reales ni salen de ningún modelo; solo ejercitan la pantalla y la vista."""
    import sys
    from pathlib import Path

    import numpy as np

    raiz = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(raiz))
    from src.ml import panorama

    tabla = panorama.read_panorama(raiz / "data" / "ml")
    counts = panorama.read_counts(raiz / "data" / "ml")
    rng = np.random.default_rng(0)
    for clave in ("food_drink", "business"):
        filas = tabla["perfil"] == clave
        n = int(filas.sum())
        brecha = rng.normal(0, 1, n)
        tabla.loc[filas, "esperado"] = rng.uniform(1, 20, n)
        tabla.loc[filas, "brecha_relativa"] = brecha
        tabla.loc[filas, "brecha_p10"] = brecha - 0.3
        tabla.loc[filas, "brecha_p90"] = brecha + 0.3
        tabla.loc[filas, "modelo_brecha"] = "boosting"
    destino = tmp_path_factory.mktemp("ml_con_brecha")
    manifiesto = {
        "procedencia": {"commit": "sintetico"},
        "parametros": {"con_brecha": True},
        "brecha": {c: {"ganador": None, "modelo_brecha": "boosting"} for c in ("food_drink", "business")},
        "advertencia": "BRECHA SINTÉTICA DE PRUEBA",
    }
    panorama.write_outputs(destino, tabla.set_index("cell_id"), counts, manifiesto)
    return destino
