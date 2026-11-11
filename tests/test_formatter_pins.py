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


ARCHIVOS_FORMATEADOS = {
    "src/",
    "tests/",
    "streamlit_app/",
    "tools/",
    "collect.py",
    "setup.py",
    "train_ensemble_models.py",
    "train_models.py",
}


def _comandos(herramienta: str) -> list:
    """Líneas del workflow que ejecutan la herramienta (`black ...` / `isort ...`)."""
    texto = FUENTES["workflow"].read_text(encoding="utf-8")
    return [linea.strip() for linea in texto.splitlines() if re.match(rf"\s+{herramienta} \S", linea)]


def test_el_ci_comprueba_el_formato_de_todos_los_archivos_de_codigo_sin_neutralizar_el_paso():
    """Black e isort se ejecutan en modo comprobación sobre todo el código, sin `|| true` ni opciones propias."""
    for herramienta, modo in (("black", "--check"), ("isort", "--check-only")):
        comandos = _comandos(herramienta)
        assert len(comandos) == 1, f"debe haber un único paso de {herramienta}: {comandos}"
        partes = comandos[0].split()[1:]
        assert modo in partes and "||" not in partes, comandos[0]
        assert {p for p in partes if p != modo} == ARCHIVOS_FORMATEADOS, comandos[0]


def test_los_archivos_formateados_existen_y_pyproject_fija_la_configuracion():
    """Las rutas que formatea el CI existen, y la línea de 120 y el perfil black salen de pyproject.toml."""
    faltan = [ruta for ruta in ARCHIVOS_FORMATEADOS if not (ROOT / ruta).exists()]
    assert not faltan, f"el CI formatea rutas que no existen: {faltan}"
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "line-length = 120" in pyproject and 'profile = "black"' in pyproject
