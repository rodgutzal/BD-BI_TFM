"""La documentación de los tests no puede quedarse atrás del código.

Hay una regla del proyecto: todos los tests están documentados. Este archivo la hace cumplir en el CI:
  1. docs/TESTS.md (el catálogo, una línea por test) debe coincidir con lo que genera
     tools/generate_tests_doc.py a partir de tests/;
  2. todo archivo `tests/test_*.py` debe aparecer en la tabla de la sección *Tests* del README, y
     la tabla no puede citar un archivo que ya no exista.

Si falla, el mensaje dice exactamente qué hacer.
"""

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("generate_tests_doc", ROOT / "tools" / "generate_tests_doc.py")
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

README = ROOT / "README.md"
TABLA_INICIO, TABLA_FIN = "<!-- tests:inicio -->", "<!-- tests:fin -->"


def _leer(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


# ---------------------------------------------------------------------------
# El catálogo generado (docs/TESTS.md)
# ---------------------------------------------------------------------------

def test_el_catalogo_de_tests_esta_al_dia():
    esperado = gen.render(gen.collect())
    actual = _leer(gen.OUTPUT) if gen.OUTPUT.exists() else ""
    assert actual == esperado, (
        "docs/TESTS.md no coincide con los tests actuales. Regenéralo y súbelo:\n"
        "    python tools/generate_tests_doc.py"
    )


def test_el_catalogo_menciona_cada_funcion_de_test():
    """Ninguna función `test_*` puede faltar en el catálogo (aunque el resto del texto cambie)."""
    catalogo = _leer(gen.OUTPUT)
    faltan = [
        f"{f.path}::{t.name}"
        for f in gen.collect()
        for t in f.tests
        if f"`{t.name}`" not in catalogo
    ]
    assert not faltan, f"Tests sin documentar en docs/TESTS.md: {faltan}"


# ---------------------------------------------------------------------------
# La tabla del README
# ---------------------------------------------------------------------------

def _archivos_en_la_tabla_del_readme() -> set:
    texto = _leer(README)
    assert TABLA_INICIO in texto and TABLA_FIN in texto, (
        f"Falta el bloque de la tabla de tests en el README (entre {TABLA_INICIO} y {TABLA_FIN})."
    )
    tabla = texto.split(TABLA_INICIO, 1)[1].split(TABLA_FIN, 1)[0]
    return set(re.findall(r"`(test_[A-Za-z0-9_]+\.py)`", tabla))


def test_todo_archivo_de_test_esta_en_la_tabla_del_readme():
    en_disco = {p.name for p in (ROOT / "tests").glob("test_*.py")}
    faltan = sorted(en_disco - _archivos_en_la_tabla_del_readme())
    assert not faltan, (
        f"Archivos de test sin documentar en la tabla de la sección Tests del README: {faltan}. "
        "Añade una fila por cada uno (qué cubre) y regenera docs/TESTS.md."
    )


def test_la_tabla_del_readme_no_cita_archivos_que_ya_no_existen():
    en_disco = {p.name for p in (ROOT / "tests").glob("test_*.py")}
    sobran = sorted(_archivos_en_la_tabla_del_readme() - en_disco)
    assert not sobran, f"La tabla de tests del README cita archivos que no existen: {sobran}. Quita esas filas."


# ---------------------------------------------------------------------------
# El propio generador
# ---------------------------------------------------------------------------

def _funcion(codigo: str):
    return ast.parse(codigo).body[0]


def test_parametrize_con_literales_cuenta_los_casos():
    f = _funcion('@pytest.mark.parametrize("x", [1, 2, 3])\ndef test_a(x): pass')
    assert gen.parametrize_cases(f) == 3


def test_parametrize_apilado_multiplica():
    f = _funcion(
        '@pytest.mark.parametrize("x", [1, 2])\n@pytest.mark.parametrize("y", ["a", "b", "c"])\ndef test_a(x, y): pass'
    )
    assert gen.parametrize_cases(f) == 6


def test_parametrize_con_valores_no_literales_no_se_puede_contar():
    f = _funcion('@pytest.mark.parametrize("x", VALORES)\ndef test_a(x): pass')
    assert gen.parametrize_cases(f) is None


def test_sin_parametrize_es_un_caso():
    assert gen.parametrize_cases(_funcion("def test_a(): pass")) == 1


def test_el_generador_encuentra_funciones_y_metodos_de_clases_test(tmp_path):
    (tmp_path / "test_ejemplo.py").write_text(
        '"""Ejemplo."""\n'
        "def test_uno():\n    '''Primera frase.\n\n    Segundo párrafo, que no se usa.'''\n"
        "def auxiliar(): pass\n"
        "class TestGrupo:\n    def test_dos(self): pass\n",
        encoding="utf-8",
    )
    (tmp_path / "conftest.py").write_text('"""Apoyo."""\n', encoding="utf-8")
    archivos = gen.collect(tmp_path)
    assert [t.name for t in archivos[0].tests] == ["test_uno", "TestGrupo::test_dos"]
    assert archivos[0].tests[0].doc == "Primera frase."
    texto = gen.render(archivos, tmp_path)
    assert "`test_uno` — Primera frase." in texto and "`TestGrupo::test_dos`" in texto
    assert "tests/conftest.py" in texto and "auxiliar" not in texto
