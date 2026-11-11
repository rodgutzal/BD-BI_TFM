"""Las versiones de black e isort están fijadas en varios sitios; que no se desincronicen.

Cada versión mayor de black puede cambiar el formato, así que el CI y `requirements-dev.txt` tienen que
usar la misma. Si una copia se actualiza y otra no, el chequeo bloqueante pasa en local y falla en el CI.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUENTES = {
    "workflow": ROOT / ".github" / "workflows" / "tests.yml",
    "requirements-dev": ROOT / "requirements-dev.txt",
    "README": ROOT / "README.md",
}


def _versiones(herramienta: str) -> dict:
    encontradas = {}
    for nombre, ruta in FUENTES.items():
        texto = ruta.read_text(encoding="utf-8")
        encontradas[nombre] = set(re.findall(rf"\b{herramienta}==(\d+(?:\.\d+)+)", texto))
    return encontradas


def test_black_tiene_la_misma_version_fijada_en_el_ci_los_requisitos_y_el_readme():
    """`black==X` aparece con la misma versión en el workflow, en requirements-dev.txt y en el README."""
    versiones = _versiones("black")
    assert all(len(v) == 1 for v in versiones.values()), f"cada archivo debe fijar black una vez: {versiones}"
    assert len({next(iter(v)) for v in versiones.values()}) == 1, f"versiones distintas de black: {versiones}"


def test_isort_tiene_la_misma_version_fijada_en_el_ci_los_requisitos_y_el_readme():
    """`isort==X` aparece con la misma versión en el workflow, en requirements-dev.txt y en el README."""
    versiones = _versiones("isort")
    assert all(len(v) == 1 for v in versiones.values()), f"cada archivo debe fijar isort una vez: {versiones}"
    assert len({next(iter(v)) for v in versiones.values()}) == 1, f"versiones distintas de isort: {versiones}"


def test_el_ci_formatea_los_mismos_directorios_que_comprueba_flake8_y_black_lee_pyproject():
    """El job de formato comprueba `src/ tests/ streamlit_app/ tools/` sin repetir opciones (van en pyproject.toml)."""
    texto = FUENTES["workflow"].read_text(encoding="utf-8")
    assert "black src/ tests/ streamlit_app/ tools/ --check\n" in texto
    assert "isort src/ tests/ streamlit_app/ tools/ --check-only\n" in texto
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "line-length = 120" in pyproject and 'profile = "black"' in pyproject
