"""Aislamiento de errores por sección de un dashboard.

Streamlit ejecuta todo el script en cada rerun: una excepción en una sección (una consulta, un modelo, una tabla
ausente) tumbaba la página entera y ninguna otra sección se veía. `render_aislado` ejecuta una sección y, si falla,
muestra el error DENTRO de esa sección y deja que las demás sigan.
"""

import logging
from typing import Callable

import streamlit as st


def render_aislado(
    nombre: str,
    render: Callable[[], None],
    logger: logging.Logger,
    *,
    ambito: str,
    unidad: str = "la sección",
    plural: str = "secciones",
) -> None:
    """Ejecuta `render()`; si lanza una excepción, la muestra en su sitio, la registra y deja seguir al resto.

    Solo se captura `Exception`: `st.stop()` y `st.rerun()` usan excepciones de control (BaseException) y deben seguir
    propagándose. El error se registra con su traza completa en `logger`.

    La sección se dibuja dentro de un hueco (`st.empty()`): si falla a mitad, lo que ya había dibujado se retira, para que
    nadie lea como completas unas tarjetas o una tabla a medias.
    """
    hueco = st.empty()
    try:
        with hueco.container():
            render()
    except Exception as e:
        hueco.empty()
        logger.exception("Falló %s «%s» del %s", unidad, nombre, ambito)
        st.error(f"No se pudo mostrar «{nombre}»: {type(e).__name__}: {e}")
        st.caption(f"Las demás {plural} no se ven afectadas. El detalle completo está en el registro de la aplicación.")
