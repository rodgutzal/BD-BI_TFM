"""
Genera docs/TESTS.md: el catálogo de TODOS los tests del proyecto, una línea por test.

Por qué existe: los tests deben estar documentados, y una lista escrita a mano se
desactualiza en cuanto alguien añade uno. Este script la deriva del propio código
(módulo `ast`, sin ejecutar nada ni importar los tests): para cada `tests/test_*.py`
toma la descripción del módulo y, de cada función `test_*`, su nombre, cuántos
casos genera `@pytest.mark.parametrize` (si los valores son literales) y la primera
frase de su docstring.

`tests/test_tests_documentation.py` ejecuta la comprobación en el CI: si el catálogo
no coincide con el código, el test falla y dice qué hacer.

Uso (desde la raíz del proyecto):
    python tools/generate_tests_doc.py            # reescribe docs/TESTS.md
    python tools/generate_tests_doc.py --check    # no escribe; sale con 1 si está desactualizado
"""

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
OUTPUT = ROOT / "docs" / "TESTS.md"


@dataclass
class TestInfo:
    name: str  # "test_algo" o "TestClase::test_algo"
    doc: str  # primer párrafo del docstring, en una línea ("" si no tiene)
    cases: Optional[int]  # casos que genera parametrize; None si no se pueden contar


@dataclass
class FileInfo:
    path: str  # "tests/test_x.py"
    doc: str  # docstring completo del módulo
    tests: List[TestInfo] = field(default_factory=list)

    @property
    def functions(self) -> int:
        return len(self.tests)

    @property
    def cases(self) -> int:
        # Un parametrize que no se puede contar (valores no literales) cuenta como 1.
        return sum(t.cases if t.cases is not None else 1 for t in self.tests)

    @property
    def has_uncounted(self) -> bool:
        return any(t.cases is None for t in self.tests)


def parametrize_cases(func: ast.AST) -> Optional[int]:
    """Casos que genera un test: el producto de los `@pytest.mark.parametrize`
    apilados. None si algún conjunto de valores no es un literal."""
    total = 1
    for dec in getattr(func, "decorator_list", []):
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "parametrize":
            if len(dec.args) < 2:
                return None
            try:
                total *= len(ast.literal_eval(dec.args[1]))
            except (ValueError, SyntaxError, TypeError):
                return None
    return total


def _first_paragraph(doc: Optional[str]) -> str:
    if not doc:
        return ""
    return " ".join(doc.strip().split("\n\n")[0].split())


def _tests_in(body, prefix: str = "") -> List[TestInfo]:
    found = []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            found.append(
                TestInfo(prefix + node.name, _first_paragraph(ast.get_docstring(node)), parametrize_cases(node))
            )
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            found.extend(_tests_in(node.body, prefix=f"{node.name}::"))
    return found


def collect(tests_dir: Path = TESTS_DIR) -> List[FileInfo]:
    files = []
    for path in sorted(tests_dir.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        files.append(
            FileInfo(
                path=f"tests/{path.name}",
                doc=(ast.get_docstring(tree) or "").strip(),
                tests=_tests_in(tree.body),
            )
        )
    return files


def render(files: List[FileInfo], tests_dir: Path = TESTS_DIR) -> str:
    n_func = sum(f.functions for f in files)
    n_cases = sum(f.cases for f in files)
    out = [
        "# Catálogo de tests",
        "",
        "> **Archivo generado automáticamente. No editar a mano.** Se deriva del código de `tests/` con",
        "> `python tools/generate_tests_doc.py`; el CI (`tests/test_tests_documentation.py`) falla si",
        "> está desactualizado. Para añadir un test: escríbelo con un nombre y un docstring descriptivos,",
        "> añade su archivo a la tabla de la sección *Tests* del README (si es un archivo nuevo) y",
        "> regenera este catálogo.",
        "",
        f"**{len(files)} archivos · {n_func} funciones de test · {n_cases} casos** "
        "(un caso es una ejecución: un test parametrizado genera varios).",
        "",
        "| Archivo | Funciones | Casos |",
        "|---|---:|---:|",
    ]
    for f in files:
        mark = "+" if f.has_uncounted else ""
        out.append(f"| [`{f.path}`](#{_anchor(f.path)}) | {f.functions} | {f.cases}{mark} |")
    if any(f.has_uncounted for f in files):
        out += ["", "`+` = hay un `parametrize` con valores no literales; esos tests se cuentan como 1 caso."]

    for f in files:
        out += ["", f"## `{f.path}`", ""]
        if f.doc:
            out += [f"> {line}" if line else ">" for line in f.doc.splitlines()]
            out.append("")
        for t in f.tests:
            extra = f" ×{t.cases}" if (t.cases or 1) > 1 else ""
            desc = f" — {t.doc}" if t.doc else ""
            out.append(f"- `{t.name}`{extra}{desc}")

    support = sorted(p for p in tests_dir.glob("*.py") if not p.name.startswith("test_") and p.name != "__init__.py")
    if support:
        out += ["", "## Archivos de apoyo (no contienen tests)", ""]
        for p in support:
            doc = ast.get_docstring(ast.parse(p.read_text(encoding="utf-8"))) or ""
            first = " ".join(doc.split("\n\n")[0].split()) if doc else "(sin descripción)"
            out.append(f"- `tests/{p.name}` — {first}")
    return "\n".join(out) + "\n"


def _anchor(path: str) -> str:
    """Ancla de GitHub para el encabezado `## \\`tests/test_x.py\\``: minúsculas y sin `/` ni `.`
    (los guiones bajos se conservan)."""
    return path.replace("/", "").replace(".", "").lower()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="no escribe; sale con 1 si docs/TESTS.md está desactualizado")
    args = ap.parse_args(argv)

    nuevo = render(collect())
    actual = OUTPUT.read_text(encoding="utf-8").replace("\r\n", "\n") if OUTPUT.exists() else None
    if args.check:
        if actual == nuevo:
            print("docs/TESTS.md está al día.")
            return 0
        print("docs/TESTS.md está DESACTUALIZADO. Ejecuta: python tools/generate_tests_doc.py", file=sys.stderr)
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(nuevo, encoding="utf-8", newline="\n")
    print(f"Escrito {OUTPUT.relative_to(ROOT)} ({len(nuevo.splitlines())} líneas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
